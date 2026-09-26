"""Reading a printed number and a printed date.

The same digits mean two different days and two different amounts
depending on where the invoice was printed. These tests pin that down,
because everything downstream trusts it.
"""

from datetime import date
from decimal import Decimal

import pytest

from amounts_and_dates import (
    COMMA_DECIMAL, DAY_FIRST, DOT_DECIMAL, ISO, MONTH_FIRST,
    parse_amount, parse_date,
)
from issuer_layouts import layout_for


def test_a_comma_is_the_cents_mark_in_europe():
    assert parse_amount("1.234,56", COMMA_DECIMAL) == Decimal("1234.56")


def test_a_dot_is_the_cents_mark_in_the_united_states():
    assert parse_amount("1,234.56", DOT_DECIMAL) == Decimal("1234.56")


def test_a_currency_sign_is_ignored():
    assert parse_amount("EUR 22,50", COMMA_DECIMAL) == Decimal("22.50")


def test_a_negative_amount_keeps_its_sign():
    assert parse_amount("-40.00", DOT_DECIMAL) == Decimal("-40.00")


def test_an_amount_with_no_digits_is_refused():
    with pytest.raises(ValueError):
        parse_amount("n/a", DOT_DECIMAL)


def test_an_unknown_decimal_mark_is_refused():
    with pytest.raises(ValueError):
        parse_amount("10.00", "semicolon")


def test_the_same_digits_read_two_ways_give_two_days():
    printed = "03/04/2026"

    assert parse_date(printed, DAY_FIRST) == date(2026, 4, 3)
    assert parse_date(printed, MONTH_FIRST) == date(2026, 3, 4)


def test_an_iso_date_reads_year_first():
    assert parse_date("2026-04-03", ISO) == date(2026, 4, 3)


def test_a_date_with_two_parts_is_refused():
    with pytest.raises(ValueError):
        parse_date("04/2026", DAY_FIRST)


def test_an_unknown_date_order_is_refused():
    with pytest.raises(ValueError):
        parse_date("03/04/2026", "whenever")


def test_an_unknown_layout_code_is_refused():
    with pytest.raises(KeyError):
        layout_for("Z")
