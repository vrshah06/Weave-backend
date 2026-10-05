import logging
import re
from typing import Optional

from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from automation import weave_selectors as sel
from automation.driver import DriverError, PrepareResult, Recipient, SendResult, SendStatus
from core.config import AppConfig, config
from utils.phone import mask_phone, national_number

logger = logging.getLogger("weave.driver")

DELIVERY_FAILURE_PATTERN = re.compile(r"not delivered|failed to send|message failed|undeliverable", re.I)
SEND_CONFIRM_TIMEOUT_MS = 15000
DRAFT_SYNC_TIMEOUT_MS = 5000
DELIVERY_SETTLE_MS = 4000


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).lower()


def _first_line(exc: PlaywrightError) -> str:
    return (exc.message or str(exc)).splitlines()[0]


class WeaveDriver:
    def __init__(self, settings: AppConfig = config):
        self.settings = settings
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._blocking_dialog: Optional[Locator] = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise DriverError("Browser is not started")
        return self._page

    async def start(self) -> None:
        profile_dir = self.settings.browser_profile_dir
        profile_dir.mkdir(parents=True, exist_ok=True)
        # The worker lock guarantees no other browser uses this profile, so leftover lock files
        # (from a crash or a container with a different hostname) are stale and would block launch.
        for lock_file in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            (profile_dir / lock_file).unlink(missing_ok=True)
        self.playwright = await async_playwright().start()
        try:
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.settings.browser_profile_dir),
                headless=self.settings.browser_headless,
                slow_mo=self.settings.browser_slow_mo_ms,
                viewport={"width": 1440, "height": 900},
                # Weave's softphone blocks the page with a "Microphone Access" dialog when the browser denies
                # the microphone (headless default). A silent fake device satisfies it; calls are unaffected
                # because this tab never becomes the active softphone.
                permissions=["microphone"],
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--use-fake-ui-for-media-stream",
                    "--use-fake-device-for-media-stream",
                ],
            )
        except PlaywrightError as exc:
            raise DriverError(
                f"Could not launch Chromium ({exc}). Install it with: python -m playwright install --with-deps chromium"
            ) from exc
        self.context.set_default_timeout(self.settings.browser_timeout_ms)
        self._page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        self._blocking_dialog = self._page.get_by_role("dialog").filter(has_text=sel.BLOCKING_DIALOG_TEXT)

    async def _dismiss_blocking_dialog(self) -> None:
        # Click the dialog's own close button; Escape would also close the New Message panel.
        if self._blocking_dialog and await self._blocking_dialog.is_visible():
            logger.info("Dismissing Weave pop-up: %s", sel.BLOCKING_DIALOG_TEXT)
            await self._blocking_dialog.get_by_role("button").first.click(timeout=5000)

    async def authenticate(self) -> None:
        page = self.page
        await page.goto(self.settings.weave_messages_url, wait_until="domcontentloaded", timeout=60000)
        first_visible = page.locator(f"{sel.NEW_MESSAGE_BUTTON}, {sel.LOGIN_FIELDS}").first
        try:
            await first_visible.wait_for(state="visible", timeout=45000)
        except PlaywrightTimeoutError as exc:
            raise DriverError(f"Weave did not load (stuck at {page.url})") from exc
        if await page.locator(sel.NEW_MESSAGE_BUTTON).is_visible():
            return
        await self._log_in()

    async def _log_in(self) -> None:
        if not self.settings.weave_email or not self.settings.weave_password:
            raise DriverError("Weave session expired and WEAVE_EMAIL/WEAVE_PASSWORD are not set")
        page = self.page
        logger.info("Weave session expired; logging in")
        email = page.locator(sel.LOGIN_EMAIL).first
        if await email.is_visible():
            await email.fill(self.settings.weave_email)
            password = page.locator(sel.LOGIN_PASSWORD).first
            if not await password.is_visible():
                await page.locator(sel.LOGIN_SUBMIT).first.click()
        password = page.locator(sel.LOGIN_PASSWORD).first
        try:
            await password.wait_for(state="visible", timeout=20000)
        except PlaywrightTimeoutError as exc:
            raise DriverError("Weave login page did not show a password field") from exc
        await password.fill(self.settings.weave_password)
        await page.locator(sel.LOGIN_SUBMIT).first.click()
        try:
            await page.locator(sel.SIGNED_IN_MARKER).wait_for(state="visible", timeout=60000)
        except PlaywrightTimeoutError as exc:
            raise DriverError(
                "Weave login did not complete (wrong credentials or a verification step; "
                f"stuck at {page.url}, page title {await page.title()!r}). "
                "Log in once with HEADLESS=false to refresh the saved session."
            ) from exc
        await page.goto(self.settings.weave_messages_url, wait_until="domcontentloaded")
        await page.locator(sel.NEW_MESSAGE_BUTTON).wait_for(state="visible")

    async def prepare_message(self, recipient: Recipient, text: str) -> PrepareResult:
        try:
            return await self._prepare_once(recipient, text)
        except PlaywrightError as exc:
            # Weave can re-render mid-step (e.g. a softphone pop-up closes the New Message panel).
            # Nothing has been sent yet, so starting this recipient over once is safe.
            logger.warning("Weave page changed while preparing a message (%s); retrying once", _first_line(exc))
            await self.reset()
            return await self._prepare_once(recipient, text)

    async def _prepare_once(self, recipient: Recipient, text: str) -> PrepareResult:
        page = self.page
        digits = national_number(recipient.phone)
        masked = mask_phone(recipient.phone)

        try:
            await self._open_new_message()
        except PlaywrightError as exc:
            return PrepareResult.ui_error(f"Could not open New Message: {_first_line(exc)}")

        to_field = page.locator(sel.TO_FIELD)
        await to_field.fill(digits)
        contact_option = page.locator(sel.contact_phone_option(digits))
        unsaved_number = page.locator(sel.SEARCH_RESULT).filter(has_text=sel.format_us_phone(digits)).filter(has_not=page.locator(sel.PERSON_RESULT))
        new_number = page.get_by_text(sel.NO_CONTACTS_TEXT)
        any_result = contact_option.or_(unsaved_number).or_(new_number).first
        try:
            await any_result.wait_for(state="visible", timeout=self.settings.browser_timeout_ms)
        except PlaywrightTimeoutError:
            if await to_field.input_value(timeout=3000) == digits:
                return PrepareResult.not_verified(f"Weave search returned no result for {masked}")
            # Weave can reset the field while the page is still initialising; type the number again once.
            await to_field.fill(digits)
            try:
                await any_result.wait_for(state="visible", timeout=self.settings.browser_timeout_ms)
            except PlaywrightTimeoutError:
                return PrepareResult.ui_error(f"Weave search did not respond for {masked}")
        if await contact_option.count():
            await contact_option.first.click()
        elif await unsaved_number.count():
            await unsaved_number.first.click()
        else:
            # Weave: "No contacts found. Press Enter to send a message to a new number".
            await to_field.press("Enter")

        try:
            await page.wait_for_function(
                "([selector, digits]) => { const el = document.querySelector(selector);"
                " return !!el && el.innerText.replace(/\\D/g, '').includes(digits); }",
                arg=[sel.THREAD_HEADER, digits],
            )
        except PlaywrightTimeoutError:
            header = page.locator(sel.THREAD_HEADER)
            shown = (await header.inner_text()).strip() if await header.count() else "no conversation header"
            return PrepareResult.not_verified(f"Conversation is not for {masked} (header: '{' '.join(shown.split())}')")

        composer = page.locator(sel.COMPOSER)
        try:
            # Wait for Weave's draft autosave so a later clear cannot race with it.
            await self._wait_for_draft_request("PUT", composer.fill(text))
            if await composer.input_value() != text:
                return PrepareResult.ui_error("Composer text did not match the reminder after typing")
            await page.locator(sel.SEND_BUTTON_ENABLED).wait_for(state="visible", timeout=5000)
        except PlaywrightError as exc:
            return PrepareResult.ui_error(f"Could not type the reminder: {_first_line(exc)}")
        return PrepareResult.ready()

    async def _open_new_message(self) -> None:
        page = self.page
        await self._dismiss_blocking_dialog()
        new_message = page.locator(sel.NEW_MESSAGE_BUTTON)
        if not await new_message.is_visible():
            await page.goto(self.settings.weave_messages_url, wait_until="domcontentloaded")
        await new_message.click()
        await page.locator(sel.TO_FIELD).wait_for(state="visible")

    async def discard_draft(self) -> None:
        composer = self.page.locator(sel.COMPOSER)
        if not (await composer.is_visible() and await composer.input_value()):
            return
        deleted = await self._wait_for_draft_request("DELETE", composer.fill(""))
        if await composer.input_value():
            raise DriverError("Could not clear the composer")
        if not deleted:
            raise DriverError("Weave did not confirm the draft was deleted; it may remain in Drafts")

    async def _wait_for_draft_request(self, method: str, action) -> bool:
        def is_draft_call(response) -> bool:
            return sel.DRAFT_API_PATH in response.url and response.request.method == method

        try:
            async with self.page.expect_response(is_draft_call, timeout=DRAFT_SYNC_TIMEOUT_MS):
                await action
            return True
        except PlaywrightTimeoutError:
            return False

    async def send_prepared_message(self, text: str) -> SendResult:
        page = self.page
        items = page.locator(sel.THREAD_ITEM)
        items_before = await items.count()
        await page.locator(sel.SEND_BUTTON_ENABLED).click()

        try:
            await page.wait_for_function(
                "selector => { const el = document.querySelector(selector); return el && el.value === ''; }",
                arg=sel.COMPOSER, timeout=SEND_CONFIRM_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError:
            return SendResult(SendStatus.UNCONFIRMED, "Composer still had the text after clicking Send")

        try:
            await page.wait_for_function(
                "([selector, before]) => document.querySelectorAll(selector).length > before",
                arg=[sel.THREAD_ITEM, items_before], timeout=SEND_CONFIRM_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError:
            return SendResult(SendStatus.UNCONFIRMED, "No new message appeared in the conversation")

        # The first line of the reminder contains the appointment date and time, so it identifies this message.
        expected = _normalize_text(text.strip().splitlines()[0])
        newest = items.last
        if expected not in _normalize_text(await newest.inner_text()):
            return SendResult(SendStatus.UNCONFIRMED, "The newest message in the conversation is not this reminder")

        # Give Weave time to flag a failed delivery on the new message before reading its status.
        await page.wait_for_timeout(DELIVERY_SETTLE_MS)
        failure = DELIVERY_FAILURE_PATTERN.search(await newest.inner_text())
        if failure:
            return SendResult(SendStatus.NOT_DELIVERED, f"Weave reported a delivery failure: {failure.group(0)}")
        return SendResult(SendStatus.SENT)

    async def capture_screenshot(self) -> Optional[bytes]:
        return await self.page.screenshot(full_page=False) if self._page else None

    async def reset(self) -> None:
        await self.page.goto(self.settings.weave_messages_url, wait_until="domcontentloaded")
        await self.page.locator(sel.NEW_MESSAGE_BUTTON).wait_for(state="visible")

    async def close(self) -> None:
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        self.context, self.playwright, self._page, self._blocking_dialog = None, None, None, None
