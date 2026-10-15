"""Moty buying packaging, one day at a time.

Monday raises orders. Every Friday a factory ships whatever is ready, in
whole cartons; the load goes FCL or LCL, whichever costs less all in, or
flies when it is late and small enough. The factory invoices the day the
box leaves, and so does the carrier, at the rate card; a CIF factory's
price already carries the freight. On arrival come the Brazilian
documents, or, in the small runs that leave Brazil out, KNG's truck.

Nothing is drawn from thin air. Every invoice names the order or the
shipment it came from, and `ledger.py` can walk the whole chain back.

A warm start matters: a lead time is 35 to 55 days and the water is another
month, so an order raised inside a short run would never arrive. The run
therefore opens with a backlog already in production, and keeps only the
paperwork dated inside its period.
"""

from datetime import timedelta
from decimal import Decimal

from business import catalogue
from business import tariffs
from simulation import anomalies, customs, defects, fx, lookalikes, newcomers
from simulation import freight as charges
from business import issuers
from business import lanes
from simulation import pricing
from business.invoice import Invoice, Line, ZERO
from business.orders import Dispatch, OrderLine, PurchaseOrder, Shipment

WEEKS = 8
BACKLOG_WEEKS = 13          # long enough for the oldest orders to land
ORDERS_PER_MONDAY = (2, 5)


class Profile:
    """How busy the business is, and for how long it is watched."""

    def __init__(self, weeks, orders_per_monday, anomalies=False, drift=False,
                 brazil=False):
        self.weeks = weeks
        self.orders_per_monday = orders_per_monday
        #: Whether errors, and their honest twins, are planted
        #: for a model to catch.
        self.anomalies = anomalies
        #: Whether the anomalies change halfway, for the monitoring scenario.
        self.drift = drift
        #: Whether the Brazilian import cost is modelled: the duty statement,
        #: the broker's invoice, and a Brazilian truck billing in reais.
        self.brazil = brazil


#: The quiet importer the tests pin: about thirteen invoices a week.
DEFAULT = Profile(WEEKS, ORDERS_PER_MONDAY)

#: The inbox in the README's story: about a hundred invoices a week.
BUSY = Profile(8, (40, 56), anomalies=True, brazil=True)

#: A full year of the busy inbox, to train and test a model on.
YEAR = Profile(52, (36, 50), anomalies=True, brazil=True)

#: Half a year in which the anomalies change halfway: more freight overbilling,
#: more accounts not on file, and unmatched vendors billing as freight.
DRIFT = Profile(26, (36, 50), anomalies=True, drift=True, brazil=True)

#: The real run: 1 January to the run date, the length set by `until`.
#: A mid-sized importer, so the backlog is a few hundred mails.
BACKLOG = Profile(52, (2, 4), anomalies=True, brazil=True)

PROFILES = {'default': DEFAULT, 'busy': BUSY, 'year': YEAR, 'drift': DRIFT,
            'backlog': BACKLOG}

#: How many invoices after a recorded bank change still look suspicious.
CHANGE_WATCH_INVOICES = 3

#: The share of partial-delivery orders that also look like a split. Real
#: partials are common; this keeps twins about as many as the anomalies.
PARTIAL_TWIN_SHARE = 0.2

SHIPPING_WEEKDAY = 4        # Friday: the week's ready orders leave together
PARTIAL_CHANCE = 0.15
AIR_CHANCE_WHEN_LATE = 0.55
#: The most a late load may weigh, chargeable, and still fly. Above it the
#: air bill passes the goods' own value, and the load sails late instead.
AIR_MAX_CHARGEABLE_KG = Decimal('1500')
DEMURRAGE_CHANCE = 0.18


class Operation:
    """One run of the business. Build it, call `run`, read the records."""

    def __init__(self, start, seed=2026, profile=DEFAULT, until=None):
        self.start = start
        self.profile = profile
        #: The run date. Nothing is dated after it; without it the run
        #: lasts the profile's weeks.
        self.until = until
        #: Anomalies roll their own dice, so turning them on never moves
        #: any other draw of the simulation.
        self._anomaly_rng = pricing.seeded(seed + 1)
        self._twin_rng = pricing.seeded(seed + 2)
        self._event_rng = pricing.seeded(seed + 3)
        self.rng = pricing.seeded(seed)
        self.orders = []
        self.shipments = []
        self.dispatches = []
        self.invoices = []
        self._open = []         # orders still owing goods
        self._counter = 0

        #: The records behind the honest twins, and the vendor master's
        #: history. Empty unless the profile plants anomalies.
        self.joined = []
        self.vendor_changes = []
        self.amendments = []
        self.receipts = []
        self._received = {}     # (order, code, shipment) -> accepted quantity
        self._direct = []       # receipts for goods that came without a shipment
        self._accounts = {}     # issuer code -> (new account, changed on)
        self._since_change = {}  # issuer code -> invoices since the change
        self._events = {}
        #: The simulated PTAX series, and the tariff changes published
        #: during the run. Used only when the profile models Brazil.
        self._fx = {}
        self.tariff_changes = []
        self._seed = seed
        self._customs_rng = pricing.seeded(seed + 4)

    @property
    def last_day(self):
        """The first day after the run: the run date's next day, or the
        end of the profile's weeks."""
        if self.until is not None:
            return self.until + timedelta(days=1)
        return self.start + timedelta(weeks=self.profile.weeks)

    @property
    def horizon(self):
        """The end of the year the events are drawn over. A run date only
        cuts that year short; it never changes what happens before it, so
        a later run date keeps every earlier document, number for number."""
        if self.until is not None:
            return self.start.replace(year=self.start.year + 1)
        return self.last_day

    @property
    def days(self):
        return (self.horizon - self.start).days

    @property
    def midpoint(self):
        return self.start + timedelta(days=self.days // 2)

    # ----------------------------------------------------------- the loop

    def run(self):
        first = self.start - timedelta(weeks=BACKLOG_WEEKS)
        last = self.last_day
        if self.profile.anomalies:
            self._schedule()
        if self.profile.brazil:
            self._fx = fx.series(last + timedelta(days=90), self._seed)
            self.tariff_changes = self._tariff_changes()
        day = first
        while day < last:
            if day.weekday() == 0:
                self._raise_orders(day)
            self._ship_what_is_ready(day)
            self._deliver_what_arrived(day)
            for event in self._events.pop(day, []):
                event[0](day, *event[1:])
            day += timedelta(days=1)
        self._keep_only_the_period()
        if self.profile.anomalies:
            self._mark_partial_deliveries()
            self.receipts = self._goods_receipts()
        return self

    # ------------------------------------------------- the business events

    def _at(self, day, *event):
        if day < self.last_day:
            self._events.setdefault(day, []).append(event)

    def _how_many(self, per_year):
        rng = self._event_rng
        return int(self.days / 364 * per_year + rng.random())

    def _some_day(self, share=0.75):
        span = int(self.days * share)
        return self.start + timedelta(days=self._event_rng.randint(0, span))

    def _schedule(self):
        """Put the vendor-master events on the calendar."""
        for index in range(self._how_many(anomalies.UNMATCHED_PER_YEAR)):
            self._at(self._some_day(), self._unmatched_joins, index)
        for index in range(self._how_many(3)):
            self._at(self._some_day(), self._supplier_joins, index)
        for _ in range(self._how_many(3)):
            self._at(self._some_day(), self._account_mismatchs)
        day = self.start + timedelta(days=3)
        while day < self.last_day:
            self._at(day, self._rent_is_billed)
            day += timedelta(days=lookalikes.RECURRING_DAYS)

    def _unmatched_joins(self, day, index):
        rng = self._event_rng
        issuer = newcomers.unmatched(rng, index)
        self.joined.append({'code': issuer.code, 'onboarded_on': day,
                            'has_order': False})
        when = day
        for _ in range(rng.randint(3, 6)):
            when += timedelta(days=rng.randint(7, 20))
            self._at(when, self._unmatched_bills, issuer)

    def _unmatched_bills(self, day, issuer):
        rng = self._event_rng
        freight = self.profile.drift and day >= self.midpoint
        services = (newcomers.UNMATCHED_FREIGHT_SERVICES if freight
                    else newcomers.UNMATCHED_SERVICES)
        amount = Decimal(rng.randint(30, 120) * 100)
        self.invoices.append(Invoice(
            number=self._invoice_number(issuer, day),
            issue_date=day,
            due_date=day + timedelta(days=30),
            issuer_code=issuer.code,
            lines=[_service(rng.choice(services), amount)],
            kind='freight' if freight else 'goods',
            anomaly='unmatched_vendor',
            sender=issuers.address_for(issuer),
        ))

    def _supplier_joins(self, day, index):
        rng = self._event_rng
        issuer, template = newcomers.new_supplier(rng, index)
        self.joined.append({'code': issuer.code, 'onboarded_on': day,
                            'has_order': True})
        self._at(day + timedelta(days=rng.randint(1, 5)),
                 self._supplier_is_ordered, issuer, template)

    def _supplier_is_ordered(self, day, issuer, template):
        rng = self._event_rng
        self._counter += 1
        pool = [part for family in template.families
                for part in catalogue.BY_FAMILY.get(family, [])]
        lines = []
        for part in rng.sample(pool, min(len(pool), rng.randint(1, 3))):
            quantity = pricing.order_quantity(rng, part)
            lines.append(OrderLine(
                code=part.code, description=part.description,
                quantity=quantity,
                agreed_price=pricing.unit_price(
                    rng, part, template.price_bias, template.price_spread,
                    part.pack_size)))
        order = PurchaseOrder(number=f'PO-{41000 + self._counter}',
                              raised_on=day,
                              required_by=day + timedelta(days=45),
                              factory_code=issuer.code, lines=lines)
        self.orders.append(order)
        self._at(day + timedelta(days=rng.randint(14, 30)),
                 self._supplier_bills, issuer, order)

    def _supplier_bills(self, day, issuer, order):
        sent = [(catalogue.by_code(l.code), l.quantity) for l in order.lines]
        self.dispatches.append(Dispatch(order.number, '', sent))
        for part, quantity in sent:
            self._direct.append({'order_number': order.number,
                                 'code': part.code, 'shipment_id': '',
                                 'quantity': Decimal(quantity),
                                 'received_on': day})
        self.invoices.append(Invoice(
            number=self._invoice_number(issuer, day),
            issue_date=day,
            due_date=day + timedelta(days=30),
            issuer_code=issuer.code,
            lines=[Line(description=l.description,
                        quantity=Decimal(l.quantity),
                        unit_price=l.agreed_price, code=l.code)
                   for l in order.lines],
            reference=order.number,
            kind='goods',
            order_number=order.number,
            lookalike_of='unmatched_vendor',
            sender=issuers.address_for(issuer),
        ))

    def _account_mismatchs(self, day):
        """A supplier moves bank, says so from its known address, and the
        desk records it after a call-back to the number on file."""
        rng = self._event_rng
        candidates = [i for i in issuers.ALL_ISSUERS
                      if i.bank_line and i.code not in self._accounts]
        if not candidates:
            return
        issuer = rng.choice(candidates)
        new = newcomers._account(rng)
        self.vendor_changes.append({
            'code': issuer.code, 'field': 'bank_account',
            'old_value': issuer.bank_line, 'new_value': new,
            'changed_on': day, 'requested_by': issuers.address_for(issuer),
            'verified': 'call-back to the number on file'})
        self._accounts[issuer.code] = (new, day)

    def _rent_is_billed(self, day):
        carrier = issuers.by_code(lookalikes.RECURRING['issuer'])
        self.invoices.append(Invoice(
            number=self._invoice_number(carrier, day),
            issue_date=day,
            due_date=day + timedelta(days=15),
            issuer_code=carrier.code,
            lines=[_service(lookalikes.RECURRING['description'],
                            lookalikes.RECURRING['amount'])],
            reference=f'Contract KNG-WH-2026, {day:%B %Y}',
            kind='freight',
            lookalike_of='near_duplicate',
        ))

    def _mark_partial_deliveries(self):
        """An order shipped in parts is billed in parts. When the parts each
        sit under the approval limit and add to more, they look exactly
        like split billing. Each one ties to its own shipment."""
        by_order = {}
        for invoice in self.invoices:
            if (invoice.kind == 'goods' and invoice.shipment_id
                    and not invoice.anomaly and not invoice.lookalike_of
                    and invoice.order_number):
                by_order.setdefault(invoice.order_number, []).append(invoice)
        for number in sorted(by_order):
            group = by_order[number]
            if len({i.shipment_id for i in group}) < 2:
                continue
            totals = [i.grand_total for i in group]
            if (max(totals) < anomalies.APPROVAL_LIMIT
                    and sum(totals) > anomalies.APPROVAL_LIMIT
                    and self._twin_rng.random() < PARTIAL_TWIN_SHARE):
                for invoice in group:
                    invoice.lookalike_of = 'split_billing'

    def _goods_receipts(self):
        """What the dock signed for, line by line. Usually what was sent;
        an accepted over-delivery is signed for in full."""
        arrived = {s.identifier: s.arrived_on for s in self.shipments}
        rows = []
        for dispatch in self.dispatches:
            if not dispatch.shipment_id:
                continue
            for part, quantity in dispatch.lines:
                key = (dispatch.order_number, part.code, dispatch.shipment_id)
                rows.append({'order_number': dispatch.order_number,
                             'code': part.code,
                             'shipment_id': dispatch.shipment_id,
                             'quantity': self._received.get(key, Decimal(quantity)),
                             'received_on': arrived[dispatch.shipment_id]})
        return rows + self._direct

    def _keep_only_the_period(self):
        """The warm start existed so the period would be full. Its
        paperwork from before the period is not part of the corpus."""
        self.invoices = [i for i in self.invoices
                         if self.start <= i.issue_date < self.last_day]

    # --------------------------------------------------------- the orders

    def _raise_orders(self, day):
        for _ in range(self.rng.randint(*self.profile.orders_per_monday)):
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
        # Moty promises itself the goods by the promised lead time, a week
        # for the Friday sailing, a normal crossing and ten days of slack.
        # A factory that slips eats that slack, and then the box flies.
        lane = lanes.lane_for(factory.code)
        promised = factory.lead_days + 7 + sum(lane.ocean_days) // 2 + 10
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
        """A factory ships every Friday whatever is ready that week."""
        return day.weekday() == SHIPPING_WEEKDAY

    def _dispatch(self, day, factory, group):
        dispatches = self._pack(group)
        if not dispatches:
            return

        mode = ('air' if self._would_miss(day, factory, group)
                and self.rng.random() < AIR_CHANCE_WHEN_LATE else 'ocean')
        shipment = self._loaded(day, factory, mode, dispatches)

        self.shipments.append(shipment)
        self.dispatches.extend(dispatches)

        for dispatch in dispatches:
            self._goods_invoice(day, factory, dispatch, shipment)
        if not factory.incoterm.startswith('CIF'):
            # A CIF price already carries the ocean freight.
            self._rate_card_freight(day, shipment)

    def _loaded(self, day, factory, mode, dispatches):
        """The shipment as the rate card books it: its room and weight in
        whole cartons, by air when late, else FCL or LCL, whichever costs
        less all in."""
        m3 = kg = Decimal(0)
        for dispatch in dispatches:
            for part, quantity in dispatch.lines:
                cartons = -(-quantity // part.carton.units)
                m3 += part.carton.m3 * cartons
                kg += part.carton.kg * cartons
        m3, kg = m3.quantize(Decimal('0.01')), kg.quantize(Decimal('0.01'))
        rate = self._fx.get(day, fx.OPENING_RATE)
        value = sum((self._agreed(self._order(d.order_number), part.code)
                     * quantity for d in dispatches
                     for part, quantity in d.lines), Decimal(0))
        if mode == 'air' and max(kg, m3 * charges.AIR_KG_PER_M3) \
                > AIR_MAX_CHARGEABLE_KG:
            # Too big to fly: it sails late.
            mode = 'ocean'
        if mode == 'air':
            load, carrier_code, boxes = 'air', lanes.AIR_CARRIER, ()
        else:
            fcl, lcl = charges.all_in_usd(m3, kg, rate, value)
            if fcl <= lcl:
                load = 'FCL'
                carrier_code = lanes.ocean_carrier(self.rng, factory.code)
                boxes = tuple(charges.containers_for(m3, kg))
            else:
                load, carrier_code, boxes = 'LCL', lanes.AIR_CARRIER, ()
        carrier = issuers.by_code(carrier_code)
        identifier = self._booking(carrier, mode)
        for dispatch in dispatches:
            dispatch.shipment_id = identifier
        lane = lanes.lane_for(factory.code)
        return Shipment(
            identifier=identifier, factory_code=factory.code,
            carrier_code=carrier_code, mode=mode, departed_on=day,
            arrived_on=day + timedelta(days=lanes.transit_days(
                self.rng, factory.code, mode)),
            origin=lane.port, destination=lanes.DESTINATION,
            container={'FCL': ' + '.join(boxes), 'LCL': 'LCL',
                       'air': 'LOOSE'}[load],
            weight_kg=kg, volume_m3=m3,
            covers=[dispatch.order_number for dispatch in dispatches],
            vessel=self._vessel(carrier, mode), load=load, fx=rate,
            boxes=boxes, cif_usd=value.quantize(Decimal('0.01')))

    def _rate_card_freight(self, day, shipment):
        """The carrier's invoice at the rate card, and its surcharges."""
        carrier = issuers.by_code(shipment.carrier_code)
        bill = {'FCL': charges.fcl_invoice, 'LCL': charges.lcl_invoice,
                'air': charges.air_invoice}[shipment.load](
            carrier, day, shipment.origin, shipment.volume_m3,
            shipment.weight_kg, number=self._invoice_number(carrier, day))
        bill.reference = bill.shipment_id = shipment.identifier
        bill.shipment['vessel'] = shipment.vessel
        bill.due_date = day + timedelta(days=self.rng.choice((15, 21, 30)))
        bill.lines += [_service(name, pricing.surcharge(self.rng, name))
                       for name in carrier.surcharges
                       if self.rng.random() < 0.82]
        self._record(bill, carrier)

    def _would_miss(self, day, factory, group):
        """Would a normal crossing arrive after the date Moty needs it?"""
        lane = lanes.lane_for(factory.code)
        typical = sum(lane.ocean_days) // 2
        arrival = day + timedelta(days=typical)
        return any(held['order'].required_by < arrival for held in group)

    def _pack(self, group):
        """What leaves today, and what stays owing."""
        dispatches = []
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
            if lines:
                dispatches.append(Dispatch(held['order'].number, '', lines))
            if not held['owing']:
                self._open.remove(held)
        return dispatches

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

    def _deliver_what_arrived(self, day):
        for shipment in self.shipments:
            if shipment.arrived_on != day:
                continue
            if self.profile.brazil:
                self._clear_in_brazil(day, shipment)
            else:
                self._inland_invoice(day, shipment)

    # ------------------------------------------------------ Brazil, in reais

    def _tariff_changes(self):
        """The tariff changes published during the run.

        Gecex publishes several resolutions a year, not one. With a
        single change on a single NCM, a declaration that honestly
        carries a new rate almost never happens, and the model never
        learns the difference between a rate that changed and a rate
        that was keyed wrong. All of these are simulated; the first is
        the aluminium tube cut the tests pin.
        """
        from business.tariffs import Rate

        days = self.profile.weeks * 7
        planned = (
            ('7612.10.00', Decimal('0.112'), days * 2 // 5),
            ('3923.30.00', Decimal('0.144'), days * 3 // 5),
            ('7010.90.22', Decimal('0.072'), days * 4 // 5),
        )
        changes = []
        for ncm, new_ii, after in planned:
            base = tariffs.rate_on(ncm, self.start)
            changes.append(Rate(ncm, new_ii, base.ipi, base.cofins,
                                self.start + timedelta(days=after),
                                'simulated Gecex resolution'))
        return changes

    def _on_shipment(self, shipment, kind, currency='USD'):
        """The live documents of one kind on a shipment: a revision
        replaces what it revises, and a resend counts once."""
        found = {}
        for invoice in self.invoices:
            if (invoice.shipment_id == shipment.identifier
                    and invoice.kind == kind and invoice.currency == currency):
                found[invoice.number] = invoice
        revised = {invoice.revises for invoice in found.values()}
        return [invoice for number, invoice in found.items()
                if number not in revised]

    def _clear_in_brazil(self, day, shipment):
        """The duty statement, the broker's invoice, the local charges, the
        storage and the truck, all on the day the shipment lands in Santos."""
        rng = self._customs_rng
        broker = issuers.BROKER
        goods = self._on_shipment(shipment, 'goods')
        freight = self._on_shipment(shipment, 'freight')
        rate = self._fx[day]
        slip = anomalies.duty_slip(rng)
        statement = customs.statement(
            rng, shipment, goods, freight, day, rate,
            self._invoice_number(broker, day), self.tariff_changes, slip)
        if slip is not None:
            statement.anomaly = 'duty_rate_wrong'
        else:
            lookalikes.at_customs(rng, statement, self.tariff_changes)
        self._record(statement, broker)

        bill = customs.broker_invoice(
            rng, shipment, day, self._invoice_number(broker, day))
        anomalies.at_customs(rng, bill)
        if not bill.anomaly:
            lookalikes.at_customs(rng, bill, self.tariff_changes)
        self._record(bill, broker)
        cargo = sum((invoice.grand_total for invoice in goods), Decimal(0)) * rate
        self._santos_bills(day, shipment, goods, freight, rate)
        trucker = issuers.TRUCKER
        self._record(customs.trucker_invoice(
            rng, shipment, day, cargo, self._invoice_number(trucker, day),
            _shipment_box(shipment, inland=True)), trucker)

    def _santos_bills(self, day, shipment, goods, freight, rate):
        """The carrier's or forwarder's Santos office bills its local
        charges, and the bonded terminal bills the first storage period on
        the CIF value."""
        agent = issuers.by_code(shipment.carrier_code)
        if shipment.load == 'FCL':
            local = charges.local_charges(
                agent, day, containers=list(shipment.boxes),
                number=self._invoice_number(agent, day),
                shipment_id=shipment.identifier, fx=rate)
        else:
            local = charges.local_charges(
                agent, day, wm=charges.wm(shipment.volume_m3, shipment.weight_kg),
                number=self._invoice_number(agent, day),
                shipment_id=shipment.identifier, fx=rate)
        self._record(local, agent)
        cif = (sum((i.grand_total for i in goods), Decimal(0))
               + sum((i.grand_total for i in freight), Decimal(0))) * rate
        terminal = issuers.TERMINAL
        self._record(charges.storage_invoice(
            day, cif, containers=list(shipment.boxes) or None,
            number=self._invoice_number(terminal, day),
            shipment_id=shipment.identifier), terminal)

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
        extras = []
        if self.profile.anomalies:
            extras = self._plant(invoice, issuer)
        self.invoices.append(invoice)
        for extra in defects.after(self.rng, invoice, issuer,
                                   self._invoice_number):
            if extra.revises:
                # A revision or credit note changes the figures, so the
                # record that made the original honest no longer fits it.
                extra.lookalike_of = ''
            self.invoices.append(extra)
        self.invoices.extend(extras)

    def _first_after_change(self, code):
        """The first few invoices into a new account are the ones a desk
        double-checks; after that the account is simply the account."""
        seen = self._since_change.get(code, 0)
        self._since_change[code] = seen + 1
        return seen < CHANGE_WATCH_INVOICES

    def _plant(self, invoice, issuer):
        """Maybe an anomaly, else maybe an honest twin. Returns any extra
        invoices either one created."""
        changed = self._accounts.get(issuer.code)
        if changed:
            invoice.pay_to = changed[0]
        boost = 2.0 if self.profile.drift and invoice.issue_date >= self.midpoint else 1.0
        extras = anomalies.apply(self._anomaly_rng, invoice, issuer,
                                 self._invoice_number, _service, boost)
        if invoice.anomaly or any(e.anomaly for e in extras):
            return extras
        if changed and self._first_after_change(issuer.code):
            invoice.lookalike_of = 'account_mismatch'
            invoice.sender = issuers.address_for(issuer)
            return extras
        order = (self._order(invoice.order_number)
                 if invoice.kind == 'goods' and invoice.order_number else None)
        twins, records = lookalikes.apply(self._twin_rng, invoice, order, issuer,
                                          self._invoice_number, _service)
        if 'amendment' in records:
            self.amendments.append(records['amendment'])
        for code, quantity in records.get('received', {}).items():
            self._received[(invoice.order_number, code, invoice.shipment_id)] = quantity
        return extras + twins

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

