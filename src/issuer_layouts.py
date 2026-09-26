"""The eight issuers, and how each of them prints an invoice.

The records themselves live in `issuer_layouts.json`, so a layout can be
changed, or a ninth issuer added, without opening any code. The same
record drives the generator and the reader, so the two can never drift
apart.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

DEFINITIONS = Path(__file__).with_name("issuer_layouts.json")

EUROPEAN_VAT = "A"
US_COMMERCIAL = "B"
FREIGHT = "C"
ASIAN_EXPORT = "D"


@dataclass(frozen=True)
class Layout:
    """How one issuer prints an invoice."""

    code: str
    name: str
    seller: str
    seller_address: Tuple[str, ...]
    tax_label: str
    tax_id: str
    currency: str
    decimal_mark: str
    date_order: str
    #: What the page calls the thing, and what it calls its number. These
    #: differ by country and are what the reader looks for.
    title: str
    number_label: str
    issued_label: str
    due_label: str
    #: One issuer prints the total block above the line items. A reader
    #: that assumes totals come last reads the wrong numbers.
    totals_above_lines: bool
    #: Every column is a name on the page and the field it holds.
    columns: Tuple[Tuple[str, str], ...]
    #: How the page is put together. Issuers differ in shape, not only in
    #: wording, and a reader that only saw one shape was tested on
    #: nothing.
    style: str = "classic"
    #: A wide table needs a wide page.
    landscape: bool = False
    #: A house colour, as red, green and blue from zero to one.
    accent: Tuple[float, float, float] = (0.15, 0.15, 0.15)
    #: One issuer bills in one currency and settles in another.
    second_currency: str = ""
    line_count: int = 3
    terms: str = ""
    bank_line: str = ""
    ship_to: bool = False
    note: str = ""


@lru_cache(maxsize=1)
def all_layouts() -> Dict[str, Layout]:
    """Every issuer the pipeline knows, read from the definitions file."""
    raw = json.loads(DEFINITIONS.read_text(encoding="utf-8"))
    return {code: _build(row) for code, row in raw.items()}


def layout_for(code: str) -> Layout:
    """Return one issuer, or complain that the code is unknown."""
    layouts = all_layouts()
    if code not in layouts:
        known = ", ".join(sorted(layouts))
        raise KeyError(f"unknown layout {code!r}, known are {known}")
    return layouts[code]


def description_at(layout: Layout) -> int:
    """Which column carries the description. Not always the first."""
    for index, (_, held) in enumerate(layout.columns):
        if held == "description":
            return index
    return 0


def _build(row: dict) -> Layout:
    """Turn one record from the file into a Layout."""
    return Layout(
        **{
            **row,
            "seller_address": tuple(row["seller_address"]),
            "columns": tuple(tuple(pair) for pair in row["columns"]),
            "accent": tuple(row["accent"]),
        }
    )
