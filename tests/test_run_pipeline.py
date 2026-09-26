"""The whole chain, from a mailbox to the two files.

The real OCR tests live at the end, and only run on a machine that has an
engine installed. Everything before them uses a stand-in, so the chain can
be exercised anywhere.
"""

import csv
from decimal import Decimal
from pathlib import Path

import pytest

import run_pipeline
from csv_output.table_writer import ExtractedInvoice, write_lines
from invoice_generator.build_invoice import build_invoice, fill_mailbox
from invoice_generator.layout_styles import (
    render_image_pdf, render_pdf, truth_file,
)
from issuer_layouts import FREIGHT, all_layouts, layout_for
from mailbox_intake.attachment_store import fetch_new, read_manifest
from mailbox_intake.field_extraction import (
    FULL_CONFIDENCE, OCR_CONFIDENCE, extract,
)
from mailbox_intake.mail_sources import LocalMailbox, write_message
from mailbox_intake.page_text import (
    IMAGE_ONLY, TESSERACT_FALLBACKS, classify, read_pages, read_text_layer,
    tesseract_reader,
)
from sound_invoice import build_line, build_sound_invoice
from validation_rules import validate

ALL_CODES = sorted(all_layouts())


def fake_ocr(path: Path) -> str:
    """Stand in for an OCR engine.

    A real engine reads pixels. This finds the words the generator drew,
    recorded beside the rendered page, so the chain can be exercised on a
    machine with no OCR binary installed. The real reader is
    `tesseract_reader`, tested at the end of this file.
    """
    typeset = read_text_layer(path)
    if typeset:
        return typeset
    wanted = truth_file(Path(path.name.split("__")[-1])).name
    for parent in path.parents:
        for found in parent.rglob(wanted):
            return found.read_text(encoding="utf-8")
    return ""


@pytest.fixture
def filled(tmp_path):
    """A mailbox with two invoices of every layout already in it."""
    inbox = tmp_path / "inbox"
    return inbox, fill_mailbox(inbox, per_layout=2), tmp_path


def read_csv(path: Path):
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run_over(inbox, tmp_path):
    return run_pipeline.run(
        mailbox=LocalMailbox(inbox),
        store=tmp_path / "raw",
        output=tmp_path / "out",
        ocr_reader=fake_ocr,
    )


def test_the_whole_chain_produces_both_files(filled):
    inbox, written, tmp_path = filled

    summary = run_over(inbox, tmp_path)

    assert summary.lines_csv.exists()
    assert summary.findings_csv.exists()
    assert summary.stored == len(written.invoices)


def test_every_typeset_invoice_is_read_without_a_model(filled):
    inbox, written, tmp_path = filled

    assert run_over(inbox, tmp_path).read_as_text == len(written.typeset)


def test_some_invoices_arrive_as_a_picture_of_a_page(filled):
    inbox, written, tmp_path = filled

    assert run_over(inbox, tmp_path).read_by_model == len(written.scanned)
    assert written.scanned


def test_every_invoice_matches_its_source(filled):
    inbox, written, tmp_path = filled

    summary = run_over(inbox, tmp_path)
    read = {r.invoice.number: r.invoice for r in summary.results}

    for number, source in written.invoices.items():
        assert read[number].grand_total == source.grand_total
        assert read[number].issue_date == source.issue_date
        assert read[number].buyer == source.buyer
        assert len(read[number].lines) == len(source.lines)


def test_a_clean_run_flags_nothing(filled):
    inbox, _, tmp_path = filled

    assert run_over(inbox, tmp_path).flagged == 0


def test_one_row_per_billed_line(filled):
    inbox, _, tmp_path = filled

    summary = run_over(inbox, tmp_path)
    rows = read_csv(summary.lines_csv)

    assert len(rows) == sum(len(r.invoice.lines) for r in summary.results)


def test_a_scanned_page_is_trusted_less_than_a_typeset_one(filled):
    inbox, written, tmp_path = filled

    summary = run_over(inbox, tmp_path)
    by_number = {r.invoice.number: r.invoice for r in summary.results}

    assert (
        by_number[written.scanned[0]].lines[0].confidence
        < by_number[written.typeset[0]].lines[0].confidence
    )


def test_a_second_run_over_the_same_mailbox_stores_nothing(filled):
    inbox, _, tmp_path = filled

    first = run_over(inbox, tmp_path)
    second = run_over(inbox, tmp_path)

    assert first.stored > 0
    assert second.stored == 0


def test_the_manifest_remembers_every_message(filled):
    inbox, written, tmp_path = filled
    store = tmp_path / "raw"

    fetch_new(LocalMailbox(inbox), store)

    assert len(read_manifest(store)) == len(written.invoices)


def test_a_duplicate_invoice_number_is_flagged(tmp_path):
    inbox = tmp_path / "inbox"
    written = fill_mailbox(inbox, per_layout=1)
    again = written.workspace / f"{written.typeset[0]}.pdf"
    write_message(
        folder=inbox, identifier="second-copy", subject="again",
        attachments=[("again.pdf", again.read_bytes())],
    )

    summary = run_over(inbox, tmp_path)
    rules = {
        finding.rule
        for result in summary.results
        for finding in result.findings
    }

    assert "number_is_new" in rules


def test_an_attachment_that_is_not_an_invoice_is_counted(tmp_path):
    from reportlab.pdfgen import canvas

    inbox = tmp_path / "inbox"
    fill_mailbox(inbox, per_layout=1)
    stray = tmp_path / "stray.pdf"
    sheet = canvas.Canvas(str(stray))
    sheet.drawString(40, 700, "Staff canteen menu for the week of March")
    sheet.drawString(40, 680, "Soup, bread, and a choice of two mains")
    sheet.save()
    write_message(
        folder=inbox, identifier="stray", subject="menu",
        attachments=[("menu.pdf", stray.read_bytes())],
    )

    assert run_over(inbox, tmp_path).unrecognised == 1


def test_a_missing_ocr_engine_does_not_end_the_batch(filled):
    inbox, written, tmp_path = filled

    def no_engine(path):
        raise RuntimeError("tesseract is not installed")

    summary = run_pipeline.run(
        mailbox=LocalMailbox(inbox),
        store=tmp_path / "raw",
        output=tmp_path / "out",
        ocr_reader=no_engine,
    )

    assert summary.unreadable == len(written.scanned)
    assert len(summary.results) == len(written.typeset)
    assert "tesseract" in summary.problems[0]


def test_a_flagged_line_still_reaches_the_table(tmp_path):
    broken = build_sound_invoice(
        number="A-2026-9999",
        buyer="",
        lines=[build_line(line_total="99.00")],
        subtotal=Decimal("99.00"),
        tax_total=Decimal("20.79"),
        grand_total=Decimal("119.79"),
    )
    result = ExtractedInvoice(
        source_file="broken.pdf",
        invoice=broken,
        findings=validate(broken, seen_numbers=()),
    )

    rows = read_csv(write_lines([result], tmp_path / "lines.csv"))

    assert len(rows) == 1
    assert "line_arithmetic" in rows[0]["flags"]


def test_the_findings_file_names_the_rule_and_the_line(filled):
    inbox, written, tmp_path = filled
    again = written.workspace / f"{written.typeset[0]}.pdf"
    write_message(
        folder=inbox, identifier="second-copy", subject="again",
        attachments=[("again.pdf", again.read_bytes())],
    )

    rows = read_csv(run_over(inbox, tmp_path).findings_csv)

    assert {"rule", "message", "line_number"} <= set(rows[0])


# ------------------------------------------------------ the real engine


def has_tesseract() -> bool:
    """Whether an OCR engine is installed on this machine."""
    import shutil

    if shutil.which("tesseract"):
        return True
    return any(Path(c).exists() for c in TESSERACT_FALLBACKS)


needs_engine = pytest.mark.skipif(
    not has_tesseract(), reason="no OCR engine installed"
)


@needs_engine
@pytest.mark.parametrize("code", ALL_CODES)
def test_a_scan_read_by_the_real_engine_matches_its_source(tmp_path, code):
    """The accuracy test the readme quotes.

    The generator recorded what it drew, so this compares the engine's
    answer against the source and not against a number typed by hand.
    """
    layout = layout_for(code)
    source = build_invoice(layout, 0)
    target = render_image_pdf(source, layout, tmp_path / f"{code}.pdf")

    assert classify(target) == IMAGE_ONLY

    lines = read_pages(target, tesseract_reader)
    read = extract(lines, layout, OCR_CONFIDENCE)

    assert read.number == source.number
    assert read.currency == source.currency
    assert read.subtotal == source.subtotal
    assert read.grand_total == source.grand_total
    assert len(read.lines) == len(source.lines)
    for taken, given in zip(read.lines, source.lines):
        assert taken.quantity == given.quantity
        assert taken.unit_price == given.unit_price
        assert taken.line_total == given.line_total


@needs_engine
def test_a_scan_passes_every_rule_after_the_real_engine(tmp_path):
    layout = layout_for(FREIGHT)
    source = build_invoice(layout, 1)
    target = render_image_pdf(source, layout, tmp_path / "c.pdf")

    lines = read_pages(target, tesseract_reader)
    read = extract(lines, layout, OCR_CONFIDENCE)

    assert validate(read, seen_numbers=()) == []


@needs_engine
def test_a_typeset_page_never_reaches_the_engine(tmp_path):
    layout = layout_for(FREIGHT)
    target = render_pdf(
        build_invoice(layout, 0), layout, tmp_path / "typeset.pdf"
    )

    def refuse(path):
        raise AssertionError("a typeset page must not go to OCR")

    assert read_pages(target, refuse)
    assert extract(
        read_pages(target, refuse), layout, FULL_CONFIDENCE
    ).number
