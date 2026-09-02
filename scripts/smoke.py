#!/usr/bin/env python3
"""End-to-end smoke test against a running JourneyMesh API.

    make smoke                       # uses http://127.0.0.1:8000
    python scripts/smoke.py http://localhost:9000

Plans a journey, asks for a cheaper hotel while keeping the flights, checks
that the untouched results were preserved, then approves it in Bengali.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8000"
TIMEOUT = 120


def call(base: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        f"{base}/api/v1{path}",
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "X-JourneyMesh-Session": "make-smoke",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read())


def main(argv: list[str]) -> int:
    base = (argv[1] if len(argv) > 1 else DEFAULT_BASE).rstrip("/")

    try:
        health = call(base, "/health")
    except (urllib.error.URLError, OSError):
        print(f"No API is answering on {base}. Start it with: make dev")
        return 1

    print(f"  health     {health['status']}  |  db {health['database']}  |  llm {health['llm']}")

    draft = call(
        base,
        "/trips/plan",
        {
            "query": (
                "Plan a relaxing 5-day family trip from Dhaka to Singapore with a budget "
                "of $3000. We like nature and local food."
            ),
            "origin": "Dhaka",
            "destination": "Singapore",
            "departure_date": "2027-01-10",
            "return_date": "2027-01-14",
            "travelers": 3,
            "budget": 3000,
            "currency": "USD",
            "travel_style": "family",
            "interests": ["food", "nature"],
            "response_language": "en",
        },
    )
    if draft.get("status") == "blocked":
        print(f"  blocked    {draft['reason_code']}: {draft['message']}")
        return 1

    trip_id = draft["trip_id"]
    print(f"  planned    {draft['review_status']}  |  agents: {', '.join(draft['selected_agents'])}")
    print(
        f"             quality {draft['evaluation']['overall_score']:.2f}"
        f"  |  {len(draft['itinerary']['days'])} days"
        f"  |  estimated {draft['budget']['estimated_total']:.0f}"
        f" {draft['budget']['currency']} ({draft['budget']['budget_status']})"
    )

    change = call(
        base,
        f"/trips/{trip_id}/request-changes",
        {
            "requested_changes": (
                "The hotel is too expensive. Find cheaper hotels under $100 per night, "
                "keep my flights."
            ),
            "response_language": "en",
        },
    )
    detail = call(base, f"/trips/{trip_id}")
    preserved = detail["flights"] == draft["flights"] and detail["weather"] == draft["weather"]
    nightly = (detail["hotels"]["options"] or [{}])[0].get("price_per_night")

    print(f"  revision {change['revision']}  re-ran: {', '.join(change['selected_agents'])}")
    print(f"             flights and weather preserved: {preserved}")
    print(f"             new nightly rate: {nightly}")

    final = call(base, f"/trips/{trip_id}/approve", {"response_language": "bn"})
    print(f"  approved   {final['final_summary']['overview']['title']}")

    ok = preserved and final["status"] == "approved"
    print("\n  " + ("smoke test passed" if ok else "smoke test FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
