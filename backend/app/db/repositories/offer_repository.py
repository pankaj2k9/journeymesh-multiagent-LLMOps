"""Data access for search runs, offers and selections."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Offer, SearchRun, SelectedOffer


class OfferRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- search runs -----------------------------------------------------
    def record_search(self, **fields: Any) -> SearchRun:
        run = SearchRun(**fields)
        self.session.add(run)
        self.session.flush()
        return run

    def get_search(self, search_id: str) -> SearchRun | None:
        return self.session.get(SearchRun, search_id)

    def recent_searches(
        self, *, trip_id: str | None = None, kind: str | None = None, limit: int = 20
    ) -> list[SearchRun]:
        stmt = select(SearchRun)
        if trip_id:
            stmt = stmt.where(SearchRun.trip_id == trip_id)
        if kind:
            stmt = stmt.where(SearchRun.kind == kind)
        return list(
            self.session.scalars(stmt.order_by(SearchRun.created_at.desc()).limit(limit))
        )

    # ---- offers ----------------------------------------------------------
    def add_offer(self, **fields: Any) -> Offer:
        offer = Offer(**fields)
        self.session.add(offer)
        self.session.flush()
        return offer

    def get_offer(self, offer_id: str) -> Offer | None:
        return self.session.get(Offer, offer_id)

    def by_ref(self, offer_ref: str, *, trip_id: str | None = None) -> Offer | None:
        """Find the most recent snapshot of one provider offer.

        Most recent, because an offer that has been re-searched has more than
        one snapshot and the newest is the one a traveller is looking at.
        """
        stmt = select(Offer).where(Offer.offer_ref == offer_ref)
        if trip_id:
            stmt = stmt.where(Offer.trip_id == trip_id)
        return self.session.scalar(stmt.order_by(Offer.created_at.desc()).limit(1))

    def offers_for_search(self, search_id: str) -> list[Offer]:
        return list(
            self.session.scalars(
                select(Offer).where(Offer.search_id == search_id).order_by(Offer.total_amount)
            )
        )

    def offers_for_trip(self, trip_id: str, *, kind: str | None = None) -> list[Offer]:
        stmt = select(Offer).where(Offer.trip_id == trip_id)
        if kind:
            stmt = stmt.where(Offer.kind == kind)
        return list(self.session.scalars(stmt.order_by(Offer.created_at.desc())))

    def count_offers(self, trip_id: str) -> int:
        return int(
            self.session.scalar(
                select(func.count(Offer.id)).where(Offer.trip_id == trip_id)
            )
            or 0
        )

    # ---- selections ------------------------------------------------------
    def add_selection(self, **fields: Any) -> SelectedOffer:
        selection = SelectedOffer(**fields)
        self.session.add(selection)
        self.session.flush()
        return selection

    def get_selection(self, selection_id: str, trip_id: str | None = None) -> SelectedOffer | None:
        stmt = select(SelectedOffer).where(SelectedOffer.id == selection_id)
        if trip_id:
            stmt = stmt.where(SelectedOffer.trip_id == trip_id)
        return self.session.scalar(stmt)

    def active_selections(
        self, trip_id: str, *, kind: str | None = None
    ) -> list[SelectedOffer]:
        stmt = select(SelectedOffer).where(
            SelectedOffer.trip_id == trip_id, SelectedOffer.status == "SELECTED"
        )
        if kind:
            stmt = stmt.where(SelectedOffer.kind == kind)
        return list(self.session.scalars(stmt.order_by(SelectedOffer.created_at)))

    def supersede(self, selection: SelectedOffer, *, by_id: str | None) -> SelectedOffer:
        selection.status = "SUPERSEDED" if by_id else "REMOVED"
        selection.superseded_by_id = by_id
        selection.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return selection

    def all_selections(self, trip_id: str) -> list[SelectedOffer]:
        return list(
            self.session.scalars(
                select(SelectedOffer)
                .where(SelectedOffer.trip_id == trip_id)
                .order_by(SelectedOffer.created_at.desc())
            )
        )
