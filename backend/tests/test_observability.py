"""LangSmith integration.

The contract is: optional, sanitised, and never load-bearing. These tests
assert exactly that, without touching the real LangSmith API.
"""

from __future__ import annotations

import pytest

from app.core.config import reload_settings
from app.observability import langsmith
from app.observability.tracing import collected_spans, span, start_trace


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------
def test_tracing_is_off_without_configuration():
    status = langsmith.configure(force=True)
    assert status.enabled is False
    assert status.reason
    assert langsmith.is_enabled() is False


def test_missing_api_key_does_not_crash_the_application(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    reload_settings()
    langsmith.reset()

    status = langsmith.configure(force=True)
    assert status.enabled is False
    assert "API_KEY" in (status.reason or "")

    monkeypatch.undo()
    reload_settings()
    langsmith.reset()


def test_configuration_is_reported_without_revealing_the_key(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    fake_key = "lsv2" + "_pt_" + "not_a_real_key_0123456789"
    monkeypatch.setenv("LANGSMITH_API_KEY", fake_key)
    monkeypatch.setenv("LANGSMITH_PROJECT", "JourneyMesh")
    reload_settings()
    langsmith.reset()

    payload = langsmith.configure(force=True).to_dict()
    assert fake_key not in str(payload)
    assert payload["project"] == "JourneyMesh"

    monkeypatch.undo()
    reload_settings()
    langsmith.reset()


def test_disabled_tracing_forces_the_environment_flags_off(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    reload_settings()
    langsmith.reset()

    langsmith.configure(force=True)
    import os

    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"

    monkeypatch.undo()
    reload_settings()
    langsmith.reset()


# ---------------------------------------------------------------------------
# Metadata safety
# ---------------------------------------------------------------------------
def test_metadata_is_restricted_to_an_allowlist():
    clean = langsmith.sanitize_metadata(
        {
            "trip_id": "trip-1",
            "agent": "hotel_agent",
            "revision_number": 2,
            "selected_agents": ["hotel_agent", "budget_agent"],
            "something_unexpected": "dropped",
        }
    )
    assert clean["trip_id"] == "trip-1"
    assert clean["revision_number"] == 2
    assert "hotel_agent" in clean["selected_agents"]
    assert "something_unexpected" not in clean


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "database_url",
        "groq_api_key",
        "langsmith_api_key",
        "passport",
        "credit_card",
        "password",
        "authorization",
        "user_query",
        "requested_changes",
        "special_requirements",
    ],
)
def test_sensitive_keys_never_reach_a_trace(key):
    assert langsmith.sanitize_metadata({key: "sensitive value"}) == {}


def test_personal_data_inside_an_allowed_value_is_redacted():
    clean = langsmith.sanitize_metadata({"destination": "Dubai, call +8801712345678"})
    assert "8801712345678" not in clean["destination"]


def test_metadata_values_are_truncated():
    clean = langsmith.sanitize_metadata({"reason_code": "x" * 5000})
    assert len(clean["reason_code"]) <= 200


def test_run_config_carries_a_name_tags_and_safe_metadata():
    config = langsmith.run_config(
        name="JourneyMesh Trip Request",
        tags=["journeymesh", "plan"],
        metadata={"trip_id": "t1", "groq_api_key": "gsk_secret"},
        base={"configurable": {"thread_id": "t1"}},
    )
    assert config["run_name"] == "JourneyMesh Trip Request"
    assert config["tags"] == ["journeymesh", "plan"]
    assert config["metadata"] == {"trip_id": "t1"}
    assert config["configurable"] == {"thread_id": "t1"}
    assert "gsk_secret" not in str(config)


# ---------------------------------------------------------------------------
# Spans
# ---------------------------------------------------------------------------
def test_a_span_is_a_no_op_when_tracing_is_off():
    langsmith.reset()
    with langsmith.span("anything", "tool", tool="search_flights") as handle:
        assert handle is None


def _break_the_tracer(monkeypatch) -> None:
    """Enable tracing, then make the SDK fail on every span."""

    def exploding_loader():
        raise RuntimeError("LangSmith is unreachable")

    monkeypatch.setattr(langsmith, "_load_trace", exploding_loader)
    monkeypatch.setattr(langsmith, "is_enabled", lambda: True)


def test_a_failing_tracer_does_not_break_the_body(monkeypatch):
    """The whole point: observability failing must not fail the work."""
    _break_the_tracer(monkeypatch)

    executed = []
    with langsmith.span("agent:hotel_agent", "chain", agent="hotel_agent"):
        executed.append("the body still ran")

    assert executed == ["the body still ran"]
    assert langsmith.status().errors >= 0  # the failure was counted, not raised


def test_an_exception_inside_a_span_is_still_raised(monkeypatch):
    monkeypatch.setattr(langsmith, "is_enabled", lambda: False)
    with pytest.raises(ValueError):
        with langsmith.span("agent:flight_agent"):
            raise ValueError("agent failure")


def test_journeymesh_spans_are_recorded_locally_regardless_of_langsmith():
    start_trace()
    with span("agent:flight_agent", kind="agent", agent="flight_agent"):
        with span("tool:search_flights", kind="tool", tool="search_flights"):
            pass

    names = [item["name"] for item in collected_spans()]
    assert "tool:search_flights" in names
    assert "agent:flight_agent" in names


@pytest.mark.asyncio
async def test_a_journey_completes_while_the_tracer_is_failing(
    monkeypatch, workflow, family_request
):
    _break_the_tracer(monkeypatch)

    state = await workflow.plan(trip_id="trip-tracing", request=family_request)

    assert state["human_review_status"] == "awaiting_review"
    assert state["itinerary_plan"]["days"]
    assert not state["errors"]


# ---------------------------------------------------------------------------
# Trace shape
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_run_is_named_by_phase_and_revision(workflow, family_request):
    state = await workflow.plan(trip_id="trip-naming", request=family_request)

    plan_config = workflow._trace_config(state, "plan")
    assert plan_config["run_name"] == "JourneyMesh Trip Request"
    assert "journeymesh" in plan_config["tags"]

    revised = await workflow.revise(state, requested_changes="Find a cheaper hotel.")
    revision_config = workflow._trace_config(revised, "revise")
    assert revision_config["run_name"] == "JourneyMesh Trip Planning - Revision 2"
    assert "revision:2" in revision_config["tags"]

    metadata = revision_config["metadata"]
    assert metadata["trip_id"] == "trip-naming"
    assert metadata["revision_number"] == 2
    # Selective re-execution is visible from the trace alone.
    assert "hotel_agent" in metadata["selected_agents"]
    assert "flight_agent" not in metadata["selected_agents"]


@pytest.mark.asyncio
async def test_trace_metadata_never_contains_the_user_query(workflow, family_request):
    state = await workflow.plan(trip_id="trip-privacy", request=family_request)
    rendered = str(workflow._trace_config(state, "plan"))
    assert "relaxing 5-day family trip" not in rendered


def test_the_health_endpoint_reports_tracing_status(client):
    payload = client.get("/api/v1/health?verbose=true").json()
    status = payload["checks"]["observability"]["langsmith"]
    assert status["enabled"] is False
    assert "api_key" not in str(status).lower()
