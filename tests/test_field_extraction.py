"""Printing an invoice and reading it back off the page.

The generator knows what it drew, so every expected value comes from the
source invoice. No number is typed in by hand, and none goes stale when a
layout changes.
"""

from pathlib import Path

import pytest

from amounts_and_dates import COMMA_DECIMAL
from invoice_generator.build_invoice import build_invoice
from invoice_generator.layout_styles import render_pdf
from issuer_layouts import (
    ASIAN_EXPORT, EUROPEAN_VAT, FREIGHT, US_COMMERCIAL,
    all_layouts, layout_for,
)
from mailbox_intake.field_extraction import (
    FULL_CONFIDENCE, detect_layout, extract, find_field, read_item,
)
from mailbox_intake.page_text import TEXT_LAYER, classify, read_pages
from sound_invoice import rules_fired
from validation_rules import validate

ALL_CODES = sorted(all_layouts())


def refuse_to_ocr(path):
    raise AssertionError(f"{path} should have carried a text layer")


def render(tmp_path: Path, code: str, index: int = 0):
    """One invoice of one layout, printed and read back off the page."""
    layout = layout_for(code)
    source = build_invoice(layout, index)
    target = render_pdf(source, layout, tmp_path / f"{code}.pdf")
    return source, layout, read_pages(target, refuse_to_ocr)


def numeric_columns(layout) -> int:
    """How many amounts one row of this issuer's table carries."""
    return len(layout.columns) - 1


@pytest.mark.parametrize("code", ALL_CODES)
def test_a_generated_pdf_carries_a_text_layer(tmp_path, code):
    layout = layout_for(code)
    target = render_pdf(
        build_invoice(layout, 0), layout, tmp_path / "a.pdf"
    )

    assert classify(target) == TEXT_LAYER


@pytest.mark.parametrize("code", ALL_CODES)
def test_the_layout_is_recognised_from_the_page(tmp_path, code):
    _, layout, lines = render(tmp_path, code)

    assert detect_layout(lines) == layout


@pytest.mark.parametrize("code", ALL_CODES)
def test_every_field_survives_the_round_trip(tmp_path, code):
    source, layout, lines = render(tmp_path, code)

    read = extract(lines, layout, FULL_CONFIDENCE)

    assert read.number == source.number
    assert read.issue_date == source.issue_date
    assert read.due_date == source.due_date
    assert read.buyer == source.buyer
    assert read.currency == source.currency
    assert read.subtotal == source.subtotal
    assert read.tax_total == source.tax_total
    assert read.grand_total == source.grand_total


@pytest.mark.parametrize("code", ALL_CODES)
def test_every_line_survives_the_round_trip(tmp_path, code):
    source, layout, lines = render(tmp_path, code)

    read = extract(lines, layout, FULL_CONFIDENCE)

    assert len(read.lines) == len(source.lines)
    for taken, given in zip(read.lines, source.lines):
        assert taken.description == given.description
        assert taken.quantity == given.quantity
        assert taken.unit_price == given.unit_price
        assert taken.line_total == given.line_total


@pytest.mark.parametrize("code", ALL_CODES)
def test_a_generated_invoice_passes_every_rule(tmp_path, code):
    _, layout, lines = render(tmp_path, code)

    read = extract(lines, layout, FULL_CONFIDENCE)

    assert validate(read, seen_numbers=()) == []


def test_a_comma_decimal_mark_is_read_as_cents(tmp_path):
    source, layout, lines = render(tmp_path, EUROPEAN_VAT)

    read = extract(lines, layout, FULL_CONFIDENCE)

    assert layout.decimal_mark == COMMA_DECIMAL
    assert read.grand_total == source.grand_total


def test_a_month_first_date_is_not_read_day_first(tmp_path):
    source, layout, lines = render(tmp_path, US_COMMERCIAL)

    read = extract(lines, layout, FULL_CONFIDENCE)

    assert read.issue_date == source.issue_date


def test_the_freight_layout_carries_more_lines(tmp_path):
    source, _, _ = render(tmp_path, FREIGHT)

    assert len(source.lines) == 6


def test_a_landscape_page_is_read_like_any_other(tmp_path):
    source, layout, lines = render(tmp_path, FREIGHT)

    read = extract(lines, layout, FULL_CONFIDENCE)

    assert layout.landscape is True
    assert len(read.lines) == len(source.lines)


def test_a_total_printed_above_the_lines_is_still_found(tmp_path):
    source, layout, lines = render(tmp_path, ASIAN_EXPORT)

    read = extract(lines, layout, FULL_CONFIDENCE)

    assert layout.totals_above_lines is True
    assert read.grand_total == source.grand_total


def test_a_second_currency_keeps_its_rate(tmp_path):
    source, layout, lines = render(tmp_path, ASIAN_EXPORT)

    read = extract(lines, layout, FULL_CONFIDENCE)

    assert read.exchange_rate == source.exchange_rate


def test_a_quantity_printed_before_the_description_is_still_read(tmp_path):
    source, layout, lines = render(tmp_path, "H")

    read = extract(lines, layout, FULL_CONFIDENCE)

    assert layout.columns[0][1] == "quantity"
    for taken, given in zip(read.lines, source.lines):
        assert taken.description == given.description
        assert taken.quantity == given.quantity


def test_the_total_label_does_not_match_the_subtotal_row():
    lines = ["Subtotal: 100.00", "Tax: 8.25", "Total: 108.25"]

    assert find_field(lines, "Total") == "108.25"


def test_a_label_sharing_a_line_with_another_column_is_found():
    lines = ["Hamburg, Germany           Invoice no: B-2026-1000"]

    assert find_field(lines, "Invoice no") == "B-2026-1000"


def test_an_unreadable_item_row_is_skipped_not_guessed():
    layout = layout_for(US_COMMERCIAL)
    broken = "Widget n/a n/a n/a n/a"

    assert read_item(
        broken, layout, FULL_CONFIDENCE, numeric_columns(layout)
    ) is None


def test_a_short_item_row_is_skipped():
    layout = layout_for(US_COMMERCIAL)

    assert read_item(
        "Widget 1", layout, FULL_CONFIDENCE, numeric_columns(layout)
    ) is None


def test_an_unknown_layout_code_gives_no_layout():
    assert detect_layout(["Invoice: Z-2026-1"]) is None


def test_a_page_without_an_invoice_number_gives_no_layout():
    assert detect_layout(["Staff canteen menu for the week"]) is None


def test_a_missing_field_is_left_empty_not_invented():
    read = extract(
        ["Invoice no: B-2026-1000"], layout_for(US_COMMERCIAL),
        FULL_CONFIDENCE,
    )

    assert read.buyer == ""
    assert read.subtotal is None
    assert read.lines == []


def test_a_missing_field_is_reported_by_the_validator():
    read = extract(
        ["Invoice no: B-2026-1000"], layout_for(US_COMMERCIAL),
        FULL_CONFIDENCE,
    )

    assert "required_fields" in rules_fired(read)
