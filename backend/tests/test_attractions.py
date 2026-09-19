"""Tourist attractions: the bundled data, the seed and the endpoint."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.db.database import session_scope
from app.db.models import Attraction
from app.db.seed import SEED_DATA, seed_attractions

RECORDS = json.loads((SEED_DATA / "attractions.json").read_text(encoding="utf-8"))


def _by_slug(*slugs: str) -> list[dict]:
    wanted = [r for r in RECORDS if r["slug"] in slugs]
    assert len(wanted) == len(slugs)
    return wanted


# ---- the bundled data ----------------------------------------------------------


def test_every_attraction_belongs_to_a_city_the_planner_offers(client) -> None:
    places = client.get("/api/v1/places").json()["countries"]
    offered = {(c["name"], city["name"]) for c in places for city in c["cities"]}
    strays = [r["slug"] for r in RECORDS if (r["country"], r["city"]) not in offered]
    assert strays == []


def test_every_attraction_has_its_photo_and_its_credit() -> None:
    assert len({r["slug"] for r in RECORDS}) == len(RECORDS)
    for record in RECORDS:
        image = record["image"]
        assert (SEED_DATA / "attractions" / image["file"]).is_file(), record["slug"]
        assert image["author"] and image["license"] and image["source_url"], record["slug"]


def test_bangladesh_is_covered_in_depth() -> None:
    cities = {r["city"] for r in RECORDS if r["country"] == "Bangladesh"}
    assert {"Bandarban", "Sylhet", "Saint Martin's Island", "Cox's Bazar"} <= cities


# ---- the seed --------------------------------------------------------------------


def test_seeds_rows_and_photos_once(client) -> None:
    records = _by_slug("taj-mahal", "burj-khalifa")
    assert seed_attractions(records) == {"created": 2, "images": 2}
    assert seed_attractions(records) == {"created": 0, "images": 0}

    with session_scope() as session:
        rows = session.scalars(select(Attraction)).unique().all()
        assert len(rows) == 2
        assert all(row.image_media_id for row in rows)


def test_logs_what_it_seeded(client, caplog) -> None:
    # A reserved LogRecord key in `extra` raises only when INFO is enabled,
    # which the suite's ERROR level would otherwise hide.
    caplog.set_level("INFO", logger="journeymesh.db.seed")
    assert seed_attractions(_by_slug("taj-mahal"))["created"] == 1
    assert "attractions seeded" in caplog.text


def test_never_overwrites_an_administrators_edit(client) -> None:
    records = _by_slug("taj-mahal")
    seed_attractions(records)
    with session_scope() as session:
        row = session.scalars(select(Attraction)).unique().one()
        row.summary = "Edited by an administrator."

    seed_attractions(records)
    with session_scope() as session:
        assert session.scalars(select(Attraction)).unique().one().summary == (
            "Edited by an administrator."
        )


# ---- the endpoint ----------------------------------------------------------------


def test_lists_a_citys_attractions_with_their_photos(client) -> None:
    seed_attractions(_by_slug("taj-mahal", "burj-khalifa"))

    items = client.get("/api/v1/places/attractions", params={"city": "agra"}).json()["items"]
    assert [item["name"] for item in items] == ["Taj Mahal"]
    image = items[0]["image"]
    assert image["url"].startswith("/media/")
    assert image["license"] and image["author"]
    assert client.get(image["card_url"]).status_code == 200


def test_filters_by_country_and_by_slug(client) -> None:
    seed_attractions(_by_slug("taj-mahal", "burj-khalifa"))

    by_country = client.get(
        "/api/v1/places/attractions", params={"country": "United Arab Emirates"}
    ).json()["items"]
    assert [item["slug"] for item in by_country] == ["burj-khalifa"]

    by_slug = client.get(
        "/api/v1/places/attractions", params=[("slug", "taj-mahal"), ("slug", "burj-khalifa")]
    ).json()["items"]
    assert {item["slug"] for item in by_slug} == {"taj-mahal", "burj-khalifa"}
