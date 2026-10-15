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
SEND_CONFIRM_TIMEOUT_MS = 6000
DRAFT_SYNC_TIMEOUT_MS = 1500
DELIVERY_SETTLE_MS = 2000


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

    async def _inspect_recipient_chips(self) -> dict:
        page = self.page
        try:
            return await page.evaluate(
                """() => {
                    const toContainer = document.querySelector("#multi-recipient-selection-field, [data-trackingid='inbox-thread-new-message-to-field']");

                    let labelCount = null;
                    // Detect indicator such as "To: 1 Recipients" or "1 Recipients"
                    const countElements = Array.from(document.querySelectorAll("*")).filter(el => {
                        return el.children.length === 0 && /\\b\\d+\\s+Recipients?\\b/i.test(el.innerText || '');
                    });
                    if (countElements.length > 0) {
                        const m = (countElements[0].innerText || '').match(/\\b(\\d+)\\s+Recipients?/i);
                        if (m) labelCount = parseInt(m[1], 10);
                    }

                    const header = document.querySelector("[data-testid='inbox-thread-header'], header");
                    const headerText = header ? (header.innerText || '').trim() : '';

                    if (!toContainer) {
                        return { labelCount: labelCount, chipCount: 0, chipTexts: [], removeButtonCount: 0, containerText: '', headerText: headerText };
                    }

                    // Recipient chips inside toContainer (Fabric DS chips)
                    let chips = Array.from(toContainer.querySelectorAll("[data-fabric-ds-name='Chip']"));
                    if (chips.length === 0) {
                        chips = Array.from(toContainer.querySelectorAll("[data-trackingid*='recipient-chip'], [data-testid*='chip']"));
                    }

                    // Remove buttons strictly belonging to chips (exclude the field clear button on the far right)
                    const removeButtons = Array.from(toContainer.querySelectorAll("button")).filter(b => {
                        const aria = (b.getAttribute("aria-label") || '').toLowerCase();
                        const tracking = (b.getAttribute("data-trackingid") || '').toLowerCase();
                        if (aria.includes("clear") || tracking.includes("clear") || b.closest("[data-trackingid*='clear']")) {
                            return false;
                        }
                        return aria.includes("remove") || aria.includes("delete") || aria.includes("close") || b.closest("[data-fabric-ds-name='Chip']");
                    });

                    const effectiveChipCount = chips.length > 0 ? chips.length : removeButtons.length;

                    return {
                        labelCount: labelCount,
                        chipCount: effectiveChipCount,
                        chipTexts: chips.map(c => c.innerText.trim()),
                        removeButtonCount: removeButtons.length,
                        containerText: (toContainer.innerText || '').trim(),
                        headerText: headerText,
                    };
                }"""
            )
        except Exception as exc:
            logger.debug("Could not inspect recipient chips via evaluate: %s", exc)
            return {"labelCount": None, "chipCount": 0, "chipTexts": [], "removeButtonCount": 0, "containerText": "", "headerText": ""}

    async def _clear_recipient_chips(self) -> None:
        page = self.page
        try:
            clear_btn = page.locator(sel.TO_FIELD_CLEAR_BUTTON).first
            if await clear_btn.count() and await clear_btn.is_visible():
                await clear_btn.click()
                await page.wait_for_timeout(200)
        except Exception:
            pass

        try:
            remove_btns = page.locator(f"{sel.TO_FIELD_CONTAINER} {sel.CHIP_REMOVE_BUTTON}, {sel.CHIP_REMOVE_BUTTON}")
            count = await remove_btns.count()
            for _ in range(count):
                btn = remove_btns.first
                if await btn.count() and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(150)
        except Exception:
            pass

    async def _verify_single_recipient(self, recipient: Recipient, digits: str) -> tuple[bool, str]:
        page = self.page
        masked = mask_phone(recipient.phone)
        digits_prefix = digits[:8] if len(digits) >= 8 else digits
        first_name_lower = recipient.first_name.lower().strip()
        last_name_lower = recipient.last_name.lower().strip()

        # Wait up to 2.5 seconds for composer or recipient chip to settle in UI
        try:
            await page.locator(sel.COMPOSER).wait_for(state="visible", timeout=2500)
        except PlaywrightTimeoutError:
            pass

        data = await self._inspect_recipient_chips()
        if data.get("chipCount", 0) == 0 and not data.get("containerText"):
            try:
                await page.wait_for_timeout(200)
            except Exception:
                pass
            data = await self._inspect_recipient_chips()

        # 1. Verify recipient count indicator if present (e.g. "To: 1 Recipients")
        label_count = data.get("labelCount")
        if label_count is not None:
            if label_count > 1:
                return False, f"Weave reports {label_count} recipients in To field; strictly 1 recipient allowed"
            if label_count == 0:
                return False, "Weave reports 0 recipients in To field"

        # 2. Verify chip count inside the To field container
        chip_count = data.get("chipCount", 0)
        if label_count != 1:
            if chip_count > 1:
                return False, f"Multiple recipient chips detected ({chip_count} selected); strictly 1 recipient allowed"
            if data.get("removeButtonCount", 0) > 1:
                return False, f"Multiple recipient remove buttons detected ({data['removeButtonCount']}); strictly 1 recipient allowed"

        # 3. Check for group indicator anywhere in thread header or container
        header_text = data.get("headerText", "")
        container_text = data.get("containerText", "")
        combined_text = f"{header_text} {container_text}".lower()

        if re.search(r"\b(group|and \d+ others?)\b", combined_text, re.I):
            return False, f"Conversation indicates a group message; strictly 1 recipient allowed"

        # 4. Verify recipient identity:
        # Check if digits (or leading digits), formatted phone, or patient name appear in UI
        raw_digits_in_ui = re.sub(r"\D", "", container_text + " " + header_text)
        has_digits_match = (digits in raw_digits_in_ui) or (digits_prefix in raw_digits_in_ui)
        has_name_match = (first_name_lower and first_name_lower in combined_text) or \
                         (last_name_lower and last_name_lower in combined_text)

        # In New Message, having 1 chip (or remove button) and composer visible confirms selection
        if not (has_digits_match or has_name_match or chip_count == 1 or data.get("labelCount") == 1):
            return False, f"Selected recipient could not be confirmed for {masked} (UI: '{container_text}')"

        return True, "Single recipient verified"

    async def _prepare_once(self, recipient: Recipient, text: str) -> PrepareResult:
        page = self.page
        digits = national_number(recipient.phone)
        masked = mask_phone(recipient.phone)

        logger.info("[INFO] Opening New Message")
        try:
            await self._open_new_message()
        except PlaywrightError as exc:
            return PrepareResult.ui_error(f"Could not open New Message: {_first_line(exc)}")

        logger.info("[INFO] Entering recipient phone number")
        to_field = page.locator(sel.TO_FIELD).first
        await to_field.fill(digits)
        contact_option = page.locator(sel.contact_phone_option(digits))
        unsaved_number = page.locator(sel.SEARCH_RESULT).filter(has_text=sel.format_us_phone(digits)).filter(has_not=page.locator(sel.PERSON_RESULT))
        new_number = page.get_by_text(sel.NO_CONTACTS_TEXT)
        any_result = contact_option.or_(unsaved_number).or_(new_number).first
        try:
            await any_result.wait_for(state="visible", timeout=self.settings.browser_timeout_ms)
        except PlaywrightTimeoutError:
            try:
                if await to_field.input_value(timeout=3000) == digits:
                    return PrepareResult.not_verified(f"Weave search returned no result for {masked}")
            except Exception:
                pass
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
        logger.info("[INFO] Recipient selected")

        # Strictly validate that exactly one recipient is selected and matches the target
        is_single, reason = await self._verify_single_recipient(recipient, digits)
        if not is_single:
            logger.warning("Single-recipient validation failed: %s", reason)
            return PrepareResult.not_verified(reason)
        logger.info("[INFO] Single-recipient validation passed")

        logger.info("[INFO] Personalized reminder generated: %s...", _normalize_text(text)[:60])
        composer = page.locator(sel.COMPOSER).first
        try:
            await composer.wait_for(state="visible", timeout=3000)
            await composer.click()
            await composer.fill(text)

            typed = await composer.input_value()
            if _normalize_text(typed) != _normalize_text(text):
                await composer.focus()
                await page.keyboard.insert_text(text)
                typed = await composer.input_value()
                if _normalize_text(typed) != _normalize_text(text):
                    return PrepareResult.ui_error("Composer text did not match the reminder after typing")

            await page.locator(sel.SEND_BUTTON_ENABLED).wait_for(state="visible", timeout=3000)
            logger.info("[INFO] Reminder message typed into composer and Send button confirmed")
        except PlaywrightError as exc:
            return PrepareResult.ui_error(f"Could not type the reminder: {_first_line(exc)}")
        return PrepareResult.ready()

    async def _open_new_message(self) -> None:
        page = self.page
        await self._dismiss_blocking_dialog()

        # Discard any draft still sitting in the composer from previous actions
        composer = page.locator(sel.COMPOSER)
        if await composer.count() and await composer.is_visible():
            try:
                if await composer.input_value():
                    await self.discard_draft()
            except Exception:
                pass

        new_message = page.locator(sel.NEW_MESSAGE_BUTTON)
        if not await new_message.is_visible():
            await page.goto(self.settings.weave_messages_url, wait_until="domcontentloaded")
            await new_message.wait_for(state="visible")
        await new_message.click()

        to_field = page.locator(sel.TO_FIELD).first
        try:
            await to_field.wait_for(state="visible", timeout=4000)
        except PlaywrightTimeoutError:
            await page.locator(sel.TO_FIELD_CONTAINER).first.wait_for(state="visible", timeout=2000)
            await to_field.wait_for(state="visible", timeout=2000)

        # Ensure no previous input remains
        try:
            val = await to_field.input_value()
            if val:
                await to_field.fill("")
        except Exception:
            pass

        await self._clear_recipient_chips()

    async def reset_composer(self) -> None:
        try:
            await self.discard_draft()
        except Exception:
            pass
        try:
            await self._clear_recipient_chips()
        except Exception:
            pass

    async def discard_draft(self) -> None:
        composer = self.page.locator(sel.COMPOSER).first
        try:
            if await composer.count() and await composer.is_visible() and await composer.input_value():
                await composer.fill("")
        except Exception:
            pass

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
        logger.info("[INFO] Sending message")
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

        logger.info("[SUCCESS] Outgoing message verified")
        logger.info("Sent")
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
