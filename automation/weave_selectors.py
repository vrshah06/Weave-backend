# Verified against app.getweave.com (Messages) on 2026-10-04.
# Pop-ups Weave can show at any time that block clicks (the softphone asks for microphone access).
BLOCKING_DIALOG_TEXT = "Microphone Access"

SIGNED_IN_MARKER = "[data-trackingid='nav-location-picker-button']"
LOGIN_FIELDS = "input[type='email'], input[name='username'], input[autocomplete='username'], input[type='password']"
LOGIN_EMAIL = "input[type='email'], input[name='username'], input[autocomplete='username']"
LOGIN_PASSWORD = "input[type='password']"
LOGIN_SUBMIT = "button[type='submit']"

NEW_MESSAGE_BUTTON = "[data-trackingid='inbox-list-new-message-button']"
TO_FIELD_CONTAINER = "[data-trackingid='inbox-thread-new-message-to-field'], #multi-recipient-selection-field"
TO_FIELD = "[data-trackingid='inbox-thread-new-message-to-field'] input, #multi-recipient-selection-field input, input[name='person-search']"
PERSON_RESULT = "[data-trackingid='person-phone-menu-item']"
SEARCH_RESULT = "menu[role='menu'] button[role='menuitem']"
NO_CONTACTS_TEXT = "No contacts found"


def contact_phone_option(national_digits: str) -> str:
    """A saved contact's phone line; Weave ends the option id with the 10-digit number."""
    return f"{PERSON_RESULT} li[role='option'][id$='-{national_digits}']"


def format_us_phone(national_digits: str) -> str:
    return f"({national_digits[:3]}) {national_digits[3:6]}-{national_digits[6:]}"


# Selectors for recipient chips and single-recipient validation in New Message
RECIPIENT_CHIP = "[data-fabric-ds-name='Chip'], [data-trackingid*='recipient-chip'], [data-trackingid*='chip'], [data-testid*='chip']"
CHIP_REMOVE_BUTTON = "button[aria-label*='remove' i], button[aria-label*='delete' i], button[aria-label*='close' i], [data-trackingid*='remove']"
TO_FIELD_CLEAR_BUTTON = "[data-trackingid='inbox-thread-new-message-to-field-clear'], [data-trackingid*='to-field'] button, [data-testid*='clear']"
RECIPIENT_COUNT_INDICATOR = "text=/\\b\\d+\\s+recipients?\\b/i"


THREAD_HEADER = "[data-testid='inbox-thread-header']"
COMPOSER = "textarea[data-testid='thread-sending-area'], textarea[name='body'], textarea[placeholder*='Type something']"
SEND_BUTTON = "[data-trackingid='inbox-thread-send-button']"
SEND_BUTTON_ENABLED = "[data-trackingid='inbox-thread-send-button'][aria-disabled='false']"
THREAD_ITEM = "[data-trackingid^='inbox-thread-thread-item-']"

# Weave autosaves composer text as a draft (PUT) and deletes it when the composer is emptied (DELETE).
DRAFT_API_PATH = "/sms/draft/v1/draft"
