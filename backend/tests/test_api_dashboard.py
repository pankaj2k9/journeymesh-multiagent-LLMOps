"""The traveller dashboard.

Two things are worth protecting here: that a journey lands on the right shelf,
and that a signed-in traveller can never be shown somebody else's trips because
a session id happened to match.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db.database import session_scope
from app.db.models import Trip

TODAY = date(2027, 1, 15)
PASSWORD = "a-long-enough-passphrase"


def make_trip(
    *,
    session_id: str | None = "browser-1",
    user_id: str | None = None,
    departure: date | None = None,
    ret: date | None = None,
    review_status: str = "approved",
    budget: float | None = 4000.0,
) -> str:
    with session_scope() as session:
        trip = Trip(
            user_query="Dhaka to Barcelona",
            origin="Dhaka",
            destination="Barcelona",
            departure_date=departure,
            return_date=ret,
            travelers=3,
            budget=budget,
            currency="USD",
            session_id=session_id,
            user_id=user_id,
            review_status=review_status,
            status="approved" if review_status == "approved" else "awaiting_review",
        )
        session.add(trip)
        session.flush()
        return trip.id


def headers(session_id: str = "browser-1") -> dict[str, str]:
    return {"X-JourneyMesh-Session": session_id}


def dashboard(client: TestClient, **kwargs) -> dict:
    params = {"today": TODAY.isoformat()}
    params.update(kwargs.pop("params", {}))
    response = client.get("/api/v1/me/dashboard", params=params, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


class TestScope:
    def test_an_anonymous_visitor_sees_their_own_session(self, client: TestClient) -> None:
        make_trip(session_id="browser-1", departure=TODAY + timedelta(days=30))
        payload = dashboard(client, headers=headers("browser-1"))
        assert payload["anonymous"] is True
        assert payload["user"] is None
        assert payload["counts"]["total"] == 1

    def test_another_session_sees_nothing(self, client: TestClient) -> None:
        make_trip(session_id="browser-1", departure=TODAY + timedelta(days=30))
        payload = dashboard(client, headers=headers("browser-2"))
        assert payload["counts"]["total"] == 0

    def test_no_session_and_no_account_returns_an_empty_dashboard(
        self, client: TestClient
    ) -> None:
        make_trip(session_id="browser-1", departure=TODAY + timedelta(days=30))
        payload = dashboard(client)
        assert payload["counts"]["total"] == 0
        assert payload["upcoming"] == []

    def test_a_signed_in_traveller_sees_their_own_trips(self, client: TestClient) -> None:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "owner@example.com", "password": PASSWORD},
        ).json()
        user_id = registered["user"]["id"]
        make_trip(session_id=None, user_id=user_id, departure=TODAY + timedelta(days=10))

        payload = dashboard(
            client, headers={"Authorization": f"Bearer {registered['access_token']}"}
        )
        assert payload["anonymous"] is False
        assert payload["user"]["email"] == "owner@example.com"
        assert payload["counts"]["total"] == 1

    def test_a_signed_in_traveller_never_falls_back_to_the_session(
        self, client: TestClient
    ) -> None:
        """A shared machine must not leak one account's journeys to another."""
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "owner@example.com", "password": PASSWORD},
        ).json()
        # An anonymous trip sits in this browser session; the account has none.
        make_trip(session_id="browser-1", departure=TODAY + timedelta(days=30))

        payload = dashboard(
            client,
            headers={
                "Authorization": f"Bearer {registered['access_token']}",
                "X-JourneyMesh-Session": "browser-1",
            },
        )
        assert payload["counts"]["total"] == 0

    def test_claiming_a_session_moves_the_trips_onto_the_dashboard(
        self, client: TestClient
    ) -> None:
        make_trip(session_id="browser-1", departure=TODAY + timedelta(days=30))
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": "late@example.com",
                "password": PASSWORD,
                "session_id": "browser-1",
            },
        ).json()
        payload = dashboard(
            client, headers={"Authorization": f"Bearer {registered['access_token']}"}
        )
        assert payload["counts"]["total"] == 1


class TestBuckets:
    def test_a_future_approved_trip_is_upcoming(self, client: TestClient) -> None:
        make_trip(departure=TODAY + timedelta(days=30), ret=TODAY + timedelta(days=37))
        payload = dashboard(client, headers=headers())
        assert payload["counts"]["upcoming"] == 1
        assert payload["upcoming"][0]["days_until_departure"] == 30

    def test_a_finished_trip_is_past(self, client: TestClient) -> None:
        make_trip(departure=TODAY - timedelta(days=40), ret=TODAY - timedelta(days=33))
        payload = dashboard(client, headers=headers())
        assert payload["counts"]["past"] == 1
        assert payload["past"][0]["days_until_departure"] == -40

    def test_an_unapproved_trip_is_a_draft(self, client: TestClient) -> None:
        make_trip(
            departure=TODAY + timedelta(days=30), review_status="awaiting_review"
        )
        payload = dashboard(client, headers=headers())
        assert payload["counts"]["drafts"] == 1

    def test_an_unapproved_trip_in_the_past_is_past_not_a_draft(
        self, client: TestClient
    ) -> None:
        """A trip to last March is not work still waiting to be done."""
        make_trip(
            departure=TODAY - timedelta(days=300),
            ret=TODAY - timedelta(days=293),
            review_status="awaiting_review",
        )
        payload = dashboard(client, headers=headers())
        assert payload["counts"]["past"] == 1
        assert payload["counts"]["drafts"] == 0

    def test_a_trip_with_no_dates_is_a_draft_not_an_upcoming_countdown(
        self, client: TestClient
    ) -> None:
        make_trip(departure=None, ret=None, review_status="approved")
        payload = dashboard(client, headers=headers())
        assert payload["counts"]["drafts"] == 1
        assert payload["drafts"][0]["days_until_departure"] is None

    def test_a_trip_departing_today_is_still_upcoming(self, client: TestClient) -> None:
        make_trip(departure=TODAY, ret=TODAY + timedelta(days=5))
        payload = dashboard(client, headers=headers())
        assert payload["counts"]["upcoming"] == 1
        assert payload["upcoming"][0]["days_until_departure"] == 0

    def test_upcoming_is_soonest_first(self, client: TestClient) -> None:
        make_trip(departure=TODAY + timedelta(days=60))
        make_trip(departure=TODAY + timedelta(days=5))
        make_trip(departure=TODAY + timedelta(days=30))
        payload = dashboard(client, headers=headers())
        assert [card["days_until_departure"] for card in payload["upcoming"]] == [5, 30, 60]

    def test_past_is_most_recent_first(self, client: TestClient) -> None:
        make_trip(departure=TODAY - timedelta(days=100), ret=TODAY - timedelta(days=95))
        make_trip(departure=TODAY - timedelta(days=10), ret=TODAY - timedelta(days=5))
        payload = dashboard(client, headers=headers())
        assert [card["days_until_departure"] for card in payload["past"]] == [-10, -100]


class TestBudgetOnTheCard:
    def test_a_trip_with_no_budget_record_reports_its_planning_ceiling(
        self, client: TestClient
    ) -> None:
        make_trip(departure=TODAY + timedelta(days=30), budget=4000.0)
        card = dashboard(client, headers=headers())["upcoming"][0]
        assert card["budget"]["total_budget"] == "4000.00"
        assert card["budget"]["percentage_used"] == 0.0

    def test_money_is_shown_at_the_currencys_precision_everywhere(
        self, client: TestClient
    ) -> None:
        """A card must not leak the four-decimal storage precision."""
        trip_id = make_trip(departure=TODAY + timedelta(days=30))
        client.put(f"/api/v1/trips/{trip_id}/budget", json={"emergency_reserve": "0"})
        make_trip(departure=TODAY + timedelta(days=40), budget=2500.0)

        payload = dashboard(client, headers=headers())
        for card in payload["upcoming"]:
            for field in ("total_budget", "remaining_budget", "allocated_cost"):
                value = card["budget"][field]
                if value is not None:
                    assert len(value.split(".")[-1]) <= 2, f"{field} = {value}"

    def test_a_trip_with_no_budget_at_all_invents_nothing(self, client: TestClient) -> None:
        make_trip(departure=TODAY + timedelta(days=30), budget=None)
        card = dashboard(client, headers=headers())["upcoming"][0]
        assert card["budget"]["total_budget"] is None
        assert card["budget"]["verdict"] == "no_budget_set"

    def test_the_card_matches_the_budget_endpoint(self, client: TestClient) -> None:
        trip_id = make_trip(departure=TODAY + timedelta(days=30))
        client.put(f"/api/v1/trips/{trip_id}/budget", json={"emergency_reserve": "0"})
        client.post(
            f"/api/v1/trips/{trip_id}/budget/expenses",
            json={"category": "FLIGHT", "label": "Flights", "amount": "1840"},
        )

        card = dashboard(client, headers=headers())["upcoming"][0]
        budget = client.get(f"/api/v1/trips/{trip_id}/budget").json()

        assert Decimal(card["budget"]["remaining_budget"]) == Decimal(
            budget["remaining_budget"]
        )
        assert Decimal(card["budget"]["allocated_cost"]) == Decimal(
            budget["allocated_cost"]
        )
        assert card["budget"]["verdict"] == budget["verdict"]

    def test_reading_the_dashboard_does_not_create_budget_rows(
        self, client: TestClient
    ) -> None:
        """A list view must not turn dozens of reads into dozens of writes."""
        from app.db.models import TripBudget

        make_trip(departure=TODAY + timedelta(days=30))
        make_trip(departure=TODAY + timedelta(days=40))
        dashboard(client, headers=headers())

        with session_scope() as session:
            assert session.query(TripBudget).count() == 0


class TestArrangementProgress:
    def _trip_with_search(self, client: TestClient) -> str:
        trip_id = make_trip(departure=date(2027, 6, 10), ret=date(2027, 6, 17))
        return trip_id

    def test_nothing_chosen_is_zero_percent(self, client: TestClient) -> None:
        make_trip(departure=TODAY + timedelta(days=30))
        card = dashboard(client, headers=headers())["upcoming"][0]
        assert card["booking"]["percent"] == 0
        assert card["booking"]["selected_count"] == 0
        assert card["next_item"] is None

    def test_choosing_a_flight_moves_progress_and_sets_the_next_item(
        self, client: TestClient
    ) -> None:
        trip_id = self._trip_with_search(client)
        results = client.post(
            f"/api/v1/trips/{trip_id}/flights/search",
            json={
                "origin": "Dhaka",
                "destination": "Barcelona",
                "departure_date": "2027-06-10",
                "return_date": "2027-06-17",
                "adults": 3,
            },
        ).json()
        offer = results["results"][0]["offer"]
        client.post(
            f"/api/v1/trips/{trip_id}/selections", json={"offer_ref": offer["offer_id"]}
        )

        payload = dashboard(client, headers=headers())
        card = payload["upcoming"][0]
        assert card["booking"]["flight_selected"] is True
        assert card["booking"]["percent"] == 50
        assert card["next_item"]["kind"] == "flight"
        assert card["next_item"]["starts_at"] is not None

    def test_a_selection_is_never_counted_as_a_booking(self, client: TestClient) -> None:
        trip_id = self._trip_with_search(client)
        results = client.post(
            f"/api/v1/trips/{trip_id}/flights/search",
            json={
                "origin": "Dhaka",
                "destination": "Barcelona",
                "departure_date": "2027-06-10",
                "adults": 3,
            },
        ).json()
        client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": results["results"][0]["offer"]["offer_id"]},
        )
        card = dashboard(client, headers=headers())["upcoming"][0]
        assert card["booking"]["selected_count"] == 1
        assert card["booking"]["booked_count"] == 0

    def test_a_flight_and_a_hotel_is_fully_arranged(self, client: TestClient) -> None:
        trip_id = self._trip_with_search(client)
        flights = client.post(
            f"/api/v1/trips/{trip_id}/flights/search",
            json={
                "origin": "Dhaka",
                "destination": "Barcelona",
                "departure_date": "2027-06-10",
                "adults": 3,
            },
        ).json()
        client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": flights["results"][0]["offer"]["offer_id"]},
        )
        hotels = client.post(
            f"/api/v1/trips/{trip_id}/hotels/search",
            json={
                "destination": "Barcelona",
                "check_in": "2027-06-10",
                "check_out": "2027-06-15",
                "adults": 3,
            },
        ).json()
        client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": hotels["results"][0]["offer"]["offer_id"]},
        )

        card = dashboard(client, headers=headers())["upcoming"][0]
        assert card["booking"]["percent"] == 100
        assert card["booking"]["hotel_selected"] is True


class TestShape:
    def test_the_response_carries_the_sections_that_arrive_later(
        self, client: TestClient
    ) -> None:
        payload = dashboard(client, headers=headers())
        assert payload["price_watches"] == []
        assert payload["notifications"] == []
        assert payload["generated_at"] is not None

    def test_the_limit_is_bounded(self, client: TestClient) -> None:
        response = client.get("/api/v1/me/dashboard", params={"limit": 5000})
        assert response.status_code == 422


class TestSessionAttribution:
    """Planning must attribute a journey to the session the caller named.

    The body field and the `X-JourneyMesh-Session` header name the same thing.
    A client that sends only the header - the documented way to group a
    visitor's journeys - used to get trips that belonged to no session and so
    appeared on no dashboard.
    """

    def _plan(self, client: TestClient, body: dict, headers: dict) -> str:
        response = client.post("/api/v1/trips/plan", json=body, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()["trip_id"]

    def test_the_header_alone_is_enough(
        self, client: TestClient, plan_payload: dict
    ) -> None:
        body = dict(plan_payload)
        body.pop("session_id")
        self._plan(client, body, headers("header-only"))

        payload = dashboard(client, headers=headers("header-only"))
        assert payload["counts"]["total"] == 1

    def test_the_body_still_wins_when_both_are_sent(
        self, client: TestClient, plan_payload: dict
    ) -> None:
        body = dict(plan_payload)
        body["session_id"] = "from-body"
        self._plan(client, body, headers("from-header"))

        assert dashboard(client, headers=headers("from-body"))["counts"]["total"] == 1
        assert dashboard(client, headers=headers("from-header"))["counts"]["total"] == 0

    def test_a_journey_planned_with_neither_belongs_to_no_session(
        self, client: TestClient, plan_payload: dict
    ) -> None:
        body = dict(plan_payload)
        body.pop("session_id")
        response = client.post("/api/v1/trips/plan", json=body)
        assert response.status_code == 200
        assert dashboard(client, headers=headers("anything"))["counts"]["total"] == 0
