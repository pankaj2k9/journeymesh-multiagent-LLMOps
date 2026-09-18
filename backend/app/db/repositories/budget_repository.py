"""Data access for trip budgets and the budget ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import BudgetItem, TripBudget


class BudgetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- budget record ---------------------------------------------------
    def get_budget(self, trip_id: str) -> TripBudget | None:
        return self.session.scalar(select(TripBudget).where(TripBudget.trip_id == trip_id))

    def create_budget(self, trip_id: str, **fields: Any) -> TripBudget:
        record = TripBudget(trip_id=trip_id, **fields)
        self.session.add(record)
        self.session.flush()
        return record

    def apply_totals(self, record: TripBudget, expected_version: int, **totals: Any) -> bool:
        """Write the derived totals, but only if nobody else has.

        Returns False when the version moved under us, which is the caller's
        signal to re-read and retry rather than overwrite a concurrent
        selection with a stale total.
        """
        result = self.session.execute(
            update(TripBudget)
            .where(
                TripBudget.id == record.id,
                TripBudget.version == expected_version,
            )
            .values(
                **totals,
                version=expected_version + 1,
                recomputed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount != 1:
            return False
        self.session.flush()
        self.session.refresh(record)
        return True

    # ---- ledger ----------------------------------------------------------
    def add_item(self, **fields: Any) -> BudgetItem:
        item = BudgetItem(**fields)
        self.session.add(item)
        self.session.flush()
        return item

    def get_item(self, item_id: str, trip_id: str | None = None) -> BudgetItem | None:
        stmt = select(BudgetItem).where(BudgetItem.id == item_id)
        if trip_id:
            stmt = stmt.where(BudgetItem.trip_id == trip_id)
        return self.session.scalar(stmt)

    def set_item_state(self, item: BudgetItem, state: str) -> BudgetItem:
        item.state = state
        self.session.flush()
        return item

    def items(
        self,
        trip_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        category: str | None = None,
        state: str | None = None,
    ) -> list[BudgetItem]:
        stmt = select(BudgetItem).where(BudgetItem.trip_id == trip_id)
        if category:
            stmt = stmt.where(BudgetItem.category == category)
        if state:
            stmt = stmt.where(BudgetItem.state == state)
        stmt = stmt.order_by(BudgetItem.created_at.desc(), BudgetItem.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def count_items(self, trip_id: str, *, category: str | None = None) -> int:
        stmt = select(func.count(BudgetItem.id)).where(BudgetItem.trip_id == trip_id)
        if category:
            stmt = stmt.where(BudgetItem.category == category)
        return int(self.session.scalar(stmt) or 0)

    def reversed_ids(self, trip_id: str) -> set[str]:
        """Ids of lines that already have a reversal, so none is reversed twice."""
        rows = self.session.scalars(
            select(BudgetItem.reverses_id).where(
                BudgetItem.trip_id == trip_id,
                BudgetItem.reverses_id.is_not(None),
            )
        )
        return {row for row in rows if row}

    def active_items(
        self, trip_id: str, *, category: str | None = None, source_type: str | None = None
    ) -> list[BudgetItem]:
        """Ledger lines that still count, i.e. neither a reversal nor reversed."""
        reversed_ids = self.reversed_ids(trip_id)
        return [
            item
            for item in self.items(trip_id, category=category)
            if item.reverses_id is None
            and item.id not in reversed_ids
            and (source_type is None or item.source_type == source_type)
        ]
