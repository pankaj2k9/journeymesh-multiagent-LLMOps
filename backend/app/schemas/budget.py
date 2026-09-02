"""Budget schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, computed_field

from app.schemas.common import DataSource, JourneyMeshModel

BudgetStatus = Literal["within_budget", "near_limit", "over_budget", "insufficient_data"]


class BudgetLine(JourneyMeshModel):
    """One row of the cost breakdown, with its own provenance."""

    amount: float = 0.0
    source: DataSource = "ESTIMATE"
    basis: str | None = None


class BudgetBreakdown(JourneyMeshModel):
    flights: float = 0.0
    hotels: float = 0.0
    food: float = 0.0
    transport: float = 0.0
    activities: float = 0.0
    miscellaneous: float = 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> float:
        return round(
            self.flights
            + self.hotels
            + self.food
            + self.transport
            + self.activities
            + self.miscellaneous,
            2,
        )


class BudgetAnalysis(JourneyMeshModel):
    currency: str = "USD"
    total_budget: float | None = None
    estimated_total: float = 0.0
    breakdown: BudgetBreakdown = Field(default_factory=BudgetBreakdown)
    line_provenance: dict[str, BudgetLine] = Field(default_factory=dict)
    remaining_budget: float | None = None
    budget_status: BudgetStatus = "insufficient_data"
    confirmed_cost_total: float = 0.0
    estimated_cost_total: float = 0.0
    per_traveler_total: float | None = None
    recommendations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
