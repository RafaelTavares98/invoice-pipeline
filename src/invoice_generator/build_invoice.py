"""Inventing invoices, and posting them to a mailbox.

The generator is the truth. It knows what it wrote, so every test can
compare the reader's answer against the source instead of against a
number typed by hand, which would go stale the moment a layout changed.
"""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

from invoice import Invoice, InvoiceLine
from invoice_generator.layout_styles import render_image_pdf, render_pdf
from issuer_layouts import Layout, all_layouts
from mailbox_intake.mail_sources import write_message

BUYERS = (
    "Costa Verde Importacao Ltda",
    "Pemberton & Clyde Retail",
    "Aurora Nordic Distribution",
    "Sunbelt Provisions Inc.",
)

GOODS = (
    "Stainless hinge, 40mm",
    "Insulated cable reel",
    "Packing foam sheet",
    "Freight surcharge, fuel",
    "Pallet wrap, heavy duty",
    "Warehouse handling fee",
)

TAX_RATES = {
    "A": Decimal("0.21"),
    "B": Decimal("0.0825"),
    "C": Decimal("0.00"),
    "D": Decimal("0.13"),
    "E": Decimal("0.20"),
    "F": Decimal("0.00"),
    "G": Decimal("0.21"),
    "H": Decimal("0.0725"),
}

#: One in this many arrives as a scan rather than a typeset page, so the
#: OCR branch runs on a normal pass and not only in a test written for it.
EVERY_NTH_IS_A_SCAN = 3


@dataclass
class FilledMailbox:
    """What was put in the mailbox, and how each one was printed.

    Which invoices went out as scans is recorded here rather than worked
    out again afterwards. A rule applied in two places is a rule that will
    disagree with itself one day.
    """

    invoices: Dict[str, Invoice] = field(default_factory=dict)
    scanned: List[str] = field(default_factory=list)
    workspace: Path = None

    @property
    def typeset(self) -> List[str]:
        """The invoices that carry a text layer."""
        return [n for n in self.invoices if n not in self.scanned]


def fill_mailbox(
    folder: Path, per_layout: int = 2, workspace: Path = None
) -> FilledMailbox:
    """Write one mail per invoice, and return what was written."""
    workspace = Path(workspace or folder / "_rendered")
    filled = FilledMailbox(workspace=workspace)
    counter = 0
    for code, layout in sorted(all_layouts().items()):
        for index in range(per_layout):
            invoice = build_invoice(layout, index)
            as_scan = counter % EVERY_NTH_IS_A_SCAN == 2
            pdf = print_one(invoice, layout, workspace, as_scan)
            write_message(
                folder=folder,
                identifier=invoice.number,
                subject=f"Invoice {invoice.number}",
                attachments=[(pdf.name, pdf.read_bytes())],
            )
            filled.invoices[invoice.number] = invoice
            if as_scan:
                filled.scanned.append(invoice.number)
            counter += 1
    return filled


def build_invoice(layout: Layout, index: int) -> Invoice:
    """Create one invoice whose numbers are internally consistent."""
    shuffler = random.Random(f"{layout.code}-{index}")
    issued = date(2026, 1, 5) + timedelta(days=index * 3)
    lines = _build_lines(layout, shuffler)
    subtotal = sum((line.line_total for line in lines), Decimal("0"))
    tax_total = _round_money(subtotal * TAX_RATES[layout.code])
    return Invoice(
        number=f"{layout.code}-2026-{1000 + index}",
        issue_date=issued,
        due_date=issued + timedelta(days=30),
        seller=layout.seller,
        buyer=shuffler.choice(BUYERS),
        currency=layout.currency,
        exchange_rate=Decimal("7.2") if layout.second_currency else None,
        lines=lines,
        subtotal=subtotal,
        tax_total=tax_total,
        grand_total=subtotal + tax_total,
    )


def print_one(invoice: Invoice, layout: Layout, workspace: Path, scan):
    """Print one invoice, typeset or scanned."""
    target = workspace / f"{invoice.number}.pdf"
    if scan:
        return render_image_pdf(invoice, layout, target)
    return render_pdf(invoice, layout, target)


def _build_lines(layout: Layout, shuffler) -> List[InvoiceLine]:
    """Create the billed items, with the totals already agreeing."""
    lines = []
    for position in range(layout.line_count):
        quantity = Decimal(shuffler.randint(1, 12))
        unit_price = _round_money(
            Decimal(shuffler.randint(150, 9900)) / Decimal("100")
        )
        lines.append(
            InvoiceLine(
                description=GOODS[position % len(GOODS)],
                quantity=quantity,
                unit_price=unit_price,
                tax_rate=TAX_RATES[layout.code],
                line_total=_round_money(quantity * unit_price),
            )
        )
    return lines


def _round_money(value: Decimal) -> Decimal:
    """Money carries two decimal places and no more."""
    return value.quantize(Decimal("0.01"))
