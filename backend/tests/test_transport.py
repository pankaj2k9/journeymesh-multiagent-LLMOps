"""Getting there by any mode: the route planner and its place in a plan."""

from __future__ import annotations

import pytest

from app.transport.planner import plan_route


def _modes(plan) -> list[str]:
    return [option.main_mode for option in plan.options]


def _chosen(plan):
    assert plan.recommended is not None
    return plan.recommended


# ---- which options exist ---------------------------------------------------------


def test_a_short_domestic_route_offers_every_ground_mode() -> None:
    plan = plan_route("Dhaka", "Chittagong")
    assert set(_modes(plan)) == {"flight", "train", "bus", "car"}
    assert plan.source == "ESTIMATE"


def test_a_place_without_an_airport_is_reached_by_flying_to_its_gateway() -> None:
    plan = plan_route("Dhaka", "Bandarban")
    flight = next(o for o in plan.options if o.main_mode == "flight")
    assert [leg.mode for leg in flight.legs][0] == "flight"
    assert flight.legs[0].to_place == "Chittagong"
    assert flight.legs[-1].to_place == "Bandarban"
    assert flight.legs[-1].mode in {"bus", "car"}


def test_an_island_ends_with_a_ferry_whatever_the_main_mode() -> None:
    plan = plan_route("Dhaka", "Saint Martin's Island", travelers=2)
    assert plan.options
    for option in plan.options:
        assert option.legs[-1].mode == "ferry"
        assert option.legs[-2].to_place == "Teknaf"


def test_the_train_stops_where_the_railway_does() -> None:
    plan = plan_route("Dhaka", "Bandarban")
    train = next(o for o in plan.options if o.main_mode == "train")
    assert train.legs[0].to_place == "Chittagong"
    assert train.legs[1].to_place == "Bandarban"


def test_fly_only_and_no_rail_places() -> None:
    assert _modes(plan_route("Kolkata", "Port Blair")) == ["flight"]
    assert "train" not in _modes(plan_route("Delhi", "Leh"))


def test_local_modes_follow_the_country() -> None:
    bd = plan_route("Sreemangal", "Sylhet")  # about 95 km: bus or car
    assert "cng" not in _modes(bd)
    from app.transport.planner import _local_mode

    assert _local_mode("Bangladesh") == "cng"
    assert _local_mode("India") == "auto_rickshaw"
    assert _local_mode("Japan") == "taxi"


def test_no_ground_route_across_the_sea() -> None:
    assert _modes(plan_route("Dhaka", "London")) == ["flight"]


# ---- auto versus a chosen mode ----------------------------------------------------


def test_auto_prefers_the_ground_for_a_short_trip_and_the_air_for_a_long_one() -> None:
    assert _chosen(plan_route("Dhaka", "Chittagong")).main_mode in {"train", "bus"}
    assert _chosen(plan_route("Kolkata", "Goa")).main_mode == "flight"


@pytest.mark.parametrize("mode", ["flight", "train", "bus", "car"])
def test_a_chosen_mode_is_the_one_costed(mode: str) -> None:
    plan = plan_route("Dhaka", "Chittagong", preference=mode)
    assert _chosen(plan).main_mode == mode
    assert "Your choice" in (_chosen(plan).reason or "")


def test_an_impossible_choice_explains_itself_and_falls_back() -> None:
    plan = plan_route("Kolkata", "Port Blair", preference="bus")
    assert _chosen(plan).main_mode == "flight"
    assert any("not practical" in note for note in plan.notes)


def test_a_car_is_shared_and_a_big_party_needs_two() -> None:
    three = plan_route("Delhi", "Agra", travelers=3, preference="car")
    five = plan_route("Delhi", "Agra", travelers=5, preference="car")
    car3, car5 = _chosen(three).legs[0], _chosen(five).legs[0]
    assert car3.vehicles == 1 and car5.vehicles == 2
    assert car5.cost_for_group == pytest.approx(car3.cost_for_group * 2)


def test_a_return_journey_costs_both_ways() -> None:
    one_way = _chosen(plan_route("Dhaka", "Sylhet", preference="bus"))
    both = _chosen(plan_route("Dhaka", "Sylhet", preference="bus", round_trip=True))
    assert both.trip_total_for_group == pytest.approx(one_way.one_way_for_group * 2)


def test_an_unknown_place_is_said_so_rather_than_guessed() -> None:
    plan = plan_route("Dhaka", "Atlantis")
    assert plan.options == []
    assert "not in Travel Crew AI's map" in plan.notes[0]


# ---- in a real plan ---------------------------------------------------------------


def test_a_chosen_mode_reaches_the_plan_and_the_budget(client) -> None:
    response = client.post(
        "/api/v1/trips/plan",
        json={
            "query": "Plan a 3 day trip from Dhaka to Chittagong by bus",
            "origin": "Dhaka",
            "destination": "Chittagong",
            "departure_date": "2027-03-01",
            "return_date": "2027-03-04",
            "travelers": 2,
            "currency": "USD",
            # The budget agent runs when there is a budget to check against.
            "budget": 500,
            "transport_mode": "bus",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    plan = body["flights"]["route_plan"]
    chosen = plan["options"][plan["recommended_index"]]
    assert chosen["main_mode"] == "bus"
    assert plan["round_trip"] is True

    line = body["budget"]["line_provenance"]["flights"]
    assert line["basis"].startswith("Bus to Chittagong")
    assert line["amount"] == pytest.approx(chosen["trip_total_for_group"])


def test_an_unknown_transport_mode_is_refused(client) -> None:
    response = client.post(
        "/api/v1/trips/plan",
        json={"query": "Plan a trip to Goa from Delhi", "transport_mode": "teleport"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("sentence", "mode"),
    [
        ("Plan a trip from Dhaka to Sylhet by train", "train"),
        ("Dhaka to Cox's Bazar by bus for 3 friends", "bus"),
        ("A road trip from Delhi to Jaipur", "car"),
        ("Fly from Kolkata to Goa for a week", "flight"),
        ("Plan 4 days in Goa", None),
        ("Beach stays in Goa, a short drive to the fort", None),
        ("Fly fishing and hiking in Leh", None),
    ],
)
def test_a_mode_in_the_sentence_is_understood(sentence: str, mode: str | None) -> None:
    from app.agents.query_parser import _transport_from_text

    assert _transport_from_text(sentence) == mode


def test_flying_is_offered_for_a_short_hop_when_it_is_the_only_way_in() -> None:
    plan = plan_route("Kathmandu", "Lukla")
    assert _modes(plan) == ["flight"]


def test_mountain_roads_take_longer_than_plains_roads() -> None:
    hills = _chosen(plan_route("Kathmandu", "Pokhara", preference="bus")).legs[0]
    # About the same straight-line distance, on the plains.
    plains = _chosen(plan_route("Delhi", "Agra", preference="bus")).legs[0]
    assert hills.distance_km / hills.duration_hours <= plains.distance_km / plains.duration_hours
    assert _chosen(plan_route("Dhaka", "Paro")).main_mode == "flight"
