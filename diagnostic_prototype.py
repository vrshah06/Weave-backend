"""
Phase 1 Diagnostic / Selector Prototype
=========================================
Purpose: Verify Weave browser authentication, navigation, and selector strategy
without attempting to compose or send any messages.

Usage:
    python diagnostic_prototype.py
"""

import sys
import time
from src.browser import BrowserManager
from src.weave import WeaveMessenger
from src.logging_utils import setup_logger, mask_phone

logger = setup_logger("diagnostic")


def run_diagnostic(test_phone: str = "7723325189"):
    logger.info("==================================================")
    logger.info("STARTING WEAVE DIAGNOSTIC / SELECTOR PROTOTYPE")
    logger.info("==================================================")

    manager = BrowserManager(headless=False, slow_mo=300)
    try:
        context, page = manager.start()
        weave = WeaveMessenger(page)

        # 1. Open Weave
        weave.navigate_to_weave()

        # 2. Check Authentication
        logger.info("Checking session authentication...")
        is_auth, status = weave.check_authenticated(timeout_ms=10000)

        if not is_auth:
            logger.warning("==================================================")
            logger.warning("WEAVE SESSION EXPIRED OR NOT LOGGED IN.")
            logger.warning("Please log into Weave in the opened browser window.")
            logger.warning("Complete any MFA prompts if required.")
            logger.warning("Waiting for up to 120 seconds for manual login...")
            logger.warning("==================================================")

            # Wait for user manual authentication
            start_wait = time.time()
            while time.time() - start_wait < 120:
                is_auth, _ = weave.check_authenticated(timeout_ms=2000)
                if is_auth:
                    logger.info("Manual login detected! Proceeding with diagnostic...")
                    break
                time.sleep(2)

            if not is_auth:
                logger.error("Authentication check failed after timeout. Please run python main.py --login")
                return

        # 3. Navigate to Messages
        logger.info("Navigating to Messages section...")
        ok_msg, msg_status = weave.open_messages()
        if not ok_msg:
            logger.error(f"Failed to open Messages section: {msg_status}")
            return

        # 4. Click New Message
        logger.info("Clicking 'New Message'...")
        ok_new, new_status = weave.open_new_message()
        if not ok_new:
            logger.error(f"Failed to open New Message: {new_status}")
            return

        # 5. Enter TEST phone number
        masked = mask_phone(test_phone)
        logger.info(f"Entering test phone number ({masked}) into 'To:' field...")
        ok_search, search_status, results = weave.search_recipient(test_phone)

        if not ok_search:
            logger.error(f"Search failed or timed out: {search_status}")
            return

        # 6. Log available matching contacts
        logger.info("==================================================")
        logger.info(f"SEARCH RESULTS RETURNED ({len(results)} found):")
        logger.info("==================================================")

        for idx, res in enumerate(results, 1):
            logger.info(f"Result [{idx}]:")
            logger.info(f"  Name: {res.name or 'N/A'}")
            logger.info(f"  Phone: {res.phone or 'N/A'}")
            logger.info(f"  Label: {res.role_label or 'N/A'}")
            logger.info(f"  Raw: {res.raw_text[:100]}...")

        logger.info("==================================================")
        logger.info("DIAGNOSTIC PROTOTYPE COMPLETE - NO MESSAGES SENT.")
        logger.info("Selectors verified successfully!")
        logger.info("==================================================")

    except Exception as e:
        logger.error(f"Diagnostic encountered error: {e}", exc_info=True)
    finally:
        logger.info("Closing browser context in 5 seconds...")
        time.sleep(5)
        manager.close()


if __name__ == "__main__":
    phone_arg = sys.argv[1] if len(sys.argv) > 1 else "7723325189"
    run_diagnostic(phone_arg)
