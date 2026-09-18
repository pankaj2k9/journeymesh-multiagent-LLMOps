"""Foreign exchange.

The rules under test are the ones that keep a converted figure honest: a rate
always has provenance, a converted amount is always an estimate, and the
provider's own price is never overwritten.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.constants import SOURCE_CACHED, SOURCE_LIVE, SOURCE_MOCK, SUPPORTED_CURRENCIES
from app.db.models import FxRate
from app.providers import fx as fx_providers
from app.providers.fx import FxProvider, OfflineFxProvider, RateTable
from app.services.currency import (
    ExchangeRate,
    apply,
    currency_for_country,
    currency_from_locale,
    identity_rate,
    offline_rate,
    resolve_currency,
)
from app.services.currency_service import CurrencyService
from app.services.money import Money


class StubProvider:
    """A provider with fixed rates, so the tests never touch the network."""

    name = "stub"

    def __init__(self, rates: dict[str, str] | None = None, fail: bool = False) -> None:
        self.rates = rates or {"EUR": "1", "USD": "1.10", "BDT": "130.00", "GBP": "0.85"}
        self.fail = fail
        self.calls = 0

    async def fetch_rates(self, base: str, symbols: list[str]) -> RateTable:
        self.calls += 1
        if self.fail:
            raise RuntimeError("upstream is down")
        return RateTable(
            base=base,
            rates={code: Decimal(value) for code, value in self.rates.items()},
            rate_date=None,
            provider=self.name,
        )


@pytest.fixture()
def stub(monkeypatch) -> StubProvider:
    provider = StubProvider()
    monkeypatch.setattr(fx_providers, "fx_provider", lambda: provider)
    return provider


class TestResolution:
    def test_the_account_preference_wins(self) -> None:
        assert (
            resolve_currency(
                user_preference="EUR", trip_currency="BDT", accept_language="en-US"
            )
            == "EUR"
        )

    def test_then_the_trip(self) -> None:
        assert resolve_currency(trip_currency="BDT", accept_language="en-US") == "BDT"

    def test_then_the_home_country(self) -> None:
        assert resolve_currency(home_country="in", accept_language="en-US") == "INR"

    def test_then_the_browser_region(self) -> None:
        assert resolve_currency(accept_language="bn-BD,bn;q=0.9,en;q=0.8") == "BDT"

    def test_then_the_default(self) -> None:
        assert resolve_currency() == "USD"

    def test_an_unsupported_preference_falls_through_rather_than_failing(self) -> None:
        assert resolve_currency(user_preference="XYZ", trip_currency="BDT") == "BDT"

    def test_the_region_names_the_currency_not_the_language(self) -> None:
        """An en-IN traveller spends rupees; a bn-GB one spends pounds."""
        assert currency_from_locale("en-IN") == "INR"
        assert currency_from_locale("bn-GB") == "GBP"

    def test_a_language_with_no_region_names_no_currency(self) -> None:
        """Guessing dollars from a bare `en` is how a Bangladeshi becomes American."""
        assert currency_from_locale("en") is None
        assert currency_from_locale("") is None
        assert currency_from_locale(None) is None

    def test_countries_sharing_the_euro_are_listed_not_inferred(self) -> None:
        for country in ("ES", "FR", "DE", "IT"):
            assert currency_for_country(country) == "EUR"


class TestOfflineRates:
    def test_every_supported_currency_has_a_fallback(self) -> None:
        for code in SUPPORTED_CURRENCIES:
            rate = offline_rate("EUR", code)
            assert rate.rate > 0
            assert rate.source == SOURCE_MOCK

    def test_the_offline_table_is_never_presented_as_live(self) -> None:
        assert offline_rate("USD", "BDT").is_live is False

    def test_a_currency_to_itself_is_exactly_one(self) -> None:
        rate = identity_rate("BDT")
        assert rate.rate == Decimal(1)
        assert apply(Money.of("500", "BDT"), rate).converted.as_str() == "500.00"


class TestConversion:
    def test_the_original_is_kept_beside_the_converted(self) -> None:
        rate = ExchangeRate(
            source_currency="USD",
            target_currency="BDT",
            rate=Decimal("123.00"),
            retrieved_at=datetime.now(timezone.utc),
            source=SOURCE_LIVE,
            provider="stub",
        )
        converted = apply(Money.of("650", "USD"), rate)

        assert converted.original.as_str() == "650.00"
        assert converted.original.currency == "USD"
        assert converted.converted.as_str() == "79950.00"
        assert converted.converted.currency == "BDT"

    def test_a_conversion_is_always_flagged_as_an_estimate(self) -> None:
        """The bank applies its own rate and spread. This is never the charge."""
        rate = ExchangeRate(
            source_currency="USD",
            target_currency="BDT",
            rate=Decimal("123.00"),
            retrieved_at=datetime.now(timezone.utc),
            source=SOURCE_LIVE,
            provider="stub",
        )
        converted = apply(Money.of("650", "USD"), rate)
        assert converted.is_estimate is True
        assert converted.to_dict()["is_estimate"] is True

    def test_a_same_currency_conversion_is_not_an_estimate(self) -> None:
        converted = apply(Money.of("650", "USD"), identity_rate("USD"))
        assert converted.unchanged is True
        assert converted.to_dict()["is_estimate"] is False

    def test_a_rate_for_the_wrong_pair_is_refused(self) -> None:
        from app.services.currency import UnsupportedCurrency

        rate = offline_rate("EUR", "BDT")
        with pytest.raises(UnsupportedCurrency):
            apply(Money.of("650", "USD"), rate)


class TestCurrencyService:
    async def test_a_live_rate_is_fetched_and_labelled(self, db_session: Session, stub) -> None:
        rate = await CurrencyService(db_session).get_exchange_rate("USD", "BDT")
        assert rate.source == SOURCE_LIVE
        assert rate.provider == "stub"
        # 130 BDT per EUR / 1.10 USD per EUR.
        assert rate.rate == Decimal("118.18181818")

    async def test_the_whole_table_is_cached_by_one_fetch(
        self, db_session: Session, stub
    ) -> None:
        service = CurrencyService(db_session)
        await service.get_exchange_rate("USD", "BDT")
        assert stub.calls == 1

        # A different pair is answered from the same stored table.
        again = await service.get_exchange_rate("GBP", "BDT")
        assert stub.calls == 1
        assert again.source == SOURCE_CACHED

    async def test_a_fresh_cache_is_reused_rather_than_refetched(
        self, db_session: Session, stub
    ) -> None:
        service = CurrencyService(db_session)
        await service.get_exchange_rate("USD", "BDT")
        await service.get_exchange_rate("USD", "BDT")
        assert stub.calls == 1

    async def test_a_stale_rate_is_preferred_to_the_offline_table(
        self, db_session: Session, monkeypatch
    ) -> None:
        """A real rate from this morning beats an indicative constant."""
        db_session.add(
            FxRate(
                base_currency="USD",
                quote_currency="BDT",
                rate=Decimal("121.50"),
                provider="stub",
                source=SOURCE_LIVE,
                retrieved_at=datetime.now(timezone.utc) - timedelta(days=3),
            )
        )
        db_session.flush()
        monkeypatch.setattr(fx_providers, "fx_provider", lambda: StubProvider(fail=True))

        rate = await CurrencyService(db_session).get_exchange_rate("USD", "BDT")
        assert rate.rate == Decimal("121.50")
        assert rate.source == SOURCE_CACHED
        assert rate.provider == "stub"

    async def test_with_nothing_at_all_the_offline_table_answers(
        self, db_session: Session, monkeypatch
    ) -> None:
        monkeypatch.setattr(fx_providers, "fx_provider", lambda: StubProvider(fail=True))
        rate = await CurrencyService(db_session).get_exchange_rate("USD", "BDT")
        assert rate.source == SOURCE_MOCK
        assert rate.provider == "offline_table"

    async def test_a_pair_the_provider_does_not_cover_degrades_alone(
        self, db_session: Session, monkeypatch
    ) -> None:
        """The ECB set has no BDT. That must not cost us live USD and GBP."""
        partial = StubProvider(rates={"EUR": "1", "USD": "1.10", "GBP": "0.85"})
        monkeypatch.setattr(fx_providers, "fx_provider", lambda: partial)
        service = CurrencyService(db_session)

        uncovered = await service.get_exchange_rate("USD", "BDT")
        assert uncovered.source == SOURCE_MOCK

        covered = await service.get_exchange_rate("USD", "GBP")
        assert covered.source in (SOURCE_LIVE, SOURCE_CACHED)

    async def test_a_currency_to_itself_never_calls_a_provider(
        self, db_session: Session, stub
    ) -> None:
        rate = await CurrencyService(db_session).get_exchange_rate("BDT", "BDT")
        assert rate.rate == Decimal(1)
        assert stub.calls == 0

    async def test_convert_many_uses_one_rate_per_pair(
        self, db_session: Session, stub
    ) -> None:
        results = await CurrencyService(db_session).convert_many(
            [Money.of("100", "USD"), Money.of("200", "USD"), Money.of("50", "GBP")],
            "BDT",
        )
        assert len(results) == 3
        assert results[0].rate.retrieved_at == results[1].rate.retrieved_at

    def test_the_supported_list_carries_symbols_and_precision(
        self, db_session: Session
    ) -> None:
        items = {item["code"]: item for item in CurrencyService(db_session).supported_currencies()}
        assert items["BDT"]["symbol"] == "৳"
        assert items["JPY"]["decimal_places"] == 0
        assert items["USD"]["decimal_places"] == 2
        assert "CAD" in items


class TestProviderAdapters:
    def test_the_offline_provider_satisfies_the_protocol(self) -> None:
        assert isinstance(OfflineFxProvider(), FxProvider)

    async def test_the_offline_provider_quotes_against_any_base(self) -> None:
        table = await OfflineFxProvider().fetch_rates("USD", list(SUPPORTED_CURRENCIES))
        assert table.rates["USD"] == Decimal(1)
        assert table.rates["BDT"] > 1

    async def test_html_from_a_captive_portal_is_a_diagnosable_error(
        self, monkeypatch
    ) -> None:
        """A proxy answering 200 with a login page must not become a rate."""
        import httpx

        from app.providers.fx import FrankfurterProvider

        class Response:
            status_code = 200
            headers = {"content-type": "text/html; charset=utf-8"}

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                raise ValueError("should never be reached")

        class Client:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def __aenter__(self) -> Client:
                return self

            async def __aexit__(self, *args) -> None:
                return None

            async def get(self, *args, **kwargs) -> Response:
                return Response()

        monkeypatch.setattr(httpx, "AsyncClient", Client)
        with pytest.raises(ValueError, match="rather than JSON"):
            await FrankfurterProvider().fetch_rates("EUR", ["USD"])
