from pathlib import Path
from typing import Optional, Tuple

from playwright.sync_api import (
    sync_playwright,
    Playwright,
    BrowserContext,
    Page,
)

from config import PROFILE_DIR, HEADLESS, SLOW_MO, DEFAULT_TIMEOUT


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

    def start(self) -> Tuple[BrowserContext, Page]:
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.playwright = sync_playwright().start()

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            slow_mo=self.slow_mo,
            viewport={"width": 1440, "height": 900},
        )

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
