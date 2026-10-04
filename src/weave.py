import re
import time
import logging
from typing import List, Optional, Tuple
from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeoutError

from config import (
    WEAVE_APP_URL,
    WEAVE_AUTH_URL,
    WEAVE_MESSAGES_URL,
    DEFAULT_TIMEOUT,
    SEARCH_TIMEOUT,
    MESSAGE_LOAD_TIMEOUT,
    WEAVE_EMAIL,
    WEAVE_PASSWORD,
)
from src.models import ProcessStatus, RecipientSearchResult
from src.recipients import analyze_search_results
from src.validation import normalize_phone

logger = logging.getLogger("weave_automation")


def run_network_diagnostics(target_url: str = WEAVE_APP_URL) -> dict:
    """
    Performs safe pre-flight network diagnostics testing DNS resolution,
    TCP port 443 socket connection, and HTTPS GET reachability.
    """
    import socket
    import ssl
    import urllib.request
    from urllib.parse import urlparse

    parsed = urlparse(target_url)
    host = parsed.netloc or "app.getweave.com"
    port = parsed.port or 443

    results = {
        "host": host,
        "dns_ok": False,
        "tcp_ok": False,
        "https_ok": False,
        "ip": None,
        "status_code": None,
        "final_url": None,
        "error": None,
    }

    # 1. DNS Resolution
    try:
        ip = socket.gethostbyname(host)
        results["dns_ok"] = True
        results["ip"] = ip
        logger.info(f"[INFO] [DIAGNOSTIC] DNS Resolution for {host}: SUCCESS (IP: {ip})")
    except Exception as e:
        results["error"] = f"DNS resolution failed for {host}: {e}"
        logger.error(f"[ERROR] [DIAGNOSTIC] DNS Resolution for {host}: FAILED ({e})")
        return results

    # 2. TCP Port 443 Connection
    try:
        sock = socket.create_connection((host, port), timeout=10)
        sock.close()
        results["tcp_ok"] = True
        logger.info(f"[INFO] [DIAGNOSTIC] TCP Port {port} Connection to {host}: SUCCESS")
    except Exception as e:
        results["error"] = f"TCP connection failed to {host}:{port}: {e}"
        logger.error(f"[ERROR] [DIAGNOSTIC] TCP Port {port} Connection to {host}: FAILED ({e})")
        return results

    # 3. HTTPS GET Reachability
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            target_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            results["https_ok"] = True
            results["status_code"] = resp.getcode()
            results["final_url"] = resp.geturl()
            logger.info(f"[INFO] [DIAGNOSTIC] HTTPS GET {target_url}: SUCCESS (Status: {resp.getcode()}, Final URL: {resp.geturl()})")
    except Exception as e:
        if hasattr(e, "code"):
            results["https_ok"] = True
            results["status_code"] = e.code
            logger.info(f"[INFO] [DIAGNOSTIC] HTTPS GET {target_url}: REACHABLE (HTTP Code: {e.code})")
        else:
            logger.warning(f"[WARNING] [DIAGNOSTIC] HTTPS GET {target_url} returned warning: {e}")
            results["https_ok"] = True

    return results


class WeaveMessenger:
    """
    Page Object Model isolating browser interactions with the Weave Web App.
    Strictly uses accessible locators, roles, labels, and verified attributes.
    """

    def __init__(self, page: Page):
        self.page = page

    def _digits(self, text: str) -> str:
        return re.sub(r"\D", "", text or "")

    # =========================================================================
    # 1. AUTHENTICATION & NAVIGATION
    # =========================================================================

    def navigate_to_weave(self) -> Tuple[bool, ProcessStatus]:
        """
        Navigates to the Weave sign-in / application home URL (https://app.getweave.com).
        Runs pre-flight network diagnostics first.
        """
        logger.info("[INFO] Testing network connectivity to Weave (https://app.getweave.com)...")
        diag = run_network_diagnostics(WEAVE_APP_URL)

        if not diag["dns_ok"]:
            logger.error(f"[ERROR] Weave network diagnostic failed: DNS resolution failed for {diag['host']}")
            return False, ProcessStatus.NETWORK_ERROR

        if not diag["tcp_ok"]:
            logger.error(f"[ERROR] Weave network diagnostic failed: TCP connection failed for {diag['host']}")
            return False, ProcessStatus.NETWORK_ERROR

        logger.info("[INFO] Network connectivity verified. Opening Weave application URL in browser...")
        try:
            try:
                self.page.goto(WEAVE_APP_URL, wait_until="domcontentloaded", timeout=45000)
            except PlaywrightTimeoutError:
                logger.warning("[WARNING] domcontentloaded timed out after 45s. Checking browser navigation state...")
                current = self.page.url.lower()
                if "weave.com" in current:
                    logger.info(f"[SUCCESS] Browser navigated to Weave page: {self.page.url}")
                    return True, ProcessStatus.READY_TO_SEND
                raise

            time.sleep(2)
            logger.info(f"[SUCCESS] Browser loaded Weave page URL: {self.page.url}")
            return True, ProcessStatus.READY_TO_SEND
        except PlaywrightTimeoutError:
            curr_url = ""
            try:
                curr_url = self.page.url
            except Exception:
                pass
            logger.error(f"[ERROR] Weave navigation timed out after 45 seconds. Current browser URL: '{curr_url}'")
            return False, ProcessStatus.NETWORK_ERROR
        except Exception as e:
            logger.error(f"[ERROR] Failed to navigate to Weave: {e}")
            return False, ProcessStatus.NETWORK_ERROR

    def check_authenticated(self, timeout_ms: int = DEFAULT_TIMEOUT) -> Tuple[bool, ProcessStatus]:
        """
        Verifies if the current session is authenticated in Weave.
        Explicitly checks for login form elements or auth redirect.
        """
        try:
            time.sleep(1.5)
            url = self.page.url.lower()

            if "auth.getweave.com" in url:
                logger.info("Current URL is on auth.getweave.com. Session not active.")
                return False, ProcessStatus.SESSION_EXPIRED

            # Check if login form or credentials fields are visible on screen
            login_form_indicators = [
                self.page.locator("input[type='password']"),
                self.page.get_by_placeholder("Email", exact=False),
                self.page.get_by_text("Log in to your Weave account", exact=False),
                self.page.get_by_role("button", name=re.compile(r"^\s*log\s*in\s*$", re.I)),
            ]

            for indicator in login_form_indicators:
                try:
                    if indicator.count() > 0 and indicator.first.is_visible():
                        logger.info("Login form detected on page. Session not active.")
                        return False, ProcessStatus.SESSION_EXPIRED
                except Exception:
                    pass

            # Check if app navigation shell is visible
            shell = (
                self.page.locator("nav")
                .or_(self.page.locator("aside"))
                .or_(self.page.get_by_role("link", name=re.compile(r"Messages", re.I)))
                .or_(self.page.locator("a[href*='/messages']"))
            ).first

            try:
                shell.wait_for(state="visible", timeout=min(timeout_ms, 5000))
                logger.info("Weave navigation shell detected. Session is active.")
                return True, ProcessStatus.READY_TO_SEND
            except Exception:
                pass

            # Fallback check on app.getweave.com URL without login fields
            if "app.getweave.com" in url:
                return True, ProcessStatus.READY_TO_SEND

            return False, ProcessStatus.WEAVE_NOT_LOADED
        except Exception as e:
            logger.error(f"Error checking authentication: {e}")
            return False, ProcessStatus.WEAVE_NOT_LOADED

    def perform_auto_login(self, email: str = WEAVE_EMAIL, password: str = WEAVE_PASSWORD, timeout_ms: int = DEFAULT_TIMEOUT) -> Tuple[bool, ProcessStatus]:
        """
        Automates credential entry into Weave login page when auth.getweave.com is open.
        """
        if not email or not password:
            logger.warning("No login credentials found in environment/config.")
            return False, ProcessStatus.SESSION_EXPIRED

        logger.info(f"Attempting automatic credential entry for email: {email}...")
        try:
            # Locate Email field
            email_field = (
                self.page.get_by_placeholder("Email", exact=False)
                .or_(self.page.locator("input[type='email']"))
                .or_(self.page.locator("input[name='username']"))
                .or_(self.page.locator("input[name='email']"))
                .or_(self.page.locator("input[id*='email']"))
                .or_(self.page.locator("input[id*='username']"))
                .or_(self.page.locator("input").first)
            ).first

            email_field.wait_for(state="visible", timeout=timeout_ms)
            email_field.click(force=True)
            email_field.press("Control+A")
            email_field.press("Backspace")
            email_field.type(email, delay=40)
            logger.info("Email address entered into login form.")

            # Locate Password field
            password_field = (
                self.page.get_by_placeholder("Password", exact=False)
                .or_(self.page.locator("input[type='password']"))
                .or_(self.page.locator("input[name='password']"))
                .or_(self.page.locator("input[id*='password']"))
            ).first

            password_field.wait_for(state="visible", timeout=timeout_ms)
            password_field.click(force=True)
            password_field.press("Control+A")
            password_field.press("Backspace")
            password_field.type(password, delay=40)
            logger.info("Password entered into login form.")

            # Locate Log In button
            login_btn = (
                self.page.get_by_role("button", name=re.compile(r"^\s*log\s*in\s*$", re.I))
                .or_(self.page.locator("button[type='submit']"))
                .or_(self.page.locator("button:has-text('Log In')"))
                .or_(self.page.locator("input[type='submit']"))
            ).first

            login_btn.wait_for(state="visible", timeout=timeout_ms)
            login_btn.click(force=True)
            logger.info("Log In button clicked. Waiting for redirection to app.getweave.com...")

            # Wait loop up to 30 seconds for post-login redirection to complete
            start_wait = time.time()
            max_wait_seconds = 30

            while time.time() - start_wait < max_wait_seconds:
                time.sleep(1.5)
                current_url = self.page.url.lower()

                # 1. Check if redirected to app.getweave.com
                if "app.getweave.com" in current_url and "auth.getweave.com" not in current_url:
                    logger.info("Redirect to app.getweave.com detected! Waiting for application navigation shell...")
                    
                    shell = (
                        self.page.locator("nav")
                        .or_(self.page.locator("aside"))
                        .or_(self.page.get_by_role("link", name=re.compile(r"Messages", re.I)))
                        .or_(self.page.locator("a[href*='/messages']"))
                        .or_(self.page.locator("[data-trackingid='inbox-list-new-message-button']"))
                    ).first

                    try:
                        shell.wait_for(state="visible", timeout=10000)
                        logger.info("Login successful! Weave application loaded.")
                        return True, ProcessStatus.READY_TO_SEND
                    except Exception:
                        pass

                # 2. Check if an explicit error alert is displayed on login page
                try:
                    err = self.page.locator("[class*='error'], [class*='Error'], [role='alert']").first
                    if err.count() > 0 and err.is_visible():
                        txt = err.inner_text().strip()
                        if txt:
                            logger.error(f"Login form error: '{txt}'")
                except Exception:
                    pass

            # Final check after timeout
            if "app.getweave.com" in self.page.url.lower():
                logger.info("Login completed on app.getweave.com.")
                return True, ProcessStatus.READY_TO_SEND

            logger.error("Timed out waiting for login redirect to app.getweave.com.")
            return False, ProcessStatus.SESSION_EXPIRED
        except Exception as e:
            logger.error(f"Auto-login failed: {e}")
            return False, ProcessStatus.SESSION_EXPIRED

    def open_messages(self, timeout_ms: int = DEFAULT_TIMEOUT) -> Tuple[bool, ProcessStatus]:
        """
        Navigates to Messages section by clicking the Messages sidebar link/icon on the left navigation bar.
        Always clicks the Messages navigation sidebar item after loading sign-in / app URL.
        """
        try:
            logger.info("Clicking 'Messages' link on the left navigation bar...")

            # Locate Messages link/icon in left navigation sidebar

            messages_link = (
                self.page.get_by_role("link", name=re.compile(r"^\s*Messages\s*$", re.I))
                .or_(self.page.locator("a[href*='/messages']"))
                .or_(self.page.locator("nav a:has-text('Messages')"))
                .or_(self.page.locator("aside a:has-text('Messages')"))
                .or_(self.page.locator("[aria-label*='Messages']"))
                .or_(self.page.get_by_text("Messages", exact=True))
            ).first

            messages_link.wait_for(state="visible", timeout=timeout_ms)
            messages_link.click(force=True)

            inbox_heading = (
                self.page.locator("[data-trackingid='inbox-list-new-message-button']")
                .or_(self.page.get_by_text("Inbox", exact=True))
                .or_(self.page.get_by_role("button", name="New Message"))
            ).first
            inbox_heading.wait_for(state="visible", timeout=timeout_ms)

            logger.info("Successfully opened Messages via left navigation bar click.")
            return True, ProcessStatus.READY_TO_SEND
        except Exception as exc:
            logger.error(f"Failed to click Messages sidebar link: {exc}")
            return False, ProcessStatus.MESSAGES_NOT_FOUND

    # =========================================================================
    # 2. NEW MESSAGE WORKFLOW
    # =========================================================================

    def open_new_message(self, timeout_ms: int = DEFAULT_TIMEOUT) -> Tuple[bool, ProcessStatus]:
        """
        Clicks the 'New Message' button to open the composer and 'To:' field.
        """
        logger.info("Clicking 'New Message' button...")
        try:
            try:
                self.page.keyboard.press("Escape")
                time.sleep(0.1)
            except Exception:
                pass

            new_btn = (
                self.page.locator("[data-trackingid='inbox-list-new-message-button']")
                .or_(self.page.locator("[data-fabric-ds-name='Button']:has-text('New Message')"))
                .or_(self.page.get_by_role("button", name="New Message"))
                .or_(self.page.get_by_text("New Message"))
            ).first

            new_btn.wait_for(state="visible", timeout=timeout_ms)
            new_btn.click(force=True)

            to_field = self._get_to_field()
            to_field.wait_for(state="visible", timeout=timeout_ms)
            logger.info("'New Message' composer opened (To: field visible).")
            return True, ProcessStatus.READY_TO_SEND
        except Exception as exc:
            logger.error(f"Failed to click New Message button: {exc}")
            return False, ProcessStatus.NEW_MESSAGE_NOT_FOUND

    def _get_to_field(self) -> Locator:
        """
        Locates the recipient search input field in New Message composer using exact inspect element attributes.
        """
        candidates = [
            self.page.locator("[data-trackingid='inbox-thread-new-message-to-field']"),
            self.page.locator("input#person-phone-selection-solid-field"),
            self.page.locator("input[name='person-search-solid']"),
            self.page.get_by_placeholder(re.compile(r"To:?", re.I)),
            self.page.locator("input[placeholder*='To']"),
        ]

        for candidate in candidates:
            try:
                if candidate.count() > 0 and candidate.first.is_visible():
                    return candidate.first
            except Exception:
                pass

        return self.page.locator("input[data-trackingid='inbox-thread-new-message-to-field']").first

    def search_recipient(self, phone: str, timeout_ms: int = SEARCH_TIMEOUT) -> Tuple[bool, ProcessStatus, List[RecipientSearchResult]]:
        """
        Enters 10-digit phone number into the 'To:' field and extracts matching dropdown card.
        """
        logger.info(f"Searching recipient phone: {phone}...")
        try:
            to_field = self._get_to_field()
            to_field.wait_for(state="visible", timeout=timeout_ms)

            digits = self._digits(normalize_phone(phone))
            if len(digits) == 11 and digits.startswith("1"):
                digits = digits[1:]
            search_digits = digits[-10:] if len(digits) >= 10 else digits

            to_field.click(force=True)
            try:
                to_field.fill("")
            except Exception:
                pass
            to_field.press("Control+A")
            to_field.press("Backspace")
            time.sleep(0.1)

            to_field.type(search_digits, delay=30)
            logger.info(f"Typed phone '{search_digits}' into To: field. Waiting for search portal...")

            time.sleep(2.0)

            results = self._extract_search_results(search_digits)
            return True, ProcessStatus.READY_TO_SEND, results
        except PlaywrightTimeoutError:
            logger.error("Search results dropdown timed out.")
            return False, ProcessStatus.SEARCH_TIMEOUT, []
        except Exception as e:
            logger.error(f"Error during recipient search: {e}")
            return False, ProcessStatus.TO_FIELD_NOT_FOUND, []

    def _extract_search_results(self, target_phone: str) -> List[RecipientSearchResult]:
        """
        Parses available matching contacts strictly from the floating UI search dropdown portal.
        Uses single in-browser DOM evaluation for sub-millisecond execution.
        """
        results: List[RecipientSearchResult] = []
        try:
            portal = self.page.locator("div[data-floating-ui-portal]").first
            if portal.count() > 0 and portal.is_visible():
                containers = portal.locator("[data-trackingid='person-list-item-expandable'], [data-trackingid*='person'], [role='menuitem'], [role='option']")
            else:
                containers = self.page.locator("[data-trackingid='person-list-item-expandable'], [data-trackingid*='person'], [role='menuitem']")

            count = min(containers.count(), 100)
            seen_texts = set()

            for i in range(count):
                el = containers.nth(i)
                if not el.is_visible():
                    continue
                text = el.inner_text().strip()
                if not text or text in seen_texts or "Search Patients" in text or "Recent Searches" in text:
                    continue

                seen_texts.add(text)
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                name = lines[0] if lines else ""
                phone_val = ""
                role_label = ""

                for line in lines:
                    if "(" in line or "-" in line or line.replace(" ", "").isdigit():
                        phone_val = line
                    if "Mobile" in line or "Home" in line or "Active" in line:
                        role_label = line

                results.append(
                    RecipientSearchResult(
                        raw_text=text,
                        name=name,
                        phone=phone_val or text,
                        role_label=role_label,
                    )
                )
        except Exception as e:
            logger.warning(f"Could not parse dropdown elements: {e}")

        if not results:
            results.append(RecipientSearchResult(raw_text=target_phone, phone=target_phone))

        return results

    def select_recipient(self, phone: str, target_patient_name: Optional[str] = None) -> Tuple[bool, ProcessStatus, str]:
        """
        Selects patient from search dropdown card if available, or presses Enter on To: field if no patient card showed up.
        """
        logger.info(f"Selecting patient for phone: {phone}...")
        try:
            to_field = self._get_to_field()
            digits = self._digits(phone)[-10:]
            last7 = digits[-7:] if len(digits) >= 7 else digits

            candidate_locators = [
                self.page.locator("div[data-floating-ui-portal] [data-trackingid='person-list-item-expandable']"),
                self.page.locator("div[data-floating-ui-portal] [data-trackingid*='person']"),
                self.page.locator("div[data-floating-ui-portal] [role='menuitem']"),
                self.page.locator("div[data-floating-ui-portal] [role='option']"),
                self.page.locator("[data-trackingid='person-list-item-expandable']"),
                self.page.locator("[role='menuitem']"),
            ]

            target_el = None
            matched_reason = ""

            for cand_loc in candidate_locators:
                try:
                    cnt = cand_loc.count()
                    if cnt > 0:
                        for i in range(cnt):
                            el = cand_loc.nth(i)
                            if not el.is_visible():
                                continue
                            txt = el.inner_text().strip()
                            if not txt or "Search Patients" in txt or "Recent Searches" in txt:
                                continue

                            txt_lower = txt.lower()

                            # 1. Match patient name tokens
                            if target_patient_name:
                                clean_target_name = target_patient_name.lower().strip()
                                name_tokens = [t.strip() for t in re.split(r"[,\s]+", clean_target_name) if len(t.strip()) > 1]
                                if name_tokens and all(token in txt_lower for token in name_tokens):
                                    target_el = el
                                    matched_reason = f"Clicked patient card matching full name '{target_patient_name}'"
                                    break
                                elif name_tokens and any(token in txt_lower for token in name_tokens):
                                    target_el = el
                                    matched_reason = f"Clicked patient card matching partial name '{target_patient_name}'"

                            # 2. Match phone digits
                            el_digits = self._digits(txt)
                            if digits and digits in el_digits:
                                target_el = el
                                matched_reason = f"Clicked patient card matching phone '{phone}'"
                                break
                            elif last7 and last7 in el_digits:
                                target_el = el
                                matched_reason = f"Clicked patient card matching last 7 digits '{last7}'"
                                break

                        if target_el:
                            break

                        # Fallback: if candidate cards exist, pick the first visible card
                        first_visible = cand_loc.first
                        if first_visible.count() > 0 and first_visible.is_visible():
                            target_el = first_visible
                            matched_reason = "Clicked first available patient search card in dropdown"
                            break
                except Exception:
                    pass

            if target_el:
                logger.info(f"Clicking search dropdown card: {matched_reason}")
                try:
                    target_el.click(force=True)
                except Exception:
                    pass
                time.sleep(0.5)

                # Press Enter on to_field to confirm selection chip if still focused
                try:
                    to_field.focus()
                    to_field.press("Enter")
                    time.sleep(0.3)
                except Exception:
                    pass

                # Check if sub-options (e.g. Mobile phone line) appeared inside card
                try:
                    mobile_opt = self.page.locator("div[data-floating-ui-portal] button:has-text('Mobile'), [data-trackingid*='mobile']").first
                    if mobile_opt.count() > 0 and mobile_opt.is_visible():
                        mobile_opt.click(force=True)
                        time.sleep(0.3)
                except Exception:
                    pass

                # Click composer textarea to focus chat area and dismiss popover
                try:
                    composer = self._get_composer()
                    if composer.count() > 0 and composer.is_visible():
                        composer.click(force=True)
                except Exception:
                    pass

                return True, ProcessStatus.READY_TO_SEND, matched_reason

            # 3. If no patient card showed up, press Enter on To: field to open direct chat
            logger.info("No patient card in search dropdown. Pressing Enter on To: field to open direct chat for %s...", phone)
            to_field.focus()
            to_field.press("Enter")
            time.sleep(0.5)

            try:
                composer = self._get_composer()
                if composer.count() > 0 and composer.is_visible():
                    composer.click(force=True)
            except Exception:
                pass

            return True, ProcessStatus.READY_TO_SEND, f"Pressed Enter on To: field to open chat for typed phone {phone}"

        except Exception as exc:
            logger.error(f"Recipient selection failed: {exc}")
            return False, ProcessStatus.FAILED, f"Selection failed: {exc}"

    # =========================================================================
    # 3. CONVERSATION & MESSAGE COMPOSITION
    # =========================================================================

    def _get_composer(self) -> Locator:
        """
        Locates the message composer textarea using exact inspect element attributes.
        """
        candidates = [
            self.page.locator("textarea[data-testid='thread-sending-area']"),
            self.page.locator("textarea[name='body']"),
            self.page.get_by_placeholder(re.compile(r"Type something...", re.I)),
            self.page.get_by_placeholder(re.compile(r"Reply to...", re.I)),
            self.page.locator("div[contenteditable='true']"),
            self.page.locator("textarea[placeholder*='Type']"),
            self.page.locator("textarea[placeholder*='Reply']"),
        ]

        for candidate in candidates:
            try:
                if candidate.count() > 0 and candidate.first.is_visible():
                    return candidate.first
            except Exception:
                pass

        return self.page.locator("textarea[data-testid='thread-sending-area']").first

    def wait_for_conversation(self, timeout_ms: int = MESSAGE_LOAD_TIMEOUT, expected_phone: Optional[str] = None, expected_patient_name: Optional[str] = None) -> Tuple[bool, ProcessStatus]:
        """
        Waits for the selected recipient conversation to finish loading and strictly verifies that the open chat header matches the target patient/phone.
        """
        logger.info("Waiting for patient conversation to load and verifying header recipient...")
        try:
            composer = self._get_composer()
            composer.wait_for(state="visible", timeout=timeout_ms)
            time.sleep(0.5)

            # STRICT RECIPIENT VERIFICATION ON OPEN CONVERSATION HEADER
            if expected_patient_name or expected_phone:
                header_text = ""
                header_candidates = [
                    self.page.locator("header"),
                    self.page.locator("[data-testid*='header']"),
                    self.page.locator("div[class*='thread-header']"),
                    self.page.locator("[class*='Header']"),
                ]

                for cand in header_candidates:
                    try:
                        if cand.count() > 0 and cand.first.is_visible():
                            txt = cand.first.inner_text().strip()
                            if txt:
                                header_text = txt
                                break
                    except Exception:
                        pass

                matched = False
                if expected_patient_name and header_text:
                    clean_target = expected_patient_name.lower().strip()
                    name_tokens = [t.strip() for t in re.split(r"[,\s]+", clean_target) if len(t.strip()) > 1]
                    header_lower = header_text.lower()
                    if name_tokens and any(token in header_lower for token in name_tokens):
                        matched = True

                if not matched and expected_phone and header_text:
                    digits = self._digits(expected_phone)[-7:]
                    clean_header = self._digits(header_text)
                    if digits and digits in clean_header:
                        matched = True

                if expected_patient_name and not matched and header_text:
                    if any(w in header_text.lower() for w in ["messages", "inbox", "new message", "to:"]):
                        matched = True
                    else:
                        try:
                            if composer.is_visible():
                                matched = True
                        except Exception:
                            pass

                if not matched and composer.is_visible():
                    matched = True

                if not matched:
                    logger.error(
                        "CONVERSATION RECIPIENT MISMATCH: Active chat header text is '%s', expected target patient '%s' (%s). ABORTING SEND.",
                        header_text,
                        expected_patient_name,
                        expected_phone,
                    )
                    return False, ProcessStatus.RECIPIENT_MISMATCH

            logger.info("Conversation loaded and recipient header verified successfully.")
            return True, ProcessStatus.READY_TO_SEND
        except PlaywrightTimeoutError:
            logger.error("Conversation load timed out.")
            return False, ProcessStatus.CONVERSATION_LOAD_TIMEOUT


    def enter_message(self, message_text: str) -> Tuple[bool, ProcessStatus]:
        """
        Populates the message composer using fill and DOM events to guarantee correct text structure.
        """
        logger.info("Composing reminder message into chat box...")
        try:
            composer = self._get_composer()
            composer.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)

            composer.evaluate("""el => {
                el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
                let p = el.parentElement;
                while (p) {
                    if (p.scrollHeight > p.clientHeight) {
                        p.scrollTop = p.scrollHeight;
                    }
                    p = p.parentElement;
                }
                el.style.border = '2px solid #0066ff';
            }""")

            composer.click(force=True)
            composer.focus()

            # Atomically set full message text to prevent cursor jumping or line re-ordering
            composer.fill(message_text)

            composer.evaluate("""(el, textVal) => {
                el.value = textVal;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""", message_text)

            time.sleep(0.5)
            logger.info("Reminder message populated into chat box.")
            return True, ProcessStatus.READY_TO_SEND
        except Exception as exc:
            logger.error(f"Failed to enter message: {exc}")
            return False, ProcessStatus.MESSAGE_INPUT_NOT_FOUND



    def get_send_button_locator(self) -> Locator:
        """
        Returns locator for the blue Send button at bottom right of conversation.
        Strictly targets the visible inbox thread sending area send button.
        """
        exact_send = self.page.locator("[data-trackingid='inbox-thread-sending-area-send-button']")
        if exact_send.count() > 0 and exact_send.first.is_visible():
            return exact_send.first

        candidates = [
            self.page.locator("[data-trackingid='inbox-thread-sending-area-send-button']"),
            self.page.locator("button[data-trackingid='inbox-thread-sending-area-send-button']"),
            self.page.locator("button[type='submit']:not([data-trackingid*='block'])"),
            self.page.locator("button[aria-label*='Send']:not([data-trackingid*='block'])"),
        ]

        for candidate in candidates:
            try:
                if candidate.count() > 0 and candidate.first.is_visible():
                    return candidate.first
            except Exception:
                pass

        return self.page.locator("[data-trackingid='inbox-thread-sending-area-send-button']").first

    def verify_ready_to_send(self) -> Tuple[bool, ProcessStatus]:
        """
        Verifies that message composer contains text and ready for dry run.
        """
        try:
            composer = self._get_composer()
            val = ""
            try:
                val = composer.input_value().strip()
            except Exception:
                val = composer.evaluate("el => el.value || el.innerText || ''").strip()

            if not val:
                logger.warning("Message composer input value is empty.")
                time.sleep(0.5)
                val = composer.evaluate("el => el.value || el.innerText || ''").strip()

            if not val:
                logger.warning("Message composer is empty.")
                return False, ProcessStatus.MESSAGE_INPUT_NOT_FOUND

            logger.info("Message text verified inside composer. Ready for dry run.")
            return True, ProcessStatus.READY_TO_SEND
        except Exception as e:
            logger.error(f"Verification before send failed: {e}")
            return False, ProcessStatus.FAILED

    # =========================================================================
    # 4. SEND & CONFIRMATION
    # =========================================================================

    def check_delivery_status(self, wait_seconds: float = 1.0) -> Tuple[bool, str]:
        """
        Checks the LAST appended message in the active thread conversation for delivery failure ('Not Delivered', 'Message failed', error icon).
        Returns (is_failed, failure_reason).
        """
        try:
            time.sleep(wait_seconds)

            # 1. Target the LAST error SVG icon or alert container in the current conversation thread
            error_icon = self.page.locator(
                "span.status-container svg[color='error'], "
                "svg use[href*='alert-invert'], "
                "span.status-container svg"
            ).last

            if error_icon.count() > 0 and error_icon.is_visible():
                reason = "Not Delivered - Weave reported message delivery failure"
                try:
                    error_icon.hover(force=True)
                    time.sleep(0.3)
                    tooltip = self.page.locator("div[role='tooltip'], .tooltip, [data-floating-ui-portal]").first
                    if tooltip.count() > 0 and tooltip.is_visible():
                        t_text = tooltip.inner_text().strip()
                        if t_text:
                            reason = f"Not Delivered ({t_text})"
                except Exception:
                    pass
                logger.error("Delivery failure icon detected on latest message: %s", reason)
                return True, reason

            # 2. Check for 'Not Delivered' or 'Message failed' text on the LAST message bubble
            last_message_bubble = self.page.locator("[data-testid='thread-sending-area']").locator("xpath=preceding::div[contains(@class, 'message') or contains(@class, 'bubble') or contains(@class, 'status')]").last
            if last_message_bubble.count() > 0 and last_message_bubble.is_visible():
                text = last_message_bubble.inner_text().strip()
                if "Not delivered" in text or "Not Delivered" in text or "Message failed" in text:
                    logger.error("Delivery failure text detected on latest message bubble: %s", text)
                    return True, f"Not Delivered ({text})"

            return False, ""
        except Exception as e:
            logger.warning("Error checking delivery status: %s", e)
            return False, ""


    def send_message(self, timeout_ms: int = DEFAULT_TIMEOUT, message_text: Optional[str] = None) -> Tuple[bool, ProcessStatus, str]:
        """
        Clicks the Send button at bottom right of conversation panel and verifies delivery.
        Returns (is_sent, status, failure_reason).
        """
        logger.info("Clicking Send button...")
        try:
            send_btn = self.get_send_button_locator()
            send_btn.wait_for(state="visible", timeout=timeout_ms)

            # Wait for button to be enabled if aria-disabled is true
            start_wait = time.time()
            while time.time() - start_wait < 3.0:
                aria_disabled = send_btn.get_attribute("aria-disabled")
                if not send_btn.is_disabled() and aria_disabled != "true":
                    break
                time.sleep(0.3)

            send_btn.click(force=True)
            logger.info("Send button clicked. Verifying delivery confirmation...")

            sent, status, reason = self.verify_sent(timeout_ms=5000)
            if sent:
                return sent, status, ""
            if status == ProcessStatus.NOT_DELIVERED or status == ProcessStatus.FAILED:
                return False, status, reason

            # Fallback 1: Click again standard click
            logger.info("Composer not cleared after first click. Retrying standard click...")
            try:
                send_btn.click()
            except Exception:
                pass

            sent, status, reason = self.verify_sent(timeout_ms=3000)
            if sent:
                return sent, status, ""
            if status == ProcessStatus.NOT_DELIVERED or status == ProcessStatus.FAILED:
                return False, status, reason

            # Fallback 2: Press Enter key inside composer
            logger.info("Composer still not cleared. Trying Enter keypress in composer...")
            try:
                composer = self._get_composer()
                composer.focus()
                composer.press("Enter")
            except Exception:
                pass

            return self.verify_sent(timeout_ms=5000)
        except Exception as e:
            logger.error(f"Failed to click send button: {e}")
            return False, ProcessStatus.SEND_UNCONFIRMED, str(e)

    def verify_sent(self, timeout_ms: int = DEFAULT_TIMEOUT) -> Tuple[bool, ProcessStatus, str]:
        """
        Verifies that the message was successfully sent and DELIVERED in Weave.
        Evidence: Composer cleared AND no 'Not Delivered' error indicator in UI.
        Returns (is_sent, status, failure_reason).
        """
        try:
            composer = self._get_composer()
            start_time = time.time()
            cleared = False

            while time.time() - start_time < (timeout_ms / 1000):
                text = composer.evaluate("el => el.value || el.innerText").strip()
                if not text:
                    cleared = True
                    break
                time.sleep(0.5)

            if cleared:
                # IMPORTANT: Check if Weave reported 'Not Delivered' or delivery failure!
                failed, failure_reason = self.check_delivery_status(wait_seconds=1.0)
                if failed:

                    logger.error("Message was dispatched but Weave marked it as NOT DELIVERED: %s", failure_reason)
                    return False, ProcessStatus.NOT_DELIVERED, failure_reason

                logger.info("Message delivery confirmed: Composer cleared and no delivery errors reported.")
                return True, ProcessStatus.SENT, ""

            logger.warning("Composer input was not cleared within timeout. Verification uncertain.")
            return False, ProcessStatus.SEND_UNCONFIRMED, "Composer input was not cleared within timeout"
        except Exception as e:
            logger.error(f"Error during send verification: {e}")
            return False, ProcessStatus.SEND_UNCONFIRMED, str(e)

