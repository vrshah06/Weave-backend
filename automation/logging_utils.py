import re
import logging
from pathlib import Path
from typing import Optional
from core.config import LOG_DIR, APPLICATION_LOG_PATH, SCREENSHOT_DIR, SCREENSHOT_ON_ERROR


def mask_phone(phone_str: str) -> str:
    digits = re.sub(r"\D", "", str(phone_str))
    if len(digits) >= 4:
        return "*" * (len(digits) - 4) + digits[-4:]
    return "****"


def setup_logger(name: str = "weave_automation") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(APPLICATION_LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    import sys
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def capture_screenshot(page, name_prefix: str, row_index: Optional[int] = None) -> Optional[Path]:
    if not SCREENSHOT_ON_ERROR or not page:
        return None

    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        clean_prefix = re.sub(r"[^\w\-]", "_", name_prefix)
        row_str = f"row_{row_index:03d}_" if row_index is not None else ""
        filename = f"{row_str}{clean_prefix}.png"
        filepath = SCREENSHOT_DIR / filename

        page.screenshot(path=str(filepath), full_page=False)
        return filepath
    except Exception as e:
        logging.getLogger("weave_automation").warning(f"Failed to capture screenshot: {e}")
        return None
