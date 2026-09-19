"""The places the planner offers as buttons."""

from __future__ import annotations

from app.mcp.aviation import lookup_airport


def _countries(client) -> dict[str, list[dict]]:
    response = client.get("/api/v1/places")
    assert response.status_code == 200
    return {country["name"]: country["cities"] for country in response.json()["countries"]}


def test_lists_countries_with_their_cities(client) -> None:
    countries = _countries(client)
    india = {city["name"]: city["iata"] for city in countries["India"]}
    assert india["Kolkata"] == "CCU"
    assert india["Goa"] == "GOI"
    assert {city["name"] for city in countries["Bangladesh"]} >= {"Dhaka", "Cox's Bazar"}


def test_aliases_are_not_offered_twice(client) -> None:
    names = [city["name"] for city in _countries(client)["India"]]
    assert "New Delhi" not in names and "Bangalore" not in names
    assert len(names) == len(set(names))


def test_every_offered_city_resolves_to_its_airport(client) -> None:
    for cities in _countries(client).values():
        for city in cities:
            record = lookup_airport(city["name"])
            assert record["iata"] == city["iata"], city


def test_is_cacheable(client) -> None:
    assert "max-age" in client.get("/api/v1/places").headers["cache-control"]
