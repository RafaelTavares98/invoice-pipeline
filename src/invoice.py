"""What an invoice is, once it has been read off the page.

Money is Decimal, never float. A cent lost to binary rounding is a cent
the validator would later report as a mismatch that was never there.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional


@dataclass
class InvoiceLine:
    """One billed item."""

    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal
    #: How much of this line the reader is willing to vouch for. A page
    #: read by a model is trusted less than one read from a text layer.
    confidence: Decimal = Decimal("1")


@dataclass
class Invoice:
    """One invoice, with every line it carries."""

    number: str
    issue_date: Optional[date]
    due_date: Optional[date]
    seller: str
    buyer: str
    currency: str
    exchange_rate: Optional[Decimal]
    lines: List[InvoiceLine] = field(default_factory=list)
    subtotal: Optional[Decimal] = None
    tax_total: Optional[Decimal] = None
    grand_total: Optional[Decimal] = None
