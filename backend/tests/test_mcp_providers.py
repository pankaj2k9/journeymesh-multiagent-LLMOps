"""MCP configuration, credential redaction and provider isolation.

These tests exercise configuration and adapter logic, not live third parties.
Where a real MCP server is started it is JourneyMesh's own weather server,
which runs offline; Tavily and AviationStack are asserted at the configuration
and adapter level only, because reaching them needs credentials this suite
does not have and must never contain.
"""

from __future__ import annotations

import shutil
import sys

import pytest

from app.core.config import reload_settings
from app.mcp import config as mcp_config
from app.mcp.providers import adapter_for
from app.mcp.security import redact_text, redact_url, safe_error


# ---------------------------------------------------------------------------
# Redaction. The Tavily endpoint carries the API key as a query parameter, so
# the URL itself is a credential and everything that touches it must mask it.
# ---------------------------------------------------------------------------
def test_a_credential_query_parameter_is_masked():
    url = "https://mcp.tavily.com/mcp/?tavilyApiKey=super-secret-value"
    masked = redact_url(url)
    assert "super-secret-value" not in masked
    assert "tavilyApiKey=***" in masked
    # The part that is useful for debugging survives.
    assert "mcp.tavily.com" in masked


@pytest.mark.parametrize(
    "param",
    ["apiKey", "api_key", "token", "access_token", "secret", "password", "authToken"],
)
def test_every_credential_shaped_parameter_is_masked(param):
    masked = redact_url(f"https://example.test/mcp?{param}=leaked-value&page=2")
    assert "leaked-value" not in masked
    # A parameter that is not a credential is left alone, so a redacted URL
    # is still useful.
    assert "page=2" in masked


def test_userinfo_credentials_are_masked():
    masked = redact_url("https://user:hunter2@example.test/mcp")
    assert "hunter2" not in masked


def test_a_url_inside_an_error_message_is_masked():
    message = (
        "ConnectError: failed to reach "
        "https://mcp.tavily.com/mcp/?tavilyApiKey=super-secret-value"
    )
    assert "super-secret-value" not in redact_text(message)


def test_a_bare_key_in_free_text_is_masked():
    assert "gsk_" not in redact_text("groq said gsk_" + "A" * 40).replace("gsk_[", "")


def test_safe_error_keeps_the_type_and_drops_the_secret():
    exc = RuntimeError("auth failed for https://mcp.tavily.com/mcp/?tavilyApiKey=abc123456789")
    detail = safe_error(exc)
    assert detail.startswith("RuntimeError")
    assert "abc123456789" not in detail


# ---------------------------------------------------------------------------
# Weather: the one server that is always available, because we ship it.
# ---------------------------------------------------------------------------
def test_weather_defaults_to_a_local_stdio_server(monkeypatch):
    monkeypatch.delenv("MCP_WEATHER_TRANSPORT", raising=False)
    reload_settings()
    weather = mcp_config.server_configs()["weather"]

    assert weather.transport == "stdio"
    assert weather.enabled is True
    # The running interpreter and a module path - never a machine-specific
    # absolute path, so the same configuration works on a Mac and in Docker.
    assert weather.command == sys.executable
    assert weather.args == ("-m", mcp_config.WEATHER_SERVER_MODULE)
    monkeypatch.undo()
    reload_settings()


def test_the_weather_server_module_exists_where_the_config_points():
    assert mcp_config.WEATHER_SERVER_PATH.is_file()


def test_the_openweather_key_reaches_the_weather_subprocess(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "unit-test-key")
    reload_settings()
    from app.mcp.client import stdio_child_environment

    weather = mcp_config.server_configs()["weather"]
    env = stdio_child_environment(weather)

    assert env.get("OPENWEATHER_API_KEY") == "unit-test-key"
    monkeypatch.undo()
    reload_settings()


def test_the_subprocess_never_receives_unrelated_secrets(monkeypatch):
    """A weather server has no business seeing the database or the tracer."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@db/journeymesh")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_should_not_travel")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_should_not_travel")
    reload_settings()
    from app.mcp.client import stdio_child_environment

    env = stdio_child_environment(mcp_config.server_configs()["weather"])

    assert "DATABASE_URL" not in env
    assert "LANGSMITH_API_KEY" not in env
    assert "GROQ_API_KEY" not in env
    monkeypatch.undo()
    reload_settings()


def test_weather_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("MCP_WEATHER_TRANSPORT", "disabled")
    reload_settings()
    weather = mcp_config.server_configs()["weather"]
    assert weather.transport == "disabled"
    assert weather.enabled is False
    monkeypatch.undo()
    reload_settings()


# ---------------------------------------------------------------------------
# Search: hosted, and the URL is a credential.
# ---------------------------------------------------------------------------
def test_search_is_enabled_by_a_tavily_key_alone(monkeypatch):
    """One secret, one variable. No pasting a key into a URL."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-unit-test-key")
    monkeypatch.delenv("MCP_SEARCH_URL", raising=False)
    reload_settings()

    search = mcp_config.server_configs()["search"]
    assert search.transport == "streamable_http"
    assert search.enabled is True
    assert "mcp.tavily.com" in (search.url or "")
    assert "tvly-unit-test-key" in (search.url or "")
    monkeypatch.undo()
    reload_settings()


def test_the_tavily_key_never_leaves_through_a_status_payload(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-unit-test-key")
    reload_settings()

    described = mcp_config.server_configs()["search"].describe()
    assert "tvly-unit-test-key" not in repr(described)
    assert described["url_configured"] is True
    assert "***" in (described["url"] or "")
    monkeypatch.undo()
    reload_settings()


def test_search_degrades_when_no_key_is_configured(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("MCP_SEARCH_URL", raising=False)
    reload_settings()

    search = mcp_config.server_configs()["search"]
    assert search.enabled is False
    # And it says why, so "my search is deterministic" has an answer.
    assert "TAVILY_API_KEY" in (search.unavailable_reason or "")
    monkeypatch.undo()
    reload_settings()


def test_the_search_adapter_maps_onto_tavilys_tool():
    adapter = adapter_for("search")
    call = adapter.to_remote("web_search", {"query": "hotels in Lisbon", "max_results": 3})

    assert call is not None
    assert call.tool == "tavily_search"
    assert call.arguments == {"query": "hotels in Lisbon", "max_results": 3}


def test_the_search_adapter_reshapes_a_tavily_response():
    adapter = adapter_for("search")
    shaped = adapter.from_remote(
        "web_search",
        {"results": [{"title": "A hotel", "url": "https://x.test", "content": "text", "score": 0.9}]},
        {"query": "hotels in Lisbon"},
    )

    assert shaped["source"] == "SEARCH_DERIVED"
    assert shaped["results"][0]["snippet"] == "text"


def test_an_uninterpretable_search_response_is_declined():
    """Declining routes to the in-process adapter instead of inventing data."""
    adapter = adapter_for("search")
    assert adapter.from_remote("web_search", {"unexpected": True}, {"query": "x"}) is None


# ---------------------------------------------------------------------------
# Aviation: a third-party server, launched as a subprocess.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "variable", ["AVIATIONSTACK_API_KEY", "AVIATION_STACK_API_KEY"]
)
def test_either_aviation_key_spelling_is_accepted(monkeypatch, variable):
    monkeypatch.delenv("AVIATIONSTACK_API_KEY", raising=False)
    monkeypatch.delenv("AVIATION_STACK_API_KEY", raising=False)
    monkeypatch.setenv(variable, "unit-test-key")
    reload_settings()

    from app.core.config import get_settings

    assert get_settings().aviation_api_key == "unit-test-key"
    monkeypatch.undo()
    reload_settings()


def test_the_aviation_subprocess_receives_both_spellings(monkeypatch):
    """The package reads one name; this application accepts two."""
    monkeypatch.setenv("AVIATIONSTACK_API_KEY", "unit-test-key")
    reload_settings()
    from app.mcp.client import stdio_child_environment

    aviation = mcp_config.server_configs()["aviation"]
    if not aviation.enabled:
        pytest.skip("the AviationStack MCP server is not installed in this environment")

    env = stdio_child_environment(aviation)
    assert env["AVIATION_STACK_API_KEY"] == "unit-test-key"
    assert env["AVIATIONSTACK_API_KEY"] == "unit-test-key"
    monkeypatch.undo()
    reload_settings()


def test_aviation_degrades_when_the_launcher_is_missing(monkeypatch):
    """A host without uv must not produce a startup error or a broken tool."""
    monkeypatch.setenv("AVIATIONSTACK_API_KEY", "unit-test-key")
    monkeypatch.setattr(shutil, "which", lambda _cmd: None)
    reload_settings()

    aviation = mcp_config.server_configs()["aviation"]
    assert aviation.enabled is False
    assert "is on PATH" in (aviation.unavailable_reason or "")
    monkeypatch.undo()
    reload_settings()


def test_aviation_degrades_when_no_key_is_configured(monkeypatch):
    monkeypatch.delenv("AVIATIONSTACK_API_KEY", raising=False)
    monkeypatch.delenv("AVIATION_STACK_API_KEY", raising=False)
    reload_settings()

    aviation = mcp_config.server_configs()["aviation"]
    assert aviation.enabled is False
    assert "API_KEY" in (aviation.unavailable_reason or "")
    monkeypatch.undo()
    reload_settings()


def test_the_aviation_adapter_declines_flight_pricing():
    """AviationStack's route endpoint has no fares; inventing one is worse."""
    adapter = adapter_for("aviation")
    assert adapter.to_remote("search_flights", {"origin": "LIS", "destination": "CDG"}) is None


def test_the_aviation_adapter_resolves_an_airport_from_the_catalogue():
    adapter = adapter_for("aviation")
    call = adapter.to_remote("lookup_airport", {"city": "Lisbon"})
    assert call is not None
    assert call.tool == "list_airports"

    shaped = adapter.from_remote(
        "lookup_airport",
        {"data": [{"city_name": "Lisbon", "iata_code": "LIS", "airport_name": "Humberto Delgado", "country_name": "Portugal"}]},
        {"city": "Lisbon"},
    )
    assert shaped["iata"] == "LIS"
    assert shaped["confidence"] == 1.0
    assert shaped["source"] == "LIVE"


def test_an_unmatched_city_is_reported_as_unavailable_not_guessed():
    adapter = adapter_for("aviation")
    shaped = adapter.from_remote(
        "lookup_airport", {"data": []}, {"city": "Nowhereville"}
    )
    assert shaped["iata"] is None
    assert shaped["source"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Isolation. The property the whole layer is built around.
# ---------------------------------------------------------------------------
def test_an_unknown_transport_disables_one_server_and_no_other(monkeypatch):
    monkeypatch.setenv("MCP_WEATHER_TRANSPORT", "carrier-pigeon")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-unit-test-key")
    reload_settings()

    servers = mcp_config.server_configs()
    assert servers["weather"].enabled is False
    assert servers["search"].enabled is True
    monkeypatch.undo()
    reload_settings()


@pytest.mark.asyncio
async def test_one_failing_server_does_not_break_the_probe_of_the_others(monkeypatch):
    """A broken weather server must not hide the state of search or aviation."""
    from app.mcp import lifecycle

    async def explode(server):
        raise RuntimeError("stdio server died")

    real_list_tools = lifecycle.list_tools

    async def selective(server):
        if server.name == "weather":
            return await explode(server)
        return ["a_tool"]

    monkeypatch.setattr(lifecycle, "list_tools", selective)
    monkeypatch.delenv("MCP_WEATHER_TRANSPORT", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-unit-test-key")
    reload_settings()

    report = await lifecycle.probe_all()

    assert report["weather"]["reachable"] is False
    assert "stdio server died" in report["weather"]["error"]
    assert report["search"]["reachable"] is True
    monkeypatch.setattr(lifecycle, "list_tools", real_list_tools)
    monkeypatch.undo()
    reload_settings()
