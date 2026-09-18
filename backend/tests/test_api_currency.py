"""The currency endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestCurrencyList:
    def test_it_lists_every_supported_currency_with_its_symbol(
        self, client: TestClient
    ) -> None:
        payload = client.get("/api/v1/currencies").json()
        codes = {item["code"] for item in payload["items"]}
        assert {"USD", "EUR", "GBP", "INR", "BDT", "CAD"} <= codes

        by_code = {item["code"]: item for item in payload["items"]}
        assert by_code["BDT"]["symbol"] == "৳"
        assert by_code["JPY"]["decimal_places"] == 0

    def test_the_browser_region_decides_the_default(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/currencies", headers={"Accept-Language": "bn-BD,bn;q=0.9,en;q=0.8"}
        )
        assert response.json()["preferred"] == "BDT"

    def test_a_trip_currency_outranks_the_browser(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/currencies?trip_currency=EUR",
            headers={"Accept-Language": "bn-BD"},
        )
        assert response.json()["preferred"] == "EUR"

    def test_the_account_preference_outranks_everything(self, client: TestClient) -> None:
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": "traveller@example.com",
                "password": "a-long-enough-passphrase",
                "preferred_currency": "GBP",
            },
        ).json()
        response = client.get(
            "/api/v1/currencies?trip_currency=EUR",
            headers={
                "Authorization": f"Bearer {registered['access_token']}",
                "Accept-Language": "bn-BD",
            },
        )
        assert response.json()["preferred"] == "GBP"

    def test_with_no_signal_at_all_it_is_the_default(self, client: TestClient) -> None:
        assert client.get("/api/v1/currencies").json()["preferred"] == "USD"


class TestRate:
    def test_a_rate_carries_its_provenance(self, client: TestClient) -> None:
        payload = client.get("/api/v1/currencies/rate?source=USD&target=BDT").json()
        assert payload["source_currency"] == "USD"
        assert payload["target_currency"] == "BDT"
        assert float(payload["rate"]) > 0
        assert payload["source"] in ("LIVE", "CACHED", "MOCK")
        assert payload["provider"]
        assert payload["retrieved_at"]

    def test_an_offline_rate_is_flagged_indicative(self, client: TestClient) -> None:
        """The suite has no network, so this exercises the fallback path."""
        payload = client.get("/api/v1/currencies/rate?source=USD&target=BDT").json()
        if payload["source"] != "LIVE":
            assert payload["indicative"] is True

    def test_a_currency_to_itself_is_one(self, client: TestClient) -> None:
        payload = client.get("/api/v1/currencies/rate?source=BDT&target=BDT").json()
        assert float(payload["rate"]) == 1.0
        assert payload["indicative"] is False

    def test_an_unknown_currency_is_a_422_not_a_500(self, client: TestClient) -> None:
        """A bad query parameter is a bad request, not a server fault."""
        response = client.get("/api/v1/currencies/rate?source=USD&target=XYZ")
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_request"

    def test_a_bad_currency_in_a_conversion_is_also_a_422(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/currencies/convert",
            json={"amount": "10", "from_currency": "ZZZ", "to_currency": "BDT"},
        )
        assert response.status_code == 422


class TestConvert:
    def test_the_original_is_returned_alongside_the_conversion(
        self, client: TestClient
    ) -> None:
        payload = client.post(
            "/api/v1/currencies/convert",
            json={"amount": "650", "from_currency": "USD", "to_currency": "BDT"},
        ).json()

        assert payload["original_amount"] == "650.00"
        assert payload["original_currency"] == "USD"
        assert float(payload["amount"]) > 0
        assert payload["currency"] == "BDT"
        assert payload["exchange_rate"]
        assert payload["exchange_rate_retrieved_at"]

    def test_a_conversion_always_says_it_is_an_estimate(self, client: TestClient) -> None:
        """Never imply the converted figure is the guaranteed card charge."""
        payload = client.post(
            "/api/v1/currencies/convert",
            json={"amount": "650", "from_currency": "USD", "to_currency": "BDT"},
        ).json()
        assert payload["is_estimate"] is True

    def test_converting_to_the_same_currency_is_not_an_estimate(
        self, client: TestClient
    ) -> None:
        payload = client.post(
            "/api/v1/currencies/convert",
            json={"amount": "650", "from_currency": "USD", "to_currency": "USD"},
        ).json()
        assert payload["amount"] == "650.00"
        assert payload["is_estimate"] is False

    def test_amounts_cross_the_wire_as_strings(self, client: TestClient) -> None:
        payload = client.post(
            "/api/v1/currencies/convert",
            json={"amount": 650.5, "from_currency": "USD", "to_currency": "BDT"},
        ).json()
        assert isinstance(payload["amount"], str)
        assert isinstance(payload["original_amount"], str)
