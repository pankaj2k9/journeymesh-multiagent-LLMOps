"""Decimal-safe currency arithmetic.

These are the tests that justify the existence of `app/services/money.py`. If
they pass with `float` substituted for `Decimal`, the module is not earning its
keep - several of them are written specifically to fail that way.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.money import (
    CurrencyMismatch,
    InvalidAmount,
    Money,
    minor_units,
    percentage_of,
    to_decimal,
    total,
)


class TestToDecimal:
    def test_reads_strings_numbers_and_decimals_exactly(self) -> None:
        assert to_decimal("612.55") == Decimal("612.55")
        assert to_decimal(1836) == Decimal("1836")
        assert to_decimal(Decimal("0.0001")) == Decimal("0.0001")

    def test_a_float_converts_through_repr_not_binary(self) -> None:
        # Decimal(0.1) is 0.1000000000000000055511151231257827.
        assert to_decimal(0.1) == Decimal("0.1")

    def test_thousands_separators_survive(self) -> None:
        assert to_decimal("1,840.00") == Decimal("1840.00")

    @pytest.mark.parametrize("value", ["", "  ", "abc", None, [], True])
    def test_rejects_what_is_not_an_amount(self, value: object) -> None:
        with pytest.raises(InvalidAmount):
            to_decimal(value)

    def test_rejects_infinity(self) -> None:
        with pytest.raises(InvalidAmount):
            to_decimal(float("inf"))


class TestArithmetic:
    def test_the_canonical_float_failure_does_not_happen(self) -> None:
        result = Money.of("0.1", "USD") + Money.of("0.2", "USD")
        assert result.amount == Decimal("0.3000")
        assert result.as_str() == "0.30"

    def test_a_hundred_small_additions_do_not_drift(self) -> None:
        running = Money.zero("USD")
        for _ in range(100):
            running = running + Money.of("0.01", "USD")
        assert running.as_str() == "1.00"

    def test_multiplication_by_a_traveller_count(self) -> None:
        assert Money.of("612.00", "USD").times(3).as_str() == "1836.00"

    def test_division_keeps_precision_so_it_multiplies_back(self) -> None:
        fare = Money.of("1000.00", "USD")
        per_head = fare.divided_by(3)
        assert per_head.times(3).as_str() == "1000.00"

    def test_subtraction_can_go_negative(self) -> None:
        remaining = Money.of("4000", "USD") - Money.of("4300", "USD")
        assert remaining.is_negative
        assert remaining.as_str() == "-300.00"

    def test_dividing_by_zero_is_refused(self) -> None:
        with pytest.raises(InvalidAmount):
            Money.of(10, "USD").divided_by(0)


class TestCurrency:
    def test_two_currencies_never_combine(self) -> None:
        with pytest.raises(CurrencyMismatch):
            Money.of(100, "USD") + Money.of(100, "EUR")

    def test_comparison_across_currencies_is_refused_too(self) -> None:
        with pytest.raises(CurrencyMismatch):
            _ = Money.of(100, "USD") < Money.of(100, "EUR")

    def test_an_unsupported_currency_is_rejected_at_construction(self) -> None:
        with pytest.raises(InvalidAmount):
            Money.of(100, "XYZ")

    def test_currency_code_is_normalised(self) -> None:
        assert Money.of(100, "usd").currency == "USD"


class TestRounding:
    def test_half_up_not_bankers(self) -> None:
        # Python's round() gives 612.54 here; a fare quote gives 612.56.
        assert Money.of("612.555", "USD").as_str() == "612.56"
        assert Money.of("612.565", "USD").as_str() == "612.57"

    def test_zero_decimal_currencies_are_not_given_cents(self) -> None:
        assert minor_units("JPY") == 0
        assert Money.of("1000", "JPY").divided_by(3).as_str() == "333"

    def test_two_decimal_currencies_keep_their_cents(self) -> None:
        assert minor_units("USD") == 2
        assert Money.of("1000", "USD").divided_by(3).as_str() == "333.33"


class TestPercentage:
    def test_share_of_a_budget(self) -> None:
        assert percentage_of(Money.of(1836, "USD"), Money.of(4000, "USD")) == Decimal("45.9")

    def test_no_budget_means_no_percentage_rather_than_zero(self) -> None:
        assert percentage_of(Money.of(1836, "USD"), Money.of(0, "USD")) is None


class TestTotal:
    def test_empty_list_totals_to_zero_in_the_named_currency(self) -> None:
        result = total([], "BDT")
        assert result.is_zero and result.currency == "BDT"

    def test_sums_a_list(self) -> None:
        amounts = [Money.of("1820", "USD"), Money.of("920", "USD"), Money.of("340", "USD")]
        assert total(amounts, "USD").as_str() == "3080.00"
