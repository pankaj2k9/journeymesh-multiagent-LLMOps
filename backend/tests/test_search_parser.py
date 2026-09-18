"""Reading a search out of a sentence.

The security-relevant test in this file is the last class: a model is never
allowed to supply an amount. A fabricated budget ceiling silently removes real
options from a real search, and the traveller has no way to tell.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.agents import search_parser
from app.agents.search_parser import ASSUMED_CHILD_AGE, parse, parse_deterministic

TODAY = date(2026, 9, 18)

SPEC_EXAMPLE = (
    "Find the cheapest flights from Dhaka to Rome for two adults and one child "
    "around June 10, flexible by three days, under $2,000 total, maximum one stop."
)


class TestTheSpecificationExample:
    async def test_every_stated_constraint_is_captured(self) -> None:
        parsed = await parse(SPEC_EXAMPLE, today=TODAY, allow_model=False)
        assert parsed.complete

        criteria = parsed.criteria
        assert criteria.origin == "Dhaka"
        assert criteria.destination == "Rome"
        assert criteria.departure_date == date(2027, 6, 10)
        assert criteria.adults == 2
        assert criteria.children == 1
        assert criteria.flexible_days == 3
        assert criteria.max_stops == 1
        assert criteria.max_total_price == Decimal("2000")
        assert criteria.currency == "USD"
        assert criteria.travelers == 3

    async def test_the_guessed_child_age_is_declared_not_hidden(self) -> None:
        parsed = await parse(SPEC_EXAMPLE, today=TODAY, allow_model=False)
        assert parsed.criteria.child_ages == [ASSUMED_CHILD_AGE]
        assert any("child age" in note for note in parsed.assumptions)


class TestParty:
    @pytest.mark.parametrize(
        "text,adults,children",
        [
            ("from Dhaka to Rome on June 10 for two adults", 2, 0),
            ("from Dhaka to Rome on June 10 for 3 adults and 2 children", 3, 2),
            ("from Dhaka to Rome on June 10 for one adult and one kid", 1, 1),
            ("from Dhaka to Rome on June 10", 1, 0),
        ],
    )
    async def test_party_sizes(self, text: str, adults: int, children: int) -> None:
        parsed = await parse(text, today=TODAY, allow_model=False)
        assert parsed.criteria.adults == adults
        assert parsed.criteria.children == children

    async def test_stated_child_ages_are_used_verbatim(self) -> None:
        parsed = await parse(
            "from Dhaka to Rome on June 10 for 2 adults and 2 children aged 4 and 9",
            today=TODAY,
            allow_model=False,
        )
        assert parsed.criteria.child_ages == [4, 9]
        assert not any("child age" in note for note in parsed.assumptions)


class TestDates:
    async def test_a_month_and_day_in_the_past_means_next_year(self) -> None:
        parsed = await parse("Dhaka to Rome on June 10", today=TODAY, allow_model=False)
        assert parsed.criteria.departure_date == date(2027, 6, 10)

    async def test_a_month_and_day_still_ahead_stays_this_year(self) -> None:
        parsed = await parse("Dhaka to Rome on December 2", today=TODAY, allow_model=False)
        assert parsed.criteria.departure_date == date(2026, 12, 2)

    async def test_iso_dates_are_understood(self) -> None:
        parsed = await parse(
            "Dhaka to Rome 2027-03-04 returning 2027-03-11", today=TODAY, allow_model=False
        )
        assert parsed.criteria.departure_date == date(2027, 3, 4)
        assert parsed.criteria.return_date == date(2027, 3, 11)

    async def test_day_before_month_works_too(self) -> None:
        parsed = await parse("Dhaka to Rome on 14 July", today=TODAY, allow_model=False)
        assert parsed.criteria.departure_date == date(2027, 7, 14)

    async def test_around_a_date_is_read_as_flexibility_and_declared(self) -> None:
        parsed = await parse("Dhaka to Rome around June 10", today=TODAY, allow_model=False)
        assert parsed.criteria.flexible_days == 2
        assert any("flexible" in note for note in parsed.assumptions)


class TestConstraints:
    async def test_non_stop(self) -> None:
        parsed = await parse("non-stop Dhaka to Rome on June 10", today=TODAY, allow_model=False)
        assert parsed.criteria.max_stops == 0

    async def test_maximum_stops_in_words(self) -> None:
        parsed = await parse(
            "Dhaka to Rome on June 10, no more than two stops", today=TODAY, allow_model=False
        )
        assert parsed.criteria.max_stops == 2

    @pytest.mark.parametrize(
        "text,cabin",
        [
            ("business class Dhaka to Rome on June 10", "business"),
            ("first class Dhaka to Rome on June 10", "first"),
            ("premium economy Dhaka to Rome on June 10", "premium_economy"),
            ("Dhaka to Rome on June 10", "economy"),
        ],
    )
    async def test_cabin(self, text: str, cabin: str) -> None:
        parsed = await parse(text, today=TODAY, allow_model=False)
        assert parsed.criteria.cabin_class == cabin

    async def test_a_checked_bag_is_understood(self) -> None:
        parsed = await parse(
            "Dhaka to Rome on June 10 with a checked bag", today=TODAY, allow_model=False
        )
        assert parsed.criteria.baggage == "checked"

    async def test_an_airline_to_avoid_becomes_an_exclusion(self) -> None:
        parsed = await parse(
            "Dhaka to Rome on June 10, avoid Ryanair", today=TODAY, allow_model=False
        )
        assert parsed.criteria.excluded_airlines == ["FR"]

    async def test_a_morning_departure_becomes_a_time_window(self) -> None:
        parsed = await parse(
            "Dhaka to Rome on June 10, morning departure", today=TODAY, allow_model=False
        )
        assert parsed.criteria.earliest_departure_hour == 5
        assert parsed.criteria.latest_departure_hour == 11

    async def test_flexible_days_are_capped(self) -> None:
        parsed = await parse(
            "Dhaka to Rome on June 10, flexible by 30 days", today=TODAY, allow_model=False
        )
        assert parsed.criteria.flexible_days <= 7


class TestIncompleteRequests:
    async def test_a_request_with_no_origin_says_what_is_missing(self) -> None:
        parsed = await parse("flights to Barcelona", today=TODAY, allow_model=False)
        assert not parsed.complete
        assert "origin" in parsed.missing
        assert "departure_date" in parsed.missing

    async def test_a_partial_parse_still_reports_what_it_understood(self) -> None:
        parsed = await parse("flights to Barcelona", today=TODAY, allow_model=False)
        assert parsed.fields.get("destination") == "Barcelona"

    async def test_nonsense_does_not_raise(self) -> None:
        parsed = await parse("asdfghjkl", today=TODAY, allow_model=False)
        assert not parsed.complete


class TestMoneyIsNeverInvented:
    """A model may read places and dates. It may never produce an amount."""

    async def test_no_budget_stated_means_no_ceiling(self) -> None:
        parsed = await parse(
            "cheapest flights from Dhaka to Rome on June 10", today=TODAY, allow_model=False
        )
        assert parsed.criteria.max_total_price is None

    async def test_a_stated_amount_comes_from_the_text(self) -> None:
        fields = parse_deterministic(
            "Dhaka to Rome on June 10 under 1500 euros", today=TODAY
        )
        assert fields["max_total_price"] == 1500.0
        assert fields["currency"] == "EUR"

    async def test_a_duration_is_not_mistaken_for_a_budget(self) -> None:
        fields = parse_deterministic("Dhaka to Rome on June 10 for 7 days", today=TODAY)
        assert "max_total_price" not in fields

    async def test_an_amount_offered_by_the_model_is_discarded(self, monkeypatch) -> None:
        """The model is asked for places and dates. It gets to supply only those."""

        async def fabricating_model(text: str, needed: list[str]) -> dict:
            return {
                "origin": "Dhaka",
                "departure_date": date(2027, 6, 10),
                # Everything below is a fabrication and must not survive.
                "max_total_price": 999.0,
                "currency": "JPY",
                "max_stops": 0,
                "excluded_airlines": ["TK"],
            }

        monkeypatch.setattr(search_parser, "_model_fill", fabricating_model)

        parsed = await parse("a trip to Rome", today=TODAY, allow_model=True)
        assert parsed.complete
        assert parsed.criteria.max_total_price is None, "a model must not set a budget"
        assert parsed.criteria.currency == "USD"
        assert parsed.criteria.max_stops is None
        assert parsed.criteria.excluded_airlines == []
        assert parsed.used_model is True
        assert any("model was used" in note for note in parsed.assumptions)

    async def test_the_model_is_not_consulted_when_patterns_suffice(self, monkeypatch) -> None:
        called = {"value": False}

        async def should_not_run(text: str, needed: list[str]) -> dict:
            called["value"] = True
            return {}

        monkeypatch.setattr(search_parser, "_model_fill", should_not_run)
        await parse(SPEC_EXAMPLE, today=TODAY, allow_model=True)
        assert called["value"] is False
