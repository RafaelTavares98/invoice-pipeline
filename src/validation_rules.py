"""The seven rules an invoice must satisfy.

A rule that fails marks the invoice. Nothing is ever dropped, because a
line the pipeline hides is a line the buyer never learns about.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, List, Optional

from invoice import Invoice, InvoiceLine

#: Money is compared to the cent. Suppliers round their own way, and a
#: one-cent gap is their rounding, not a mistake worth reporting.
TOLERANCE = Decimal("0.01")

KNOWN_CURRENCIES = frozenset(
    ["EUR", "USD", "GBP", "BRL", "JPY", "CNY", "INR", "CHF", "CAD", "AUD"]
)

REQUIRED_FIELDS = (
    "number",
    "issue_date",
    "due_date",
    "seller",
    "buyer",
    "currency",
    "subtotal",
    "tax_total",
    "grand_total",
)


@dataclass(frozen=True)
class Finding:
    """One rule, one failure, and where it happened."""

    rule: str
    message: str
    line_number: Optional[int] = None


def validate(
    invoice: Invoice, *, seen_numbers: Iterable[str]
) -> List[Finding]:
    """Run every rule and return what failed.

    `seen_numbers` has no default on purpose. A caller that forgets it
    would silently skip the duplicate check, so the contract breaks loudly
    instead.
    """
    findings: List[Finding] = []
    findings.extend(check_required_fields(invoice))
    findings.extend(check_known_currency(invoice))
    findings.extend(check_due_after_issue(invoice))
    findings.extend(check_number_is_new(invoice, seen_numbers))
    findings.extend(check_line_arithmetic(invoice))
    findings.extend(check_line_totals_match_subtotal(invoice))
    findings.extend(check_totals_add_up(invoice))
    return findings


def check_required_fields(invoice: Invoice) -> List[Finding]:
    """Every field in REQUIRED_FIELDS must carry a value."""
    missing = [
        name for name in REQUIRED_FIELDS if is_empty(getattr(invoice, name))
    ]
    if not missing:
        return []
    return [
        Finding(
            rule="required_fields",
            message="missing: " + ", ".join(missing),
        )
    ]


def check_known_currency(invoice: Invoice) -> List[Finding]:
    """The currency code must be one the pipeline can convert."""
    if invoice.currency in KNOWN_CURRENCIES:
        return []
    return [
        Finding(
            rule="known_currency",
            message=f"unknown currency code {invoice.currency!r}",
        )
    ]


def check_due_after_issue(invoice: Invoice) -> List[Finding]:
    """An invoice cannot fall due before it was issued."""
    if invoice.issue_date is None or invoice.due_date is None:
        return []
    if invoice.due_date >= invoice.issue_date:
        return []
    return [
        Finding(
            rule="due_after_issue",
            message=(
                f"due {invoice.due_date} precedes issue {invoice.issue_date}"
            ),
        )
    ]


def check_number_is_new(
    invoice: Invoice, seen_numbers: Iterable[str]
) -> List[Finding]:
    """The same invoice number must not arrive twice."""
    if invoice.number not in set(seen_numbers):
        return []
    return [
        Finding(
            rule="number_is_new",
            message=f"invoice number {invoice.number!r} was seen before",
        )
    ]


def check_line_arithmetic(invoice: Invoice) -> List[Finding]:
    """Quantity times unit price must equal the line total."""
    findings = []
    for position, line in enumerate(invoice.lines, start=1):
        expected = line.quantity * line.unit_price
        if matches(expected, line.line_total):
            continue
        findings.append(
            Finding(
                rule="line_arithmetic",
                message=(
                    f"{line.quantity} x {line.unit_price} is {expected}, "
                    f"the line says {line.line_total}"
                ),
                line_number=position,
            )
        )
    return findings


def check_line_totals_match_subtotal(invoice: Invoice) -> List[Finding]:
    """The lines added together must equal the stated subtotal."""
    if invoice.subtotal is None:
        return []
    summed = sum_line_totals(invoice.lines)
    if matches(summed, invoice.subtotal):
        return []
    return [
        Finding(
            rule="line_totals_match_subtotal",
            message=(
                f"lines add up to {summed}, "
                f"the subtotal says {invoice.subtotal}"
            ),
        )
    ]


def check_totals_add_up(invoice: Invoice) -> List[Finding]:
    """Subtotal plus tax must equal the grand total."""
    if invoice.subtotal is None or invoice.tax_total is None:
        return []
    if invoice.grand_total is None:
        return []
    expected = invoice.subtotal + invoice.tax_total
    if matches(expected, invoice.grand_total):
        return []
    return [
        Finding(
            rule="totals_add_up",
            message=(
                f"subtotal plus tax is {expected}, "
                f"the total says {invoice.grand_total}"
            ),
        )
    ]


def sum_line_totals(lines: List[InvoiceLine]) -> Decimal:
    """Add the line totals, starting from an exact zero."""
    return sum((line.line_total for line in lines), Decimal("0"))


def matches(left: Decimal, right: Decimal) -> bool:
    """True when two amounts agree to within the rounding tolerance."""
    return abs(left - right) <= TOLERANCE


def is_empty(value) -> bool:
    """True for a value the page never gave us."""
    return value is None or (isinstance(value, str) and not value.strip())
