"""Turning the lines of a page back into an invoice.

Nothing here depends on a separator character invented for the reader's
convenience. A field is found by the label its issuer prints beside it,
and a row of the table by the amounts it ends in. A field the page does
not give is left empty and reported, never invented.
"""

import re
from decimal import Decimal
from typing import List, Optional, Tuple

from amounts_and_dates import parse_amount, parse_date
from invoice import Invoice, InvoiceLine
from issuer_layouts import Layout, all_layouts, description_at, layout_for

#: How much of a field the reader is willing to vouch for.
FULL_CONFIDENCE = Decimal("1")
OCR_CONFIDENCE = Decimal("0.8")

#: Once one of these starts a line, the table is over.
TOTAL_LABELS = ("Subtotal", "Tax", "Total", "Balance due", "Amount due")

#: What the issuers call the amount owed. The longer names come first so
#: that "Total" never answers for "Balance due" printed further down.
GRAND_TOTAL_LABELS = ("Balance due", "Amount due", "Total")

#: What the issuers call the person being billed.
BUYER_HEADINGS = ("Bill to", "Billed to", "Consignee", "Sold to")


def detect_layout(lines) -> Optional[Layout]:
    """Say which issuer printed this page.

    By the seller's name, which is how a clerk would do it. An invoice
    number is a fallback, because a scan can lose a letter of a name and
    still carry a clean number.
    """
    page = "\n".join(lines)
    for layout in all_layouts().values():
        if layout.seller.lower() in page.lower():
            return layout
    found = re.search(r"\b([A-H])-\d{4}-\d+\b", page)
    if not found:
        return None
    try:
        return layout_for(found.group(1))
    except KeyError:
        return None


def extract(lines: List[str], layout: Layout, confidence) -> Invoice:
    """Read one invoice off the lines of its page."""
    return Invoice(
        number=find_field(lines, layout.number_label) or "",
        issue_date=read_date(
            find_field(lines, layout.issued_label), layout
        ),
        due_date=read_date(find_field(lines, layout.due_label), layout),
        seller=read_seller(lines, layout),
        buyer=read_buyer(lines),
        currency=read_currency(lines),
        exchange_rate=read_exchange_rate(lines, layout),
        lines=read_items(lines, layout, confidence),
        subtotal=read_amount(find_field(lines, "Subtotal"), layout),
        tax_total=read_amount(find_field(lines, "Tax"), layout),
        grand_total=read_grand_total(lines, layout),
    )


def find_field(lines, label: str) -> Optional[str]:
    """Return the value printed after `label:`, or None.

    The label is looked for anywhere in the line, not only at its start,
    because a page with two columns puts the seller's address and the
    invoice number on the same baseline and a reader returns them as one
    line.

    The letter before the label must not be a letter itself, so that
    "Total" never picks up the "Subtotal" printed above it.

    Case is ignored. A model reading a scan returns "subtotal" for a page
    that says "Subtotal", and a field lost to one capital letter is a
    field lost for no reason.
    """
    wanted = re.compile(
        rf"(?<![A-Za-z]){re.escape(label)}\s*:\s*"
        r"(.+?)(?=\s{2,}[A-Z]|\s+[A-Z][\w /.#-]*:\s|$)",
        re.IGNORECASE,
    )
    for line in lines:
        found = wanted.search(line.strip())
        if found:
            return found.group(1).strip()
    return None


def read_seller(lines: List[str], layout: Layout) -> str:
    """The seller's name, printed near the head of the page."""
    for line in lines:
        if layout.seller.lower() in line.lower():
            return layout.seller
    return ""


def read_buyer(lines: List[str]) -> str:
    """The buyer, under whatever this issuer calls that block.

    The heading often shares its baseline with another column, so the
    name is taken from the same line when the heading carries a value,
    and from the line below when it does not.
    """
    for heading in BUYER_HEADINGS:
        named = find_field(lines, heading)
        if named:
            return named
    for position, line in enumerate(lines):
        lowered = line.strip().lower()
        if not any(
            lowered.startswith(head.lower()) for head in BUYER_HEADINGS
        ):
            continue
        if position + 1 < len(lines):
            return lines[position + 1].strip()
    return ""


def read_currency(lines: List[str]) -> str:
    """The currency code, which is three letters and nothing else."""
    value = find_field(lines, "Currency")
    if not value:
        return ""
    found = re.search(r"\b([A-Z]{3})\b", value)
    return found.group(1) if found else ""


def read_grand_total(lines, layout: Layout) -> Optional[Decimal]:
    """The amount owed, under whichever name this issuer gives it.

    The label may carry no colon, because a page that prints it inside a
    box puts the words on the left and the figure on the right.
    """
    for label in GRAND_TOTAL_LABELS:
        wanted = re.compile(
            rf"(?<![A-Za-z]){re.escape(label)}\s*:?\s+([\d][\d.,]*)\s*$",
            re.IGNORECASE,
        )
        for line in lines:
            found = wanted.search(line.strip())
            if found:
                return read_amount(found.group(1), layout)
    return None


def read_items(lines, layout: Layout, confidence) -> List[InvoiceLine]:
    """Read the table of billed items.

    A row is a line that carries a description and as many amounts as the
    table has numeric columns. That holds on a typeset page and on the
    same page after a model has read it.

    The printed header row narrows the search when it survives, but the
    reading does not depend on it. The header is the smallest type on the
    page and the first line an engine loses, and a table whose rows are
    only found through its header is a table that disappears whole.
    """
    wanted = len(layout.columns) - 1
    start = _header_row(lines, layout)
    body = lines[start + 1:] if start is not None else lines
    items = []
    for line in body:
        if _is_end_of_table(line):
            break
        item = read_item(line, layout, confidence, wanted)
        if item is not None:
            items.append(item)
    return items


def read_item(line: str, layout: Layout, confidence, wanted: int):
    """Read one row, or None when it is not a row of the table."""
    description, amounts = _split_row(line, layout, wanted)
    if description is None:
        return None
    quantity, unit_price, tax_rate, line_total = amounts
    return InvoiceLine(
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        tax_rate=tax_rate / Decimal("100"),
        line_total=line_total,
        confidence=confidence,
    )


def read_amount(text: Optional[str], layout: Layout) -> Optional[Decimal]:
    """Read one amount, or None when the page did not print it."""
    if text is None:
        return None
    try:
        return parse_amount(text, layout.decimal_mark)
    except ValueError:
        return None


def read_date(text: Optional[str], layout: Layout):
    """Read one date, or None when the page did not print it."""
    if text is None:
        return None
    try:
        return parse_date(text, layout.date_order)
    except ValueError:
        return None


def read_exchange_rate(lines, layout: Layout) -> Optional[Decimal]:
    """Read the settlement rate, where a layout carries two currencies."""
    if not layout.second_currency:
        return None
    settlement = find_field(lines, "Settlement")
    if not settlement or " at " not in settlement:
        return None
    return read_amount(settlement.split(" at ")[-1], layout)


def _header_row(lines, layout: Layout) -> Optional[int]:
    """Where the table starts, by the column names printed on its head."""
    names = [name.lower() for name, _ in layout.columns]
    for position, line in enumerate(lines):
        lowered = line.lower()
        if all(name in lowered for name in names):
            return position
    return None


def _is_end_of_table(line: str) -> bool:
    """True once the totals block has begun."""
    first = line.strip().split(":")[0].strip()
    return first in TOTAL_LABELS


def _split_row(line: str, layout: Layout, wanted: int):
    """Separate a row into its description and its amounts.

    The description is not always the first column. One issuer prints the
    quantity before it, so the row carries numbers on both sides of the
    text and a reader that only looks at the tail finds nothing.
    """
    tokens = line.strip().split()
    if len(tokens) <= wanted:
        return None, None
    leading = description_at(layout)
    trailing = wanted - leading
    head = tokens[:leading]
    tail = tokens[len(tokens) - trailing:] if trailing else []
    if not all(_is_amount(token) for token in head + tail):
        return None, None
    middle = (
        tokens[leading:len(tokens) - trailing] if trailing
        else tokens[leading:]
    )
    description = " ".join(middle).strip()
    if not description:
        return None, None
    try:
        amounts = _amounts_in_field_order(head, tail, layout)
    except ValueError:
        return None, None
    return description, amounts


def _is_amount(token: str) -> bool:
    """True for a token that is only digits and separators."""
    return bool(re.fullmatch(r"\d[\d.,]*", token))


def _amounts_in_field_order(head, tail, layout: Layout) -> Tuple:
    """Quantity, unit price, tax rate and line total, in that order.

    The page may print them in any order. The layout says which column is
    which, so the reader never assumes one.
    """
    numeric = [
        held for _, held in layout.columns if held != "description"
    ]
    read = [
        parse_amount(token, layout.decimal_mark)
        for token in list(head) + list(tail)
    ]
    by_field = dict(zip(numeric, read))
    return (
        by_field["quantity"],
        by_field["unit_price"],
        by_field["tax_rate"],
        by_field["line_total"],
    )
