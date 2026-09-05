"""The request sentence is usually the only place a constraint is stated."""

from __future__ import annotations

import pytest

from app.agents.query_parser import extract_constraints, places_from_text


@pytest.mark.parametrize(
    ("query", "origin", "destination"),
    [
        ("Plan a complete 7-day India trip from Bangladesh", "Bangladesh", "India"),
        ("Plan a 5-day trip from Dhaka to Singapore", "Dhaka", "Singapore"),
        ("I want to visit Bali, leaving from Kolkata", "Kolkata", "Bali"),
        ("What will the weather be like in Dubai next week?", None, "Dubai"),
        ("A week in Kyoto", None, "Kyoto"),
        ("Plan something nice for the summer", None, None),
    ],
)
def test_places_are_read_from_the_sentence(query, origin, destination):
    assert places_from_text(query) == (origin, destination)


def test_a_place_named_once_is_the_destination_not_the_origin():
    """"Trip to Bangkok" states where to go, and says nothing about leaving."""
    assert places_from_text("Plan a trip to Bangkok") == (None, "Bangkok")


def test_the_same_place_is_never_both_ends_of_a_journey():
    origin, destination = places_from_text("A Dhaka trip from Dhaka")
    assert not (origin and destination and origin == destination)


def test_a_filled_in_field_is_never_overwritten():
    """The form outranks the prose: a typed field is an instruction."""
    updates = extract_constraints(
        "7-day India trip from Bangladesh",
        {"destination": "Nepal", "origin": "Kolkata"},
    )
    assert "destination" not in updates
    assert "origin" not in updates


def test_budget_is_read_with_its_currency():
    updates = extract_constraints("5-day trip to Singapore with a budget of $2000", {})
    assert updates["budget"] == 2000.0
    assert updates["currency"] == "USD"


def test_a_bare_number_is_not_a_budget():
    """"7-day" and "3 people" are not amounts of money."""
    updates = extract_constraints("A 7-day trip to Goa for 3 people", {})
    assert "budget" not in updates
    assert updates["travelers"] == 3


def test_the_word_budget_in_estimated_budget_is_not_a_travel_style():
    """It names an amount to be worked out, not a way of travelling."""
    updates = extract_constraints(
        "Plan a complete 7-day India trip from Bangladesh including an estimated budget",
        {},
    )
    assert updates.get("travel_style") is None


def test_the_most_specific_travel_style_wins():
    updates = extract_constraints("A relaxing family trip to Phuket", {})
    assert updates["travel_style"] == "family"


def test_travellers_are_read_from_several_phrasings():
    assert extract_constraints("A family of 4 going to Dubai", {})["travelers"] == 4
    assert extract_constraints("Honeymoon in Maldives", {})["travelers"] == 2
    assert extract_constraints("Solo trip to Hanoi", {})["travelers"] == 1


def test_interests_come_from_the_supported_vocabulary_only():
    updates = extract_constraints("Trip to Bangkok for street food and beaches", {})
    assert set(updates["interests"]) == {"food", "beaches"}
