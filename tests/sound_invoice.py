"""One invoice whose numbers agree, for the rules to be tested against.

Every rule test starts from a sound invoice and breaks exactly one thing.
A test that built its own invoice each time would break two and prove
nothing about which rule caught what.
"""

from datetime import date
from decimal import Decimal

from invoice import Invoice, InvoiceLine
from validation_rules import validate


def build_line(quantity="2", unit_price="10.00", line_total="20.00"):
    """One billed line, sound unless a caller asks otherwise."""
    return InvoiceLine(
        description="Blue widget",
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price),
        tax_rate=Decimal("0.21"),
        line_total=Decimal(line_total),
    )


def build_sound_invoice(**overrides):
    """An invoice that passes every rule, with any field replaceable."""
    defaults = dict(
        number="INV-001",
        issue_date=date(2026, 1, 10),
        due_date=date(2026, 2, 10),
        seller="Nordwind Handel GmbH",
        buyer="Costa Verde Importacao",
        currency="EUR",
        exchange_rate=None,
        lines=[build_line()],
        subtotal=Decimal("20.00"),
        tax_total=Decimal("4.20"),
        grand_total=Decimal("24.20"),
    )
    defaults.update(overrides)
    return Invoice(**defaults)


def rules_fired(invoice, seen_numbers=()):
    """The names of the rules this invoice broke."""
    return {f.rule for f in validate(invoice, seen_numbers=seen_numbers)}
