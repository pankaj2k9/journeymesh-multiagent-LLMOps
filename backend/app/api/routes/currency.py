"""Currency endpoints.

Two reads and nothing else. Conversion for display happens here so that the
interface never has to hold an exchange rate of its own - a second rate in a
second place is how two screens end up showing two different totals for one
price.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session, optional_user
from app.core.constants import CONVERTED_AMOUNT_IS_ESTIMATE, SUPPORTED_CURRENCIES
from app.core.exceptions import ValidationRejection
from app.db.models import User
from app.schemas.common import TravelCrewModel
from app.schemas.money import MoneyAmount
from app.services.currency import resolve_currency
from app.services.currency_service import CurrencyService
from app.services.money import Money

router = APIRouter(prefix="/currencies", tags=["currency"])


class CurrencyOut(TravelCrewModel):
    code: str
    symbol: str
    decimal_places: int


class CurrencyListResponse(TravelCrewModel):
    items: list[CurrencyOut]
    # What this caller should be shown, resolved from their account, their
    # locale and the application default - never from IP geolocation.
    preferred: str


class RateOut(TravelCrewModel):
    source_currency: str
    target_currency: str
    rate: str
    source: str
    provider: str
    retrieved_at: str
    # True whenever the rate did not come from the live provider, so the
    # interface can say so rather than implying a quote.
    indicative: bool


class ConversionRequest(TravelCrewModel):
    amount: MoneyAmount
    from_currency: str
    to_currency: str


class ConversionOut(TravelCrewModel):
    original_amount: str
    original_currency: str
    amount: str
    currency: str
    exchange_rate: str
    exchange_rate_source: str
    exchange_rate_retrieved_at: str
    # Always true for a real conversion. The provider bills in its own
    # currency and the traveller's bank applies its own rate and spread, so
    # this figure is an estimate of a card charge and never the charge itself.
    is_estimate: bool


def currency_service(session: Session = Depends(db_session)) -> CurrencyService:
    return CurrencyService(session)


def _checked(code: str, field: str) -> str:
    """Validate a currency code at the boundary.

    Without this the service layer raises a plain ``ValueError`` deep inside a
    conversion and the caller gets a 500 for what is simply a bad query
    parameter. Input is validated where it arrives.
    """
    upper = (code or "").strip().upper()
    if upper not in SUPPORTED_CURRENCIES:
        raise ValidationRejection(
            f"{field} must be one of {', '.join(SUPPORTED_CURRENCIES)}",
            details={"field": field, "value": code},
        )
    return upper


@router.get(
    "",
    response_model=CurrencyListResponse,
    summary="Currencies, and which one to show this traveller",
    description=(
        "The preferred currency is resolved from the account, then the trip, then a "
        "stated home country, then the browser's `Accept-Language` region, then the "
        "application default. IP geolocation is deliberately not consulted: it is "
        "wrong for anyone travelling or on a VPN, and being silently re-denominated "
        "by an invisible signal is worse than being shown the default."
    ),
)
def list_currencies(
    trip_currency: str | None = Query(default=None, max_length=3),
    home_country: str | None = Query(default=None, max_length=2),
    accept_language: str | None = Header(default=None),
    service: CurrencyService = Depends(currency_service),
    user: User | None = Depends(optional_user),
) -> CurrencyListResponse:
    preferred = resolve_currency(
        user_preference=user.preferred_currency if user else None,
        trip_currency=trip_currency,
        home_country=home_country,
        accept_language=accept_language,
    )
    return CurrencyListResponse(
        items=[CurrencyOut(**item) for item in service.supported_currencies()],
        preferred=preferred,
    )


@router.get(
    "/rate",
    response_model=RateOut,
    summary="One exchange rate, with its provenance",
)
async def get_rate(
    source: str = Query(min_length=3, max_length=3),
    target: str = Query(min_length=3, max_length=3),
    service: CurrencyService = Depends(currency_service),
) -> RateOut:
    rate = await service.get_exchange_rate(
        _checked(source, "source"), _checked(target, "target")
    )
    return RateOut(
        source_currency=rate.source_currency,
        target_currency=rate.target_currency,
        rate=format(rate.rate, "f"),
        source=rate.source,
        provider=rate.provider,
        retrieved_at=rate.retrieved_at.isoformat(),
        indicative=not rate.is_live,
    )


@router.post(
    "/convert",
    response_model=ConversionOut,
    summary="Convert an amount, keeping the original",
    description=(
        "The provider's own figure is returned alongside the converted one and is "
        "never replaced. A booking is always charged in the provider's currency."
    ),
)
async def convert(
    payload: ConversionRequest,
    service: CurrencyService = Depends(currency_service),
) -> ConversionOut:
    converted = await service.convert(
        Money(payload.amount, _checked(payload.from_currency, "from_currency")),
        _checked(payload.to_currency, "to_currency"),
    )
    data: dict[str, Any] = converted.to_dict()
    data["is_estimate"] = CONVERTED_AMOUNT_IS_ESTIMATE and not converted.unchanged
    return ConversionOut(**data)
