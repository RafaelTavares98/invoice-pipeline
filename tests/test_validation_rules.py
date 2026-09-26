"""The seven rules, one broken thing at a time."""

from datetime import date
from decimal import Decimal

import pytest

from sound_invoice import build_line, build_sound_invoice, rules_fired
from validation_rules import validate


def test_a_sound_invoice_fires_no_rule():
    assert rules_fired(build_sound_invoice()) == set()


def test_line_totals_must_sum_to_the_subtotal():
    invoice = build_sound_invoice(subtotal=Decimal("19.00"))

    assert "line_totals_match_subtotal" in rules_fired(invoice)


def test_subtotal_plus_tax_must_equal_the_grand_total():
    invoice = build_sound_invoice(grand_total=Decimal("25.00"))

    assert "totals_add_up" in rules_fired(invoice)


def test_quantity_times_unit_price_must_equal_the_line_total():
    invoice = build_sound_invoice(
        lines=[build_line(line_total="99.00")],
        subtotal=Decimal("99.00"),
        tax_total=Decimal("20.79"),
        grand_total=Decimal("119.79"),
    )

    assert "line_arithmetic" in rules_fired(invoice)


def test_the_due_date_may_not_precede_the_issue_date():
    invoice = build_sound_invoice(due_date=date(2026, 1, 1))

    assert "due_after_issue" in rules_fired(invoice)


def test_an_invoice_number_may_not_repeat():
    invoice = build_sound_invoice()

    assert "number_is_new" in rules_fired(invoice, seen_numbers=["INV-001"])


def test_a_required_field_may_not_be_empty():
    assert "required_fields" in rules_fired(build_sound_invoice(seller=""))


def test_the_currency_must_be_a_known_code():
    assert "known_currency" in rules_fired(
        build_sound_invoice(currency="XYZ")
    )


def test_a_finding_names_the_line_it_came_from():
    invoice = build_sound_invoice(
        lines=[build_line(line_total="99.00")],
        subtotal=Decimal("99.00"),
        tax_total=Decimal("20.79"),
        grand_total=Decimal("119.79"),
    )

    findings = validate(invoice, seen_numbers=())
    arithmetic = [f for f in findings if f.rule == "line_arithmetic"]

    assert arithmetic[0].line_number == 1


def test_validation_never_removes_a_line():
    invoice = build_sound_invoice(lines=[build_line(line_total="99.00")])

    validate(invoice, seen_numbers=())

    assert len(invoice.lines) == 1


def test_rounding_of_one_cent_is_tolerated():
    invoice = build_sound_invoice(grand_total=Decimal("24.21"))

    assert "totals_add_up" not in rules_fired(invoice)


def test_a_missing_seen_numbers_argument_is_refused():
    with pytest.raises(TypeError):
        validate(build_sound_invoice())
