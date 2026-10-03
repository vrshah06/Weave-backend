import sys
import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from playwright.sync_api import (
    sync_playwright,
    Playwright,
    BrowserContext,
    Page,
)

from config import PROFILE_DIR, HEADLESS, SLOW_MO, DEFAULT_TIMEOUT

logger = logging.getLogger("weave_automation")


class BrowserManager:
    """
    Manages a persistent Chromium context.

    Authentication is handled manually in the browser. The persistent
    profile preserves the normal browser session between runs.
    """

    def __init__(
        self,
        profile_dir: Optional[Path] = None,
        headless: bool = HEADLESS,
        slow_mo: int = SLOW_MO,
        default_timeout: int = DEFAULT_TIMEOUT,
    ):
        self.profile_dir = profile_dir or PROFILE_DIR
        self.headless = headless
        self.slow_mo = slow_mo
        self.default_timeout = default_timeout

        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def _ensure_chromium_installed(self):
        try:
            logger.info("Ensuring Playwright Chromium browser binary is installed...")
            res = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
            logger.info(f"Playwright chromium install finished with code {res.returncode}")
        except Exception as e:
            logger.warning(f"Auto-install Chromium attempt failed: {e}")

    def start(self) -> Tuple[BrowserContext, Page]:
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.playwright = sync_playwright().start()

        chromium_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
        ]

        user_agent_str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                slow_mo=self.slow_mo,
                viewport={"width": 1440, "height": 900},
                user_agent=user_agent_str,
                args=chromium_args,
            )
        except Exception as exc:
            logger.warning(f"launch_persistent_context failed: {exc}. Attempting Chromium install and launch fallback...")
            self._ensure_chromium_installed()
            try:
                self.context = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=self.headless,
                    slow_mo=self.slow_mo,
                    viewport={"width": 1440, "height": 900},
                    user_agent=user_agent_str,
                    args=chromium_args,
                )
            except Exception as e2:
                logger.warning(f"Persistent context fallback failed: {e2}. Launching clean browser instance...")
                try:
                    browser = self.playwright.chromium.launch(
                        headless=self.headless,
                        slow_mo=self.slow_mo,
                        args=chromium_args,
                    )
                    self.context = browser.new_context(
                        viewport={"width": 1440, "height": 900},
                        user_agent=user_agent_str,
                    )
                except Exception as e3:
                    logger.error(f"Clean browser launch failed: {e3}. Retrying Chromium install...")
                    self._ensure_chromium_installed()
                    browser = self.playwright.chromium.launch(
                        headless=self.headless,
                        slow_mo=self.slow_mo,
                        args=chromium_args,
                    )
                    self.context = browser.new_context(
                        viewport={"width": 1440, "height": 900},
                        user_agent=user_agent_str,
                    )

        self.context.set_default_timeout(self.default_timeout)

        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        try:
            self.page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception:
            pass

        return self.context, self.page

    def close(self):
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass

        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
