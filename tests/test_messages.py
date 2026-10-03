from src.messages import generate_message, hash_message


def test_generate_message():
    msg = generate_message(
        patient_name="James Laterra",
        appointment_date="09/21/2026",
        appointment_time="10:00 AM",
        business_name="MD Primary Care Inc.",
    )
    assert "09/21/2026" in msg
    assert "10:00 AM" in msg
    assert "MD Primary Care Inc." in msg
    assert "Reply STOP to unsubscribe." in msg


def test_hash_message():
    msg1 = "Hello James, your appointment is at 10:00 AM."
    msg2 = "Hello James, your appointment is at 10:00 AM."
    msg3 = "Hello James, your appointment is at 11:00 AM."

    h1 = hash_message(msg1)
    h2 = hash_message(msg2)
    h3 = hash_message(msg3)

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64
