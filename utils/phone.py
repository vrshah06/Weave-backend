import re


def normalize_phone(raw: str) -> str:
    """Return the phone number in E.164 form (US numbers default to +1); raise ValueError if invalid."""
    text = (raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("+") and not digits.startswith("1"):
        if 8 <= len(digits) <= 15:
            return f"+{digits}"
        raise ValueError(f"Invalid phone number '{raw}'")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01" or digits[3] in "01":
        raise ValueError(f"Invalid phone number '{raw}'")
    return f"+1{digits}"


def national_number(phone_e164: str) -> str:
    digits = re.sub(r"\D", "", phone_e164)
    return digits[1:] if len(digits) == 11 and digits.startswith("1") else digits


def mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"
