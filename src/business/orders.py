"""The two things that exist before any invoice does.

A purchase order is Moty asking for components. A shipment is those
components actually moving. Every invoice in the corpus points back at one
of these, which is what makes the set a chain instead of a pile.
"""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class OrderLine:
    code: str
    description: str
    quantity: int
    agreed_price: Decimal

    @property
    def value(self):
        return Decimal(f'{self.quantity * self.agreed_price:.2f}')


@dataclass
class PurchaseOrder:
    number: str
    raised_on: object
    required_by: object
    factory_code: str
    lines: list = field(default_factory=list)

    @property
    def value(self):
        return Decimal(f'{sum(line.value for line in self.lines):.2f}')


@dataclass
class Shipment:
    identifier: str
    factory_code: str
    carrier_code: str
    mode: str
    departed_on: object
    arrived_on: object
    origin: str
    destination: str
    container: str
    weight_kg: Decimal
    volume_m3: Decimal
    covers: list = field(default_factory=list)
    vessel: str = ''
    #: How it travels: FCL, LCL or air. Empty in the small test runs,
    #: which only know sea and air.
    load: str = ''
    #: The day's dollar rate the load was chosen at.
    fx: Decimal = Decimal('5.40')
    #: The containers booked, for FCL.
    boxes: tuple = ()
    #: The goods' value in dollars, which storage is charged on.
    cif_usd: Decimal = Decimal(0)

    @property
    def transit_days(self):
        return (self.arrived_on - self.departed_on).days


@dataclass
class Dispatch:
    """What one factory actually put on one shipment, for one order.

    A partial dispatch sends less than the order asked for, so the order
    stays open and is finished by a later one.
    """
    order_number: str
    shipment_id: str
    lines: list = field(default_factory=list)
