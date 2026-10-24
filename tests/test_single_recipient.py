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


def test_default_template_includes_patient_name():
    from core.config import DEFAULT_MESSAGE_TEMPLATE
    from services.message_template import validate_template, render_sample

    validate_template(DEFAULT_MESSAGE_TEMPLATE)
    d = date(2026, 10, 15)
    patient = {"full_name": "Hemlata Shah", "first_name": "Hemlata", "last_name": "Shah"}
    rendered = render_message(
        DEFAULT_MESSAGE_TEMPLATE,
        patient=patient,
        appointment_date=d,
        appointment_time="14:30",
        provider="Dr. Smith",
        business_name="MD Primary Care",
    )
    assert "This is a friendly reminder that Hemlata Shah has an appointment scheduled on 10/15/2026 at 2:30 PM with MD Primary Care." in rendered
    assert "Reply STOP to unsubscribe." in rendered

    sample = render_sample(DEFAULT_MESSAGE_TEMPLATE, "MD Primary Care")
    assert "This is a friendly reminder that Jane Doe has an appointment scheduled on 10/02/2026 at 9:00 AM with MD Primary Care." in sample


def test_space_tolerant_placeholder_normalization():
    from services.message_template import validate_template

    template = "Reminder for {patient name}: appointment on {appointment date} at {appointment time}."
    validate_template(template)
    patient = {"full_name": "Hemlata Shah", "first_name": "Hemlata", "last_name": "Shah"}
    rendered = render_message(
        template,
        patient=patient,
        appointment_date=date(2026, 10, 15),
        appointment_time="09:00",
        provider="",
        business_name="MD Primary Care",
    )
    assert rendered == "Reminder for Hemlata Shah: appointment on 10/15/2026 at 9:00 AM."


@pytest.mark.asyncio
async def test_undelivered_or_unconfirmed_message_marks_item_failed(monkeypatch):
    from bson import ObjectId
    from automation.driver import SendResult, SendStatus
    from models.enums import AppointmentStatus, RunItemStatus, RunMode
    from worker.run_executor import RunExecutor

    appt_id = ObjectId()
    run_id = ObjectId()
    patient_id = ObjectId()
    appointment = {
        "_id": appt_id,
        "patient": {"_id": patient_id, "full_name": "Jane Doe", "first_name": "Jane", "last_name": "Doe", "phone": "+15551234567"},
        "appointment_time": "09:00",
        "appointment_date": "2026-10-12",
        "provider": "MD Primary Care",
    }
    settings = {
        "message_template": "Hi {first_name}, appointment on {appointment_date} at {appointment_time}.",
        "business_name": "MD Primary Care",
    }

    # Mock appointment_repository
    mock_find_by_id = AsyncMock(return_value={"_id": appt_id, "status": "PENDING", "excluded": False})
    mock_claim = AsyncMock(return_value=True)
    mock_set_status = AsyncMock()
    monkeypatch.setattr("repositories.appointment_repository.find_by_id", mock_find_by_id)
    monkeypatch.setattr("repositories.appointment_repository.claim_for_sending", mock_claim)
    monkeypatch.setattr("repositories.appointment_repository.set_status", mock_set_status)

    mock_driver = MagicMock()
    mock_driver.prepare_message = AsyncMock(return_value=PrepareResult.ready())
    mock_driver.capture_screenshot = AsyncMock(return_value=b"fake-png")
    mock_driver.discard_draft = AsyncMock()

    # Case 1: Driver returns NOT_DELIVERED
    mock_driver.send_prepared_message = AsyncMock(return_value=SendResult(SendStatus.NOT_DELIVERED, "Weave shows Not Delivered"))
    executor = RunExecutor(
        run={"_id": run_id, "mode": RunMode.SEND, "appointment_date": "2026-10-12"},
        driver=mock_driver,
        sending_enabled=True,
        max_consecutive_errors=3,
    )
    status, reason = await executor._attempt(appointment, settings)
    assert status == RunItemStatus.FAILED
    assert "Not Delivered" in reason
    mock_set_status.assert_called_with(appt_id, AppointmentStatus.FAILED, reason, run_id)

    # Case 2: Driver returns UNCONFIRMED
    mock_driver.send_prepared_message = AsyncMock(return_value=SendResult(SendStatus.UNCONFIRMED, "The newest message in the conversation is not this reminder"))
    status, reason = await executor._attempt(appointment, settings)
    assert status == RunItemStatus.FAILED
    assert "not this reminder" in reason
    mock_set_status.assert_called_with(appt_id, AppointmentStatus.FAILED, reason, run_id)

