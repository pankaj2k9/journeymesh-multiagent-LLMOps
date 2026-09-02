"""Output guardrails."""

from __future__ import annotations

from app.guardrails import output_guard
from app.schemas.travel import TripConstraints


def base_payload():
    return {
        "selected_agents": ["itinerary_agent", "budget_agent"],
        "itinerary": {
            "days": [
                {
                    "day": 1,
                    "slots": [
                        {
                            "slot": "morning",
                            "activities": [{"title": "Museum visit", "estimated_cost": 10}],
                        }
                    ],
                }
            ]
        },
        "budget": {
            "breakdown": {
                "flights": 100,
                "hotels": 200,
                "food": 50,
                "transport": 20,
                "activities": 20,
                "miscellaneous": 10,
            },
            "estimated_total": 400,
        },
    }


def test_a_well_formed_payload_passes():
    decision = output_guard.check_payload(base_payload())
    assert decision.allowed
    assert not decision.failures


# Assembled at runtime so this file contains no credential-shaped literal for a
# secret scanner to trip over, while still exercising the guard's pattern.
FAKE_KEY = "gsk" + "_" + "abcdefghijklmnopqrstuvwx"


def test_a_credential_in_the_output_is_a_failure():
    payload = base_payload()
    payload["itinerary"]["days"][0]["summary"] = f"use {FAKE_KEY} to book"
    decision = output_guard.check_payload(payload)
    assert not decision.allowed
    assert any("credential" in failure for failure in decision.failures)


def test_a_connection_string_in_the_output_is_a_failure():
    payload = base_payload()
    payload["itinerary"]["notes"] = ["postgresql://user:pass@host:5432/db"]
    decision = output_guard.check_payload(payload)
    assert not decision.allowed


def test_script_markup_in_the_output_is_a_failure():
    payload = base_payload()
    payload["itinerary"]["days"][0]["title"] = "<script>alert(1)</script>"
    decision = output_guard.check_payload(payload)
    assert not decision.allowed
    assert any("markup" in failure for failure in decision.failures)


def test_an_unsafe_url_scheme_is_a_failure():
    payload = base_payload()
    payload["itinerary"]["notes"] = ["book at file:///etc/passwd"]
    decision = output_guard.check_payload(payload)
    assert not decision.allowed


def test_a_missing_itinerary_is_a_failure_when_the_agent_ran():
    payload = base_payload()
    payload["itinerary"] = {"days": []}
    decision = output_guard.check_payload(payload)
    assert not decision.allowed
    assert any("no days" in failure for failure in decision.failures)


def test_budget_arithmetic_mismatch_is_a_warning():
    payload = base_payload()
    payload["budget"]["estimated_total"] = 999
    decision = output_guard.check_payload(payload)
    assert decision.allowed
    assert any("does not match" in warning for warning in decision.warnings)


def test_itinerary_length_mismatch_is_a_warning():
    constraints = TripConstraints(destination="Rome", trip_days=4)
    decision = output_guard.check_payload(base_payload(), constraints=constraints)
    assert any("covers 1 days" in warning for warning in decision.warnings)


def test_personal_data_is_redacted_from_the_output():
    payload = base_payload()
    payload["itinerary"]["days"][0]["summary"] = "call the guide on +8801712345678"
    decision = output_guard.check_payload(payload)
    assert "8801712345678" not in str(decision.sanitized)
    assert "phone" in decision.redactions
