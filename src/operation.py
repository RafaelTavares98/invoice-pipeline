"""Eight weeks of Moty buying packaging.

The loop runs one day at a time. Monday raises orders. A factory ships an
order once its lead time has run out, consolidating whatever is ready into
one shipment, and invoices on the day the box leaves. The ocean carrier
invoices the same departure. The truck invoices on arrival in Louveira.

Nothing is drawn from thin air. Every invoice names the order or the
shipment it came from, and `ledger.py` can walk the whole chain back.

A warm start matters: a lead time is 35 to 55 days and the water is another
month, so an order raised inside an eight week window would never arrive.
The simulation therefore opens with a backlog already in production.
"""

from datetime import timedelta
from decimal import Decimal

import catalogue
import defects
import issuers
import lanes
import pricing
from invoice import Invoice, Line, ZERO
from orders import Dispatch, OrderLine, PurchaseOrder, Shipment

WEEKS = 8
BACKLOG_WEEKS = 13          # long enough for the oldest orders to land
ORDERS_PER_MONDAY = (2, 5)
WAIT_DAYS = 7               # how long one lonely order waits for company
PARTIAL_CHANCE = 0.15
AIR_CHANCE_WHEN_LATE = 0.55
DEMURRAGE_CHANCE = 0.18


class Operation:
    """One run of the business. Build it, call `run`, read the records."""

    def __init__(self, start, seed=2026):
        self.start = start
        self.rng = pricing.seeded(seed)
        self.orders = []
        self.shipments = []
        self.dispatches = []
        self.invoices = []
        self._open = []         # orders still owing goods
        self._counter = 0

    # ----------------------------------------------------------- the loop

    def run(self):
        first = self.start - timedelta(weeks=BACKLOG_WEEKS)
        last = self.start + timedelta(weeks=WEEKS)
        day = first
        while day < last:
            if day.weekday() == 0:
                self._raise_orders(day)
            self._ship_what_is_ready(day)
            self._deliver_what_arrived(day)
            day += timedelta(days=1)
        self._keep_only_the_window()
        return self

    def _keep_only_the_window(self):
        """The backlog existed so the window would be full. Its paperwork
        from before the window is not part of the corpus."""
        last = self.start + timedelta(weeks=WEEKS)
        self.invoices = [i for i in self.invoices
                         if self.start <= i.issue_date < last]

    # --------------------------------------------------------- the orders

    def _raise_orders(self, day):
        for _ in range(self.rng.randint(*ORDERS_PER_MONDAY)):
            factory = self.rng.choice(issuers.FACTORIES)
            order = self._order_for(factory, day)
            self.orders.append(order)
            self._open.append({'order': order, 'factory': factory,
                               'owing': {l.code: l.quantity for l in order.lines},
                               'ready_on': day + timedelta(
                                   days=self._lead(factory))})

    def _order_for(self, factory, day):
        self._counter += 1
        parts = self._parts_for(factory)
        lines = [
            OrderLine(
                code=part.code,
                description=part.description,
                quantity=pricing.order_quantity(self.rng, part),
                agreed_price=pricing.unit_price(
                    self.rng, part, factory.price_bias,
                    factory.price_spread, part.pack_size),
            )
            for part in parts
        ]
        # Moty promises itself the goods by the promised lead time plus a
        # normal crossing plus ten days of slack. A factory that slips
        # eats that slack, and then the box has to fly.
        lane = lanes.lane_for(factory.code)
        promised = factory.lead_days + sum(lane.ocean_days) // 2 + 10
        return PurchaseOrder(
            number=f'PO-{41000 + self._counter}',
            raised_on=day,
            required_by=day + timedelta(days=promised),
            factory_code=factory.code,
            lines=lines,
        )

    def _parts_for(self, factory):
        pool = [part for family in factory.families
                for part in catalogue.BY_FAMILY.get(family, [])]
        count = min(len(pool), self.rng.choices(
            (1, 2, 3, 4), weights=(20, 34, 28, 18))[0])
        return self.rng.sample(pool, count)

    def _lead(self, factory):
        """Promised lead time, plus the slip that actually happens."""
        slip = self.rng.choices((0, 3, 7, 14), weights=(55, 25, 14, 6))[0]
        return factory.lead_days + slip

    # ------------------------------------------------------- the shipping

    def _ship_what_is_ready(self, day):
        ready = [held for held in self._open if held['ready_on'] <= day]
        if not ready:
            return
        by_factory = {}
        for held in ready:
            by_factory.setdefault(held['factory'].code, []).append(held)

        for code, group in by_factory.items():
            if not self._worth_sailing(day, group):
                continue
            self._dispatch(day, issuers.by_code(code), group)

    def _worth_sailing(self, day, group):
        """A container costs the same half full, so the factory waits.

        It stops waiting once two orders are ready, or once the oldest one
        has been sitting for a week.
        """
        if len(group) >= 2:
            return True
        waited = (day - min(held['ready_on'] for held in group)).days
        return waited >= WAIT_DAYS

    def _dispatch(self, day, factory, group):
        dispatches, weight = self._pack(group)
        if not dispatches:
            return

        mode = ('air' if self._would_miss(day, factory, group)
                and self.rng.random() < AIR_CHANCE_WHEN_LATE else 'ocean')
        shipment = self._shipment(day, factory, mode, dispatches, weight)

        self.shipments.append(shipment)
        self.dispatches.extend(dispatches)

        for dispatch in dispatches:
            self._goods_invoice(day, factory, dispatch, shipment)
        self._freight_invoice(day, shipment)

    def _would_miss(self, day, factory, group):
        """Would a normal crossing arrive after the date Moty needs it?"""
        lane = lanes.lane_for(factory.code)
        typical = sum(lane.ocean_days) // 2
        arrival = day + timedelta(days=typical)
        return any(held['order'].required_by < arrival for held in group)

    def _pack(self, group):
        """What leaves today, and what stays owing."""
        dispatches = []
        weight = Decimal('0.00')
        for held in group:
            lines = []
            for code, owing in list(held['owing'].items()):
                part = catalogue.by_code(code)
                sending = owing
                if self.rng.random() < PARTIAL_CHANCE and owing > part.pack_size:
                    packs = max(1, int(owing / part.pack_size) // 2)
                    sending = packs * part.pack_size
                if not sending:
                    continue
                held['owing'][code] = owing - sending
                if held['owing'][code] == 0:
                    del held['owing'][code]
                lines.append((part, sending))
                weight += Decimal(f'{sending * part.grams / 1000:.2f}')
            if lines:
                dispatches.append(Dispatch(held['order'].number, '', lines))
            if not held['owing']:
                self._open.remove(held)
        return dispatches, weight

    def _shipment(self, day, factory, mode, dispatches, weight):
        lane = lanes.lane_for(factory.code)
        carrier_code = (lanes.AIR_CARRIER if mode == 'air'
                        else lanes.ocean_carrier(self.rng, factory.code))
        carrier = issuers.by_code(carrier_code)
        days = lanes.transit_days(self.rng, factory.code, mode)
        identifier = self._booking(carrier, mode)

        for dispatch in dispatches:
            dispatch.shipment_id = identifier

        return Shipment(
            identifier=identifier,
            factory_code=factory.code,
            carrier_code=carrier_code,
            mode=mode,
            departed_on=day,
            arrived_on=day + timedelta(days=days),
            origin=lane.port,
            destination=lanes.DESTINATION,
            container=self.rng.choice(('20GP', '40GP', '40HC'))
            if mode == 'ocean' else 'LOOSE',
            weight_kg=weight or Decimal('1.00'),
            volume_m3=Decimal(f'{float(weight or 1) / self.rng.uniform(190, 330):.2f}'),
            covers=[dispatch.order_number for dispatch in dispatches],
            vessel=self._vessel(carrier, mode),
        )

    # ------------------------------------------------------- the invoices

    def _goods_invoice(self, day, factory, dispatch, shipment):
        order = self._order(dispatch.order_number)
        lines = [
            Line(
                description=part.description,
                quantity=Decimal(quantity),
                unit_price=self._agreed(order, part.code),
                code=part.code,
                unit=part.unit,
                hs_code=part.hs_code,
                weight_kg=Decimal(f'{quantity * part.grams / 1000:.2f}'),
            )
            for part, quantity in dispatch.lines
        ]
        if self.rng.random() < factory.tooling_chance:
            lines.append(_service(
                'Tooling and plate set-up',
                pricing.money(self.rng.uniform(180, 1450))))

        discount = ZERO
        if self.rng.random() < 0.18:
            gross = sum((line.net for line in lines), ZERO)
            discount = pricing.money(float(gross) * self.rng.uniform(0.01, 0.04))

        invoice = Invoice(
            number=self._invoice_number(factory, day),
            issue_date=day,
            due_date=day + timedelta(days=factory.lead_days),
            issuer_code=factory.code,
            lines=lines,
            discount=discount,
            reference=defects.quoted_order(self.rng, order.number, self.orders),
            incoterm=f'{factory.incoterm} {lanes.lane_for(factory.code).port}',
            kind='goods',
            order_number=order.number,
            shipment_id=shipment.identifier,
        )
        self._record(invoice, factory)

    def _freight_invoice(self, day, shipment):
        carrier = issuers.by_code(shipment.carrier_code)
        rate = pricing.freight_rate(
            self.rng,
            {'ocean': 1850.0, 'air': 4.35}[shipment.mode],
            carrier.price_bias, carrier.price_spread)

        if shipment.mode == 'air':
            chargeable = max(shipment.weight_kg,
                             Decimal(f'{float(shipment.volume_m3) * 167:.1f}'))
            main = Line(
                description=f'Air freight {shipment.origin} to '
                            f'{shipment.destination}, chargeable weight',
                quantity=chargeable, unit_price=rate, unit='kg',
                weight_kg=shipment.weight_kg, volume_m3=shipment.volume_m3)
        else:
            main = Line(
                description=f'Ocean freight {shipment.origin} to '
                            f'{shipment.destination}, {shipment.container}',
                quantity=Decimal(1), unit_price=rate, unit='container',
                weight_kg=shipment.weight_kg, volume_m3=shipment.volume_m3)

        lines = [main] + [
            _service(name, pricing.surcharge(self.rng, name))
            for name in carrier.surcharges if self.rng.random() < 0.82
        ]
        self._record(Invoice(
            number=self._invoice_number(carrier, day),
            issue_date=day,
            due_date=day + timedelta(days=self.rng.choice((15, 21, 30))),
            issuer_code=carrier.code,
            lines=lines,
            reference=shipment.identifier,
            kind='freight',
            shipment_id=shipment.identifier,
            shipment=_shipment_box(shipment),
        ), carrier)

    def _deliver_what_arrived(self, day):
        for shipment in self.shipments:
            if shipment.arrived_on != day:
                continue
            self._inland_invoice(day, shipment)

    def _inland_invoice(self, day, shipment):
        carrier = issuers.by_code(lanes.INLAND_CARRIER)
        rate = pricing.freight_rate(self.rng, 1420.0, carrier.price_bias,
                                     carrier.price_spread)
        lines = [Line(
            description=f'Road haulage {lanes.DESTINATION} to {lanes.INLAND}, '
                        f'{shipment.container}',
            quantity=Decimal(1), unit_price=rate, unit='trip',
            weight_kg=shipment.weight_kg, volume_m3=shipment.volume_m3)]
        lines += [
            _service(name, pricing.surcharge(self.rng, name))
            for name in carrier.surcharges if self.rng.random() < 0.6
        ]
        if self.rng.random() < DEMURRAGE_CHANCE:
            days = self.rng.randint(2, 11)
            lines.append(_service(
                f'Port storage, {days} days',
                pricing.money(days * self.rng.uniform(48, 135))))

        self._record(Invoice(
            number=self._invoice_number(carrier, day),
            issue_date=day,
            due_date=day + timedelta(days=self.rng.choice((15, 21, 30))),
            issuer_code=carrier.code,
            lines=lines,
            reference=shipment.identifier,
            kind='freight',
            shipment_id=shipment.identifier,
            shipment=_shipment_box(shipment, inland=True),
        ), carrier)

    def _record(self, invoice, issuer):
        """File the invoice, and whatever the supplier got wrong about it."""
        self.invoices.append(invoice)
        for extra in defects.after(self.rng, invoice, issuer,
                                   self._invoice_number):
            self.invoices.append(extra)

    # ----------------------------------------------------------- plumbing

    def _order(self, number):
        for order in self.orders:
            if order.number == number:
                return order
        raise KeyError(number)

    def _agreed(self, order, code):
        for line in order.lines:
            if line.code == code:
                return line.agreed_price
        raise KeyError(code)

    def _invoice_number(self, issuer, day):
        self._counter += 1
        return f'{issuer.number_prefix}-{day.year}-{3000 + self._counter}'

    def _booking(self, carrier, mode):
        self._counter += 1
        if mode == 'air':
            return (f'AWB {self.rng.randint(100, 999)}-'
                    f'{self.rng.randint(10000000, 99999999)}')
        return f'B/L {carrier.code}{7000000 + self._counter}'

    def _vessel(self, carrier, mode):
        if mode == 'air':
            return f'Flight {carrier.code}{self.rng.randint(100, 899)}'
        names = ('Ever Dawn', 'Pacific Lotus', 'Santos Express',
                 'Nordic Trader', 'Blue Meridian', 'Hanjin Star')
        return f'MV {self.rng.choice(names)} / voy. {self.rng.randint(10, 89)}E'


def _service(description, amount):
    return Line(description=description, quantity=Decimal(1),
                unit_price=amount, unit='lot')


def _shipment_box(shipment, inland=False):
    return {
        'origin': lanes.DESTINATION if inland else shipment.origin,
        'destination': lanes.INLAND if inland else shipment.destination,
        'container': shipment.container,
        'weight_kg': str(shipment.weight_kg),
        'volume_m3': str(shipment.volume_m3),
        'vessel': 'Truck' if inland else shipment.vessel,
    }

