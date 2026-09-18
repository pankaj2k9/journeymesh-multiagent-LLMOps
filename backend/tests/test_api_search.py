"""Search and selection over HTTP.

The integration this file protects is the one between search and money: what a
result card promises ("$2,164 remaining after selection") must be exactly what
the budget says once the traveller selects it. Those are two different code
paths reaching the same engine, and they are easy to let drift apart.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db.database import session_scope
from app.db.models import Offer, SearchRun, SelectedOffer, Trip

DEPART = "2027-06-10"
RETURN = "2027-06-17"


def make_trip(budget: float | None = 4000.0) -> str:
    with session_scope() as session:
        trip = Trip(
            user_query="Dhaka to Barcelona for three",
            origin="Dhaka",
            destination="Barcelona",
            travelers=3,
            budget=budget,
            currency="USD",
        )
        session.add(trip)
        session.flush()
        return trip.id


def flight_body(**overrides) -> dict:
    body = {
        "origin": "Dhaka",
        "destination": "Barcelona",
        "departure_date": DEPART,
        "return_date": RETURN,
        "adults": 2,
        "children": 1,
        "child_ages": [7],
        "baggage": "checked",
    }
    body.update(overrides)
    return body


def hotel_body(**overrides) -> dict:
    body = {
        "destination": "Barcelona",
        "check_in": DEPART,
        "check_out": "2027-06-15",
        "adults": 2,
        "children": 1,
        "child_ages": [7],
    }
    body.update(overrides)
    return body


def search(client: TestClient, trip_id: str, sort: str = "cheapest") -> dict:
    response = client.post(
        f"/api/v1/trips/{trip_id}/flights/search?sort={sort}", json=flight_body()
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestFlightSearch:
    def test_a_search_returns_ranked_results(self, client: TestClient) -> None:
        trip_id = make_trip()
        payload = search(client, trip_id)

        assert payload["total"] > 0
        assert payload["search_id"]
        assert payload["sort"] == "cheapest"
        assert len(payload["results"]) == payload["total"]

    def test_results_are_cheapest_first_by_total(self, client: TestClient) -> None:
        payload = search(client, make_trip())
        totals = [Decimal(item["offer"]["total_price"]) for item in payload["results"]]
        assert totals == sorted(totals)
        assert "CHEAPEST" in payload["results"][0]["badges"]

    def test_every_offer_says_where_it_came_from(self, client: TestClient) -> None:
        payload = search(client, make_trip())
        for item in payload["results"]:
            assert item["offer"]["meta"]["source"] == "MOCK"
            assert item["offer"]["meta"]["provider"] == "mock_flights"

    def test_the_response_says_the_prices_are_not_real(self, client: TestClient) -> None:
        payload = search(client, make_trip())
        assert any("MOCK" in note for note in payload["notes"])
        assert payload["providers"][0]["provider"] == "mock_flights"

    def test_each_card_carries_its_budget_consequence(self, client: TestClient) -> None:
        payload = search(client, make_trip())
        for item in payload["results"]:
            budget = item["budget"]
            assert budget is not None
            assert budget["total_budget"] == "4000.00"
            assert budget["remaining_after"] is not None
            assert budget["percentage_of_budget"] is not None
            assert budget["within_budget"] in (True, False)

    def test_a_search_without_a_trip_has_no_budget_context(self, client: TestClient) -> None:
        response = client.post("/api/v1/flights/search", json=flight_body())
        assert response.status_code == 200
        assert all(item["budget"] is None for item in response.json()["results"])

    def test_every_sort_mode_is_accepted(self, client: TestClient) -> None:
        trip_id = make_trip()
        for mode in ("cheapest", "best_value", "fastest", "fewest_stops", "recommended"):
            assert search(client, trip_id, sort=mode)["sort"] == mode

    def test_a_sort_that_does_not_apply_is_refused(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.post(
            f"/api/v1/trips/{trip_id}/flights/search?sort=distance", json=flight_body()
        )
        assert response.status_code == 422

    def test_max_stops_reaches_the_provider(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.post(
            f"/api/v1/trips/{trip_id}/flights/search", json=flight_body(max_stops=0)
        )
        assert all(item["offer"]["stops"] == 0 for item in response.json()["results"])

    def test_an_invalid_search_is_rejected_before_any_provider_is_called(
        self, client: TestClient
    ) -> None:
        trip_id = make_trip()
        response = client.post(
            f"/api/v1/trips/{trip_id}/flights/search",
            json=flight_body(origin="Dhaka", destination="Dhaka"),
        )
        assert response.status_code == 422

    def test_children_without_ages_are_refused(self, client: TestClient) -> None:
        trip_id = make_trip()
        body = flight_body()
        body.pop("child_ages")
        response = client.post(f"/api/v1/trips/{trip_id}/flights/search", json=body)
        assert response.status_code == 422

    def test_an_unknown_trip_is_a_404(self, client: TestClient) -> None:
        response = client.post("/api/v1/trips/nope/flights/search", json=flight_body())
        assert response.status_code == 404

    def test_the_search_and_its_offers_are_persisted(self, client: TestClient) -> None:
        trip_id = make_trip()
        payload = search(client, trip_id)
        with session_scope() as session:
            run = session.get(SearchRun, payload["search_id"])
            assert run is not None
            assert run.kind == "flight"
            assert run.result_count == payload["total"]
            assert run.trip_id == trip_id
            offers = session.query(Offer).filter_by(search_id=run.id).all()
            assert len(offers) == payload["total"]


class TestHotelSearch:
    def test_hotels_are_ordered_by_total_stay(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.post(
            f"/api/v1/trips/{trip_id}/hotels/search", json=hotel_body()
        )
        assert response.status_code == 200
        payload = response.json()
        totals = [Decimal(item["offer"]["total_stay"]) for item in payload["results"]]
        assert totals == sorted(totals)

    def test_a_stay_total_exceeds_nightly_times_nights(self, client: TestClient) -> None:
        trip_id = make_trip()
        payload = client.post(
            f"/api/v1/trips/{trip_id}/hotels/search", json=hotel_body()
        ).json()
        for item in payload["results"]:
            offer = item["offer"]
            naive = Decimal(offer["price_per_night"]) * offer["nights"]
            assert Decimal(offer["total_stay"]) > naive

    def test_hotel_sorts(self, client: TestClient) -> None:
        trip_id = make_trip()
        for mode in ("cheapest", "best_value", "rating", "distance", "recommended"):
            response = client.post(
                f"/api/v1/trips/{trip_id}/hotels/search?sort={mode}", json=hotel_body()
            )
            assert response.status_code == 200, mode

    def test_check_out_must_follow_check_in(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.post(
            f"/api/v1/trips/{trip_id}/hotels/search",
            json=hotel_body(check_in=DEPART, check_out=DEPART),
        )
        assert response.status_code == 422


class TestActivitySearch:
    def test_activities_are_returned_and_priced_for_the_party(
        self, client: TestClient
    ) -> None:
        trip_id = make_trip()
        response = client.post(
            f"/api/v1/trips/{trip_id}/activities/search",
            json={"destination": "Barcelona", "participants": 3},
        )
        assert response.status_code == 200
        for item in response.json()["results"]:
            offer = item["offer"]
            assert Decimal(offer["total_price"]) == Decimal(offer["price_per_person"]) * 3


class TestNaturalLanguageSearch:
    def test_a_sentence_is_parsed_but_not_executed_by_default(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/flights/search/natural",
            json={
                "query": (
                    "cheapest flights from Dhaka to Rome for two adults and one child "
                    "around June 10, flexible by three days, under $2,000 total, "
                    "maximum one stop"
                ),
                "today": "2026-09-18",
            },
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["results"] is None, "nothing runs until the traveller confirms"
        criteria = payload["criteria"]
        assert criteria["origin"] == "Dhaka"
        assert criteria["destination"] == "Rome"
        assert criteria["adults"] == 2 and criteria["children"] == 1
        assert criteria["max_stops"] == 1
        assert criteria["flexible_days"] == 3
        assert payload["assumptions"]

    def test_it_can_run_the_search_in_the_same_call(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/flights/search/natural",
            json={
                "query": "flights from Dhaka to Barcelona on June 10, non-stop",
                "today": "2026-09-18",
                "execute": True,
            },
        )
        payload = response.json()
        assert payload["results"] is not None
        assert payload["results"]["total"] > 0
        assert all(item["offer"]["stops"] == 0 for item in payload["results"]["results"])

    def test_an_incomplete_sentence_reports_what_it_needs(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/flights/search/natural",
            json={"query": "somewhere warm", "today": "2026-09-18"},
        )
        payload = response.json()
        assert payload["criteria"] is None
        assert "origin" in payload["missing"]


class TestSelection:
    def _search_and_pick(self, client: TestClient, trip_id: str, index: int = 0) -> dict:
        payload = search(client, trip_id)
        return payload["results"][index]

    def test_the_promise_on_the_card_is_what_selecting_delivers(
        self, client: TestClient
    ) -> None:
        """The integration this whole file exists for."""
        trip_id = make_trip()
        client.put(f"/api/v1/trips/{trip_id}/budget", json={"emergency_reserve": "0"})

        card = self._search_and_pick(client, trip_id)
        promised = card["budget"]["remaining_after"]

        response = client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": card["offer"]["offer_id"]},
        )
        assert response.status_code == 201
        assert response.json()["budget"]["remaining_budget"] == promised

    def test_selecting_charges_the_flight_category(self, client: TestClient) -> None:
        trip_id = make_trip()
        card = self._search_and_pick(client, trip_id)
        response = client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": card["offer"]["offer_id"]},
        )
        budget = response.json()["budget"]
        assert budget["categories"]["flight_cost"] == card["offer"]["total_price"]
        assert budget["planned_cost"] == card["offer"]["total_price"]
        assert budget["committed_cost"] == "0.00", "a MOCK price is never committed"

    def test_choosing_a_second_flight_replaces_the_first(self, client: TestClient) -> None:
        trip_id = make_trip()
        client.put(f"/api/v1/trips/{trip_id}/budget", json={"emergency_reserve": "0"})
        payload = search(client, trip_id)
        first, second = payload["results"][0], payload["results"][1]

        client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": first["offer"]["offer_id"]},
        )
        response = client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": second["offer"]["offer_id"]},
        )
        budget = response.json()["budget"]

        # The second price, not the sum of both.
        assert budget["categories"]["flight_cost"] == second["offer"]["total_price"]

        listed = client.get(f"/api/v1/trips/{trip_id}/selections").json()
        assert listed["total"] == 1
        assert listed["items"][0]["offer_ref"] == second["offer"]["offer_id"]

    def test_the_superseded_selection_is_kept_not_deleted(self, client: TestClient) -> None:
        trip_id = make_trip()
        payload = search(client, trip_id)
        for card in payload["results"][:2]:
            client.post(
                f"/api/v1/trips/{trip_id}/selections",
                json={"offer_ref": card["offer"]["offer_id"]},
            )
        with session_scope() as session:
            rows = session.query(SelectedOffer).filter_by(trip_id=trip_id).all()
            assert len(rows) == 2
            assert {row.status for row in rows} == {"SELECTED", "SUPERSEDED"}

    def test_a_hotel_and_a_flight_coexist(self, client: TestClient) -> None:
        trip_id = make_trip()
        client.put(f"/api/v1/trips/{trip_id}/budget", json={"emergency_reserve": "0"})

        flight_card = self._search_and_pick(client, trip_id)
        client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": flight_card["offer"]["offer_id"]},
        )
        hotels = client.post(
            f"/api/v1/trips/{trip_id}/hotels/search", json=hotel_body()
        ).json()
        hotel_card = hotels["results"][0]
        response = client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": hotel_card["offer"]["offer_id"]},
        )
        budget = response.json()["budget"]

        assert budget["categories"]["flight_cost"] == flight_card["offer"]["total_price"]
        assert (
            budget["categories"]["accommodation_cost"]
            == hotel_card["offer"]["total_stay"]
        )
        assert client.get(f"/api/v1/trips/{trip_id}/selections").json()["total"] == 2

    def test_unselecting_gives_the_money_back(self, client: TestClient) -> None:
        trip_id = make_trip()
        client.put(f"/api/v1/trips/{trip_id}/budget", json={"emergency_reserve": "0"})
        before = client.get(f"/api/v1/trips/{trip_id}/budget").json()["remaining_budget"]

        card = self._search_and_pick(client, trip_id)
        created = client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": card["offer"]["offer_id"]},
        ).json()

        response = client.delete(
            f"/api/v1/trips/{trip_id}/selections/{created['selection']['id']}"
        )
        assert response.status_code == 200
        assert response.json()["budget"]["remaining_budget"] == before
        assert response.json()["total"] == 0

    def test_unselecting_leaves_an_audit_trail(self, client: TestClient) -> None:
        trip_id = make_trip()
        card = self._search_and_pick(client, trip_id)
        created = client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": card["offer"]["offer_id"]},
        ).json()
        client.delete(f"/api/v1/trips/{trip_id}/selections/{created['selection']['id']}")

        ledger = client.get(f"/api/v1/trips/{trip_id}/budget/ledger").json()
        assert ledger["total"] == 2
        assert any(line["reverses_id"] for line in ledger["items"])

    def test_an_unknown_offer_cannot_be_selected(self, client: TestClient) -> None:
        trip_id = make_trip()
        response = client.post(
            f"/api/v1/trips/{trip_id}/selections", json={"offer_ref": "made-up"}
        )
        assert response.status_code == 404
        assert response.json()["error"] == "offer_not_found"

    def test_an_expired_offer_cannot_be_selected(self, client: TestClient) -> None:
        """A stale quote must never quietly become a commitment."""
        trip_id = make_trip()
        card = self._search_and_pick(client, trip_id)
        offer_ref = card["offer"]["offer_id"]

        with session_scope() as session:
            row = session.query(Offer).filter_by(offer_ref=offer_ref).one()
            row.expires_at = row.retrieved_at - timedelta(minutes=5)

        response = client.post(
            f"/api/v1/trips/{trip_id}/selections", json={"offer_ref": offer_ref}
        )
        assert response.status_code == 409
        assert response.json()["error"] == "offer_expired"

    def test_removing_the_same_selection_twice_is_refused(self, client: TestClient) -> None:
        trip_id = make_trip()
        card = self._search_and_pick(client, trip_id)
        created = client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": card["offer"]["offer_id"]},
        ).json()
        path = f"/api/v1/trips/{trip_id}/selections/{created['selection']['id']}"

        assert client.delete(path).status_code == 200
        assert client.delete(path).status_code == 404


class TestBudgetInteraction:
    def test_an_over_budget_option_is_shown_and_labelled(self, client: TestClient) -> None:
        trip_id = make_trip(budget=200.0)
        payload = search(client, trip_id)
        assert payload["total"] > 0, "expensive options are never hidden"
        assert all("OVER_BUDGET" in item["badges"] for item in payload["results"])
        assert all(item["budget"]["within_budget"] is False for item in payload["results"])

    def test_a_trip_with_no_budget_shows_cards_without_invented_numbers(
        self, client: TestClient
    ) -> None:
        trip_id = make_trip(budget=None)
        payload = search(client, trip_id)
        for item in payload["results"]:
            assert item["budget"]["total_budget"] is None
            assert item["budget"]["remaining_after"] is None
            assert item["budget"]["within_budget"] is None
            assert "WITHIN_BUDGET" not in item["badges"]
            assert "OVER_BUDGET" not in item["badges"]

    def test_the_percentage_matches_the_amount(self, client: TestClient) -> None:
        trip_id = make_trip(budget=4000.0)
        payload = search(client, trip_id)
        for item in payload["results"]:
            total = Decimal(item["offer"]["total_price"])
            expected = float(round(total / Decimal(4000) * 100, 1))
            assert abs(item["budget"]["percentage_of_budget"] - expected) < 0.11

    def test_a_search_after_a_selection_nets_out_the_previous_choice(
        self, client: TestClient
    ) -> None:
        trip_id = make_trip()
        client.put(f"/api/v1/trips/{trip_id}/budget", json={"emergency_reserve": "0"})
        first = search(client, trip_id)["results"][0]
        client.post(
            f"/api/v1/trips/{trip_id}/selections",
            json={"offer_ref": first["offer"]["offer_id"]},
        )

        # Searching again: each card must price as a replacement, not an addition.
        again = search(client, trip_id)
        for item in again["results"]:
            expected = Decimal("4000") - Decimal(item["offer"]["total_price"])
            assert Decimal(item["budget"]["remaining_after"]) == expected


class TestProviderFailure:
    def test_a_failing_provider_degrades_to_the_offline_one_and_says_so(
        self, client: TestClient, monkeypatch
    ) -> None:
        from app.providers import registry

        class BrokenProvider:
            name = "broken_flights"

            async def search_flights(self, criteria):  # noqa: ANN001
                raise RuntimeError("upstream is down")

        monkeypatch.setattr(registry, "flight_provider", lambda: BrokenProvider())

        trip_id = make_trip()
        payload = search(client, trip_id)

        assert payload["total"] > 0, "one provider's outage does not empty the page"
        assert payload["providers"][0]["provider"] == "mock_flights"
        assert "did not respond" in (payload["providers"][0]["message"] or "")
        assert any("offline" in note for note in payload["notes"])

    def test_the_circuit_opens_after_repeated_failure(
        self, client: TestClient, monkeypatch
    ) -> None:
        from app.providers import circuit, registry

        class BrokenProvider:
            name = "broken_flights"
            calls = 0

            async def search_flights(self, criteria):  # noqa: ANN001
                BrokenProvider.calls += 1
                raise RuntimeError("upstream is down")

        provider = BrokenProvider()
        monkeypatch.setattr(registry, "flight_provider", lambda: provider)

        trip_id = make_trip()
        for _ in range(6):
            search(client, trip_id)

        breaker = circuit.breaker_for("broken_flights")
        assert breaker.state == "open"
        assert breaker.health() == "DOWN"
        # Once open, the provider stops being called at all.
        assert BrokenProvider.calls < 6
