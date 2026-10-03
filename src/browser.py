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
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=60,
            )
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
        ]

        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                slow_mo=self.slow_mo,
                viewport={"width": 1440, "height": 900},
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
                    args=chromium_args,
                )
            except Exception as e2:
                logger.warning(f"Persistent context fallback failed: {e2}. Launching clean browser instance...")
                browser = self.playwright.chromium.launch(
                    headless=self.headless,
                    slow_mo=self.slow_mo,
                    args=chromium_args,
                )
                self.context = browser.new_context(viewport={"width": 1440, "height": 900})

        self.context.set_default_timeout(self.default_timeout)

        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

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
