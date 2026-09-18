"""The budget and preferences endpoints.

Amounts cross this boundary as strings. That is deliberate - see
`app/schemas/money.py` - and one of the tests below is there to keep it that
way, because a well-meant change to a number type would reintroduce float
drift on the one page where it matters most.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.db.database import session_scope
from app.db.models import Trip


def make_trip(budget: float | None = 4000.0, currency: str = "USD") -> str:
    with session_scope() as session:
        trip = Trip(
            user_query="Dhaka to Barcelona for three",
            origin="Dhaka",
            destination="Barcelona",
            travelers=3,
            budget=budget,
            currency=currency,
        )
        session.add(trip)
        session.flush()
        return trip.id


class TestReadBudget:
    def test_a_budget_appears_on_first_read(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.get(f"/api/v1/trips/{trip_id}/budget")
        assert response.status_code == 200

        payload = response.json()
        assert payload["total_budget"] == "4000.00"
        assert payload["remaining_budget"] == "3800.00"  # 5% reserve held back
        assert payload["verdict"] == "within_budget"

    def test_amounts_are_strings_not_json_numbers(self, client: TestClient) -> None:
        trip_id = make_trip()
        payload = client.get(f"/api/v1/trips/{trip_id}/budget").json()
        for field in ("total_budget", "committed_cost", "planned_cost", "allocated_cost"):
            assert isinstance(payload[field], str), f"{field} must not be a JSON number"
        assert isinstance(payload["categories"]["flight_cost"], str)

    def test_an_unknown_trip_is_a_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/trips/not-a-trip/budget")
        assert response.status_code == 404
        assert response.json()["error"] == "trip_not_found"


class TestSetBudget:
    def test_the_ceiling_and_reserve_can_be_changed(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.put(
            f"/api/v1/trips/{trip_id}/budget",
            json={"total_budget": "5000", "emergency_reserve": "250"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_budget"] == "5000.00"
        assert payload["remaining_budget"] == "4750.00"

    def test_an_amount_sent_as_a_number_is_still_accepted(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.put(
            f"/api/v1/trips/{trip_id}/budget",
            json={"total_budget": 5000.50, "emergency_reserve": 0},
        )
        assert response.status_code == 200
        assert response.json()["total_budget"] == "5000.50"

    def test_nonsense_is_rejected(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.put(
            f"/api/v1/trips/{trip_id}/budget", json={"total_budget": "not-money"}
        )
        assert response.status_code == 422


class TestImpact:
    def test_the_flight_card_numbers(self, client: TestClient) -> None:
        trip_id = make_trip()
        client.put(f"/api/v1/trips/{trip_id}/budget", json={"emergency_reserve": "0"})

        response = client.post(
            f"/api/v1/trips/{trip_id}/budget/impact",
            json={
                "amount": "1875",
                "travelers": 3,
                "label": "Turkish Airlines DAC-BCN",
                "source": "LIVE",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["per_traveler"] == "625.00"
        assert payload["item_total"] == "1875.00"
        assert payload["remaining_after"] == "2125.00"
        assert payload["within_budget"] is True
        assert payload["payable"] is True

    def test_a_preview_changes_nothing(self, client: TestClient) -> None:
        trip_id = make_trip()
        client.post(
            f"/api/v1/trips/{trip_id}/budget/impact",
            json={"amount": "1875", "travelers": 3},
        )
        ledger = client.get(f"/api/v1/trips/{trip_id}/budget/ledger").json()
        assert ledger["total"] == 0
        assert ledger["budget"]["allocated_cost"] == "0.00"

    def test_an_over_budget_option_is_reported_not_refused(self, client: TestClient) -> None:
        trip_id = make_trip()
        client.put(f"/api/v1/trips/{trip_id}/budget", json={"emergency_reserve": "0"})
        payload = client.post(
            f"/api/v1/trips/{trip_id}/budget/impact",
            json={"amount": "4500", "travelers": 3},
        ).json()
        assert payload["within_budget"] is False
        assert payload["verdict_after"] == "over_budget"
        assert payload["remaining_after"] == "-500.00"


class TestExpenses:
    def test_adding_an_expense_moves_the_budget(self, client: TestClient) -> None:
        trip_id = make_trip()
        client.put(f"/api/v1/trips/{trip_id}/budget", json={"emergency_reserve": "0"})

        response = client.post(
            f"/api/v1/trips/{trip_id}/budget/expenses",
            json={
                "category": "LOCAL_TRANSPORT",
                "label": "Airport transfer",
                "amount": "64.50",
                "state": "PAID",
            },
        )
        assert response.status_code == 201
        budget = response.json()["budget"]
        assert budget["committed_cost"] == "64.50"
        assert budget["remaining_budget"] == "3935.50"
        assert budget["categories"]["local_transport_cost"] == "64.50"

    def test_a_request_body_cannot_claim_something_is_booked(
        self, client: TestClient
    ) -> None:
        trip_id = make_trip()
        response = client.post(
            f"/api/v1/trips/{trip_id}/budget/expenses",
            json={
                "category": "FLIGHT",
                "label": "Definitely booked",
                "amount": "1800",
                "state": "BOOKED",
            },
        )
        assert response.status_code == 422

    def test_removing_an_expense_appends_a_reversal(self, client: TestClient) -> None:
        trip_id = make_trip()
        client.put(f"/api/v1/trips/{trip_id}/budget", json={"emergency_reserve": "0"})

        created = client.post(
            f"/api/v1/trips/{trip_id}/budget/expenses",
            json={"category": "ACTIVITY", "label": "Museum", "amount": "80"},
        ).json()
        item_id = created["items"][0]["id"]

        removed = client.delete(f"/api/v1/trips/{trip_id}/budget/expenses/{item_id}")
        assert removed.status_code == 200
        assert removed.json()["items"][0]["amount"] == "-80.00"
        assert removed.json()["budget"]["allocated_cost"] == "0.00"

        ledger = client.get(f"/api/v1/trips/{trip_id}/budget/ledger").json()
        assert ledger["total"] == 2, "the original line must survive its reversal"

    def test_reversing_twice_is_a_conflict_not_a_double_refund(
        self, client: TestClient
    ) -> None:
        trip_id = make_trip()
        created = client.post(
            f"/api/v1/trips/{trip_id}/budget/expenses",
            json={"category": "ACTIVITY", "label": "Museum", "amount": "80"},
        ).json()
        item_id = created["items"][0]["id"]

        assert client.delete(f"/api/v1/trips/{trip_id}/budget/expenses/{item_id}").status_code == 200
        second = client.delete(f"/api/v1/trips/{trip_id}/budget/expenses/{item_id}")
        assert second.status_code == 409
        assert second.json()["error"] == "invalid_budget_transition"

    def test_the_ledger_reads_as_a_transaction_history(self, client: TestClient) -> None:
        trip_id = make_trip()
        client.post(
            f"/api/v1/trips/{trip_id}/budget/expenses",
            json={"category": "FLIGHT", "label": "Flight selected", "amount": "1840"},
        )
        created = client.post(
            f"/api/v1/trips/{trip_id}/budget/expenses",
            json={"category": "ACTIVITY", "label": "Museum", "amount": "80"},
        ).json()
        client.delete(
            f"/api/v1/trips/{trip_id}/budget/expenses/{created['items'][0]['id']}"
        )

        lines = client.get(f"/api/v1/trips/{trip_id}/budget/ledger").json()["items"]
        rendered = [(line["label"], line["amount"]) for line in lines]
        assert ("Flight selected", "1840.00") in rendered
        assert ("Museum", "80.00") in rendered
        assert ("Reversal: Museum", "-80.00") in rendered


class TestPreferences:
    def test_a_brief_is_derived_for_a_trip_that_has_none(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.get(f"/api/v1/trips/{trip_id}/preferences")
        assert response.status_code == 200
        payload = response.json()
        assert payload["adults"] == 3
        assert payload["children"] == 0
        assert payload["cabin_class"] == "economy"

    def test_a_brief_can_be_written_and_read_back(self, client: TestClient) -> None:
        trip_id = make_trip()
        brief = {
            "adults": 2,
            "children": 1,
            "child_ages": [6],
            "flexible_days": 3,
            "cabin_class": "premium_economy",
            "max_stops": 1,
            "baggage": "checked",
            "preferred_airlines": ["TK"],
            "excluded_airlines": ["FR"],
            "accommodation_type": "apartment",
            "hotel_min_rating": 4.0,
            "pace": "relaxed",
            "interests": ["food", "history"],
            "dietary_requirements": "one vegetarian",
            "accessibility_requirements": "step-free access",
            "notes": "prefer morning departures",
        }
        written = client.put(f"/api/v1/trips/{trip_id}/preferences", json=brief)
        assert written.status_code == 200
        assert written.json()["travelers_total"] == 3

        read_back = client.get(f"/api/v1/trips/{trip_id}/preferences").json()
        assert read_back["child_ages"] == [6]
        assert read_back["preferred_airlines"] == ["TK"]
        assert read_back["max_stops"] == 1

        with session_scope() as session:
            assert session.get(Trip, trip_id).travelers == 3

    def test_children_without_ages_are_refused(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.put(
            f"/api/v1/trips/{trip_id}/preferences", json={"adults": 2, "children": 1}
        )
        assert response.status_code == 422

    def test_an_airline_cannot_be_preferred_and_excluded(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.put(
            f"/api/v1/trips/{trip_id}/preferences",
            json={"preferred_airlines": ["TK"], "excluded_airlines": ["tk"]},
        )
        assert response.status_code == 422

    def test_planning_persists_the_brief_and_opens_a_budget(
        self, client: TestClient, plan_payload: dict
    ) -> None:
        payload = dict(plan_payload)
        payload.pop("travelers")
        payload["preferences"] = {
            "adults": 2,
            "children": 1,
            "child_ages": [5],
            "cabin_class": "economy",
            "max_stops": 1,
        }
        response = client.post("/api/v1/trips/plan", json=payload)
        assert response.status_code == 200, response.text
        trip_id = response.json()["trip_id"]

        brief = client.get(f"/api/v1/trips/{trip_id}/preferences").json()
        assert brief["children"] == 1 and brief["child_ages"] == [5]
        assert brief["max_stops"] == 1

        budget = client.get(f"/api/v1/trips/{trip_id}/budget").json()
        assert budget["total_budget"] == "3000.00"
        assert Decimal(budget["allocated_cost"]) == Decimal(0)
