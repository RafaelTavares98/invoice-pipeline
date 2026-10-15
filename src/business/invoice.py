"""One invoice, and the arithmetic over it.

Nothing here knows about pages or PDF. Every amount is in the invoice's
currency: US dollars from abroad, reais from Brazil. The totals are the
truth the reading pipeline will later be measured against.

There is no tax field. These are export documents: the seller's local VAT is
zeroed on export, and the Brazilian duty is assessed by customs, not by the
supplier. Anything the supplier does charge for arrives as its own line.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

ZERO = Decimal('0.00')


def _round(value):
    return Decimal(f'{value:.2f}')


@dataclass
class Line:
    description: str
    quantity: Decimal
    unit_price: Decimal
    code: str = ''
    unit: str = 'pcs'
    hs_code: str = ''
    weight_kg: Decimal = ZERO
    volume_m3: Decimal = ZERO

    @property
    def net(self):
        return _round(self.quantity * self.unit_price)


@dataclass
class Invoice:
    number: str
    issue_date: date
    due_date: date
    issuer_code: str
    lines: list = field(default_factory=list)
    discount: Decimal = ZERO
    reference: str = ''
    incoterm: str = ''
    shipment: dict = field(default_factory=dict)
    currency: str = 'USD'

    #: What this document is about. A goods invoice bills components, a
    #: freight invoice bills the move, a credit note gives money back.
    kind: str = 'goods'

    #: The chain. Which order it fulfils, which shipment carried it, and
    #: which earlier invoice it replaces or credits.
    order_number: str = ''
    shipment_id: str = ''
    revises: str = ''
    #: An error planted on purpose, named for the answer key.
    anomaly: str = ''
    #: A legitimate invoice that looks like that anomaly, also for the key.
    lookalike_of: str = ''
    #: The account printed to pay into. Empty means the issuer's usual one.
    pay_to: str = ''
    #: The address the mail came from. Empty means the issuer's own.
    sender: str = ''
    #: Extra labelled figures printed beside the dates, such as the FX
    #: rate and the customs value of a duty statement.
    facts: tuple = ()

    @property
    def subtotal(self):
        return _round(sum((line.net for line in self.lines), ZERO))

    @property
    def grand_total(self):
        return _round(self.subtotal - self.discount)

    @property
    def is_credit(self):
        return self.kind == 'credit'

    @property
    def total_weight_kg(self):
        return _round(sum((line.weight_kg for line in self.lines), ZERO))

    def as_truth(self):
        """The answer key, for checking whatever reads this invoice later."""
        return {
            'number': self.number,
            'kind': self.kind,
            'issuer': self.issuer_code,
            'issue_date': self.issue_date.isoformat(),
            'due_date': self.due_date.isoformat(),
            'currency': self.currency,
            'line_count': len(self.lines),
            'subtotal': str(self.subtotal),
            'discount': str(self.discount),
            'grand_total': str(self.grand_total),
            'total_weight_kg': str(self.total_weight_kg),
            'order_number': self.order_number,
            'shipment_id': self.shipment_id,
            'revises': self.revises,
            'anomaly': self.anomaly,
            'lookalike_of': self.lookalike_of,
            'pay_to': self.pay_to,
            'sender': self.sender,
        }
