"""PII detection and redaction."""

from __future__ import annotations

from app.guardrails import pii_guard


def test_passport_number_is_redacted():
    result = pii_guard.redact_text("My passport number: A1234567 for the booking")
    assert "A1234567" not in result.text
    assert "passport" in result.categories


def test_credit_card_is_redacted_only_when_it_validates():
    valid = pii_guard.redact_text("card 4111 1111 1111 1111")
    assert "credit_card" in valid.categories
    assert "4111" not in valid.text

    invalid = pii_guard.redact_text("reference 1234 5678 9012 3456")
    assert "credit_card" not in invalid.categories


def test_email_and_phone_are_redacted():
    result = pii_guard.redact_text("write to me at a.traveller@example.com or +8801712345678")
    assert "email" in result.categories
    assert "phone" in result.categories
    assert "example.com" not in result.text


def test_iso_dates_are_not_mistaken_for_phone_numbers():
    assert pii_guard.detect("departing 2027-01-10 and returning 2027-01-14") == []


def test_ordinary_travel_text_is_left_alone():
    text = "Plan a 5-day family trip from Dhaka to Singapore with a budget of $3000"
    result = pii_guard.redact_text(text)
    assert result.text == text
    assert result.categories == []


def test_payload_redaction_is_recursive():
    payload = {
        "traveller": {"passport": "passport number: X9876543"},
        "notes": ["call +8801712345678"],
    }
    cleaned, categories = pii_guard.sanitize_payload(payload)
    assert "X9876543" not in str(cleaned)
    assert set(categories) >= {"passport", "phone"}


def test_travel_document_mentions_are_flagged():
    assert pii_guard.mentions_travel_documents("I will send my passport number later")
    assert not pii_guard.mentions_travel_documents("I like beaches")


def test_a_request_containing_pii_is_redacted_before_planning(client, plan_payload):
    plan_payload["query"] += " My passport number: A1234567."
    response = client.post("/api/v1/trips/plan", json=plan_payload)
    assert response.status_code == 200
    assert "A1234567" not in response.text
