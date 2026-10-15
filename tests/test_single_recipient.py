import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from automation.driver import PrepareFailure, PrepareResult, Recipient
from automation.weave_driver import WeaveDriver
from services.message_template import render_message


@pytest.mark.asyncio
async def test_verify_single_recipient_passes_with_one_recipient():
    driver = WeaveDriver()
    driver._page = MagicMock()
    # Mock header contains target digits
    driver.page.wait_for_function = AsyncMock()
    header_loc = MagicMock()
    header_loc.count = AsyncMock(return_value=1)
    header_loc.inner_text = AsyncMock(return_value="(561) 208-6041")
    header_loc.wait_for = AsyncMock()
    driver.page.locator.return_value = header_loc

    # Mock evaluate returns 1 chip and labelCount = 1
    driver.page.evaluate = AsyncMock(return_value={
        "labelCount": 1,
        "chipCount": 1,
        "chipTexts": ["+15612086041"],
        "removeButtonCount": 1,
        "containerText": "To: 1 +15612086041",
        "headerText": "(561) 208-6041",
    })

    recipient = Recipient("Hemlata Shah", "Hemlata", "Shah", "+15612086041")
    ok, reason = await driver._verify_single_recipient(recipient, "5612086041")
    assert ok is True
    assert "Single recipient verified" in reason


@pytest.mark.asyncio
async def test_verify_single_recipient_passes_in_new_message_view_without_thread_header():
    driver = WeaveDriver()
    driver._page = MagicMock()
    composer_loc = MagicMock()
    composer_loc.wait_for = AsyncMock()
    driver.page.locator.return_value = composer_loc

    # In New Message, headerText is empty, but containerText has the chip with truncated phone
    driver.page.evaluate = AsyncMock(return_value={
        "labelCount": 1,
        "chipCount": 1,
        "chipTexts": ["+156120860..."],
        "removeButtonCount": 1,
        "containerText": "To: 1 +156120860...",
        "headerText": "",
    })

    recipient = Recipient("Hemlata Shah", "Hemlata", "Shah", "+15612086041")
    ok, reason = await driver._verify_single_recipient(recipient, "5612086041")
    assert ok is True
    assert "Single recipient verified" in reason


@pytest.mark.asyncio
async def test_verify_single_recipient_fails_when_multiple_chips_detected():
    driver = WeaveDriver()
    driver._page = MagicMock()
    composer_loc = MagicMock()
    composer_loc.wait_for = AsyncMock()
    driver.page.locator.return_value = composer_loc

    # Mock evaluate returns 2 chips
    driver.page.evaluate = AsyncMock(return_value={
        "labelCount": 2,
        "chipCount": 2,
        "chipTexts": ["+15612086041", "+17725551234"],
        "removeButtonCount": 2,
        "containerText": "To: 1 +15612086041 2 +17725551234",
        "headerText": "",
    })

    recipient = Recipient("Hemlata Shah", "Hemlata", "Shah", "+15612086041")
    ok, reason = await driver._verify_single_recipient(recipient, "5612086041")
    assert ok is False
    assert "strictly 1 recipient allowed" in reason


@pytest.mark.asyncio
async def test_verify_single_recipient_fails_when_group_detected():
    driver = WeaveDriver()
    driver._page = MagicMock()
    composer_loc = MagicMock()
    composer_loc.wait_for = AsyncMock()
    driver.page.locator.return_value = composer_loc

    driver.page.evaluate = AsyncMock(return_value={
        "labelCount": None,
        "chipCount": 1,
        "chipTexts": ["+15612086041"],
        "removeButtonCount": 1,
        "containerText": "To: 1 +15612086041",
        "headerText": "5612086041 and 2 others (Group)",
    })

    recipient = Recipient("Hemlata Shah", "Hemlata", "Shah", "+15612086041")
    ok, reason = await driver._verify_single_recipient(recipient, "5612086041")
    assert ok is False
    assert "group" in reason.lower()


def test_independent_personalization_per_patient():
    template = "Hi {first_name}, you have an appointment on {appointment_date} at {appointment_time} with {business_name}."
    d = date(2026, 10, 9)

    patient_a = {"full_name": "Hemlata Shah", "first_name": "Hemlata", "last_name": "Shah"}
    patient_b = {"full_name": "Rick Roe", "first_name": "Rick", "last_name": "Roe"}

    msg_a = render_message(template, patient=patient_a, appointment_date=d, appointment_time="10:00", provider="", business_name="MD Primary Care")
    msg_b = render_message(template, patient=patient_b, appointment_date=d, appointment_time="16:30", provider="", business_name="MD Primary Care")

    assert "Hemlata" in msg_a and "10:00 AM" in msg_a
    assert "Rick" in msg_b and "4:30 PM" in msg_b
    assert "10:00 AM" not in msg_b
    assert "4:30 PM" not in msg_a
