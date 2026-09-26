"""The whole chain, from mailbox to the two files.

Mailbox, store, reader, rules, files. This module holds the order and
nothing else, so a change to any one step does not touch it.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List

from csv_output.table_writer import (
    ExtractedInvoice, write_findings, write_lines,
)
from mailbox_intake.attachment_store import StoredFile, fetch_new
from mailbox_intake.field_extraction import (
    FULL_CONFIDENCE, OCR_CONFIDENCE, detect_layout, extract,
)
from mailbox_intake.page_text import IMAGE_ONLY, TEXT_LAYER, classify, read_pages
from validation_rules import Finding, validate

LINES_FILE = "invoice_lines.csv"
FINDINGS_FILE = "findings.csv"


@dataclass
class RunSummary:
    """What one pass over the mailbox did."""

    stored: int
    read_as_text: int
    read_by_model: int
    unrecognised: int
    results: List[ExtractedInvoice]
    lines_csv: Path
    findings_csv: Path
    problems: List[str] = field(default_factory=list)

    @property
    def flagged(self) -> int:
        """How many invoices came out with at least one rule broken."""
        return len([r for r in self.results if r.findings])

    @property
    def unreadable(self) -> int:
        """How many files could not be read at all."""
        return len(self.problems)


def run(
    mailbox, store: Path, output: Path, ocr_reader: Callable[[Path], str]
) -> RunSummary:
    """Take everything new in the mailbox as far as the two CSV files."""
    fresh = fetch_new(mailbox, store)
    results: List[ExtractedInvoice] = []
    problems: List[str] = []
    seen_numbers: List[str] = []
    read_as_text = 0
    read_by_model = 0
    unrecognised = 0

    for stored_file in fresh:
        kind = classify(stored_file.path)
        if kind == TEXT_LAYER:
            read_as_text += 1
        else:
            read_by_model += 1
        result, problem = _read_one(
            stored_file, kind, seen_numbers, ocr_reader
        )
        if problem:
            problems.append(problem)
            continue
        if result is None:
            unrecognised += 1
            continue
        seen_numbers.append(result.invoice.number)
        results.append(result)

    return RunSummary(
        stored=len(fresh),
        read_as_text=read_as_text,
        read_by_model=read_by_model,
        unrecognised=unrecognised,
        results=results,
        lines_csv=write_lines(results, output / LINES_FILE),
        findings_csv=write_findings(results, output / FINDINGS_FILE),
        problems=problems,
    )


def _read_one(stored_file: StoredFile, kind: str, seen_numbers, ocr_reader):
    """Read one stored file.

    Returns the invoice, or a sentence saying why this one file could not
    be read. One unreadable page must not end the batch: the other
    invoices in the mailbox are still owed to whoever is waiting.
    """
    try:
        lines = read_pages(stored_file.path, ocr_reader=ocr_reader)
    except Exception as failure:
        return None, f"{stored_file.filename}: {failure}"
    layout = detect_layout(lines)
    if layout is None:
        return None, None
    confidence = OCR_CONFIDENCE if kind == IMAGE_ONLY else FULL_CONFIDENCE
    invoice = extract(lines, layout, confidence)
    findings: List[Finding] = validate(invoice, seen_numbers=seen_numbers)
    return ExtractedInvoice(stored_file.filename, invoice, findings), None
