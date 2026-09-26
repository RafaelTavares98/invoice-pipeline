"""The two files a person actually opens.

One row per billed line, and one row per rule that failed. A line that
failed a check still appears in the first file, flagged, never only in the
second. A line the software hides is a line nobody checks.
"""

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import List

from invoice import Invoice
from validation_rules import Finding

#: Windows writes a carriage return that a reader on another machine sees
#: as an extra blank row. Pin the terminator so the file travels.
LINE_TERMINATOR = "\n"

LINE_COLUMNS = (
    "source_file", "invoice_number", "issue_date", "due_date", "seller",
    "buyer", "currency", "exchange_rate", "line_number", "description",
    "quantity", "unit_price", "tax_rate", "line_total", "subtotal",
    "tax_total", "grand_total", "confidence", "flags",
)

FINDING_COLUMNS = (
    "source_file", "invoice_number", "line_number", "rule", "message",
)


@dataclass
class ExtractedInvoice:
    """One invoice, its source, and what the rules said about it."""

    source_file: str
    invoice: Invoice
    findings: List[Finding]


def write_lines(results: List[ExtractedInvoice], target: Path) -> Path:
    """Write every billed line of every invoice, flagged where needed."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=LINE_COLUMNS,
            lineterminator=LINE_TERMINATOR,
        )
        writer.writeheader()
        for result in results:
            for row in _rows_for(result):
                writer.writerow(row)
    return target


def write_findings(results: List[ExtractedInvoice], target: Path) -> Path:
    """Write every rule that failed, and where."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=FINDING_COLUMNS,
            lineterminator=LINE_TERMINATOR,
        )
        writer.writeheader()
        for result in results:
            for finding in result.findings:
                writer.writerow({
                    "source_file": result.source_file,
                    "invoice_number": result.invoice.number,
                    "line_number": finding.line_number or "",
                    "rule": finding.rule,
                    "message": finding.message,
                })
    return target


def _rows_for(result: ExtractedInvoice) -> List[dict]:
    """Turn one invoice into one row per billed line.

    An invoice whose table could not be read still gets a row, so that a
    failure is visible in the file rather than absent from it.
    """
    if not result.invoice.lines:
        return [_row(result, None, None)]
    return [
        _row(result, position, line)
        for position, line in enumerate(result.invoice.lines, start=1)
    ]


def _row(result: ExtractedInvoice, position, line) -> dict:
    """One output row: the invoice header plus one of its lines."""
    invoice = result.invoice
    return {
        "source_file": result.source_file,
        "invoice_number": invoice.number,
        "issue_date": _text(invoice.issue_date),
        "due_date": _text(invoice.due_date),
        "seller": invoice.seller,
        "buyer": invoice.buyer,
        "currency": invoice.currency,
        "exchange_rate": _text(invoice.exchange_rate),
        "line_number": position or "",
        "description": line.description if line else "",
        "quantity": _text(line.quantity if line else None),
        "unit_price": _text(line.unit_price if line else None),
        "tax_rate": _text(line.tax_rate if line else None),
        "line_total": _text(line.line_total if line else None),
        "subtotal": _text(invoice.subtotal),
        "tax_total": _text(invoice.tax_total),
        "grand_total": _text(invoice.grand_total),
        "confidence": _text(line.confidence if line else None),
        "flags": _flags_for(result, position),
    }


def _flags_for(result: ExtractedInvoice, position) -> str:
    """Every rule that failed for this line, plus the invoice-wide ones."""
    names = [
        finding.rule
        for finding in result.findings
        if finding.line_number in (None, position)
    ]
    return ";".join(sorted(set(names)))


def _text(value) -> str:
    """Print a value for the file, with an empty cell for nothing."""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)
