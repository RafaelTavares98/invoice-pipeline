"""Compose one invoice for one issuer, drawing its numbers from pricing.py.

Every extra the supplier charges for, tooling or a surcharge, is a line on
the page. Nothing is added to the subtotal that a reader cannot see.
"""

from datetime import date, timedelta
from decimal import Decimal

from business import catalogue, lanes
from simulation import pricing
from business.invoice import Invoice, Line, ZERO


def goods_invoice(factory, seed):
    """A components invoice from one of the factories."""
    rng = pricing.seeded(seed)
    issued = _issue_date(rng)

    lines = []
    for part in _parts_for(rng, factory):
        quantity = pricing.order_quantity(rng, part)
        lines.append(Line(
            description=part.description,
            quantity=Decimal(quantity),
            unit_price=pricing.unit_price(
                rng, part, factory.price_bias, factory.price_spread, quantity),
            code=part.code,
            unit=part.unit,
            hs_code=part.hs_code,
            weight_kg=Decimal(f'{quantity * part.grams / 1000:.2f}'),
        ))

    if rng.random() < factory.tooling_chance:
        lines.append(_service_line(
            'Tooling and plate set-up', pricing.money(rng.uniform(180, 1450))))
    if rng.random() < 0.18:
        lines.append(_service_line(
            'Pre-production samples, courier',
            pricing.money(rng.uniform(45, 190))))

    discount = ZERO
    if rng.random() < 0.22:
        gross = sum((line.net for line in lines), ZERO)
        discount = pricing.money(float(gross) * rng.uniform(0.01, 0.04))

    return Invoice(
        number=_number(rng, factory, issued),
        issue_date=issued,
        due_date=issued + timedelta(days=factory.lead_days),
        issuer_code=factory.code,
        lines=lines,
        discount=discount,
        reference=f'PO-{rng.randint(41000, 48999)}',
        incoterm=f'{factory.incoterm} {lanes.lane_for(factory.code).port}',
    )


def freight_invoice(carrier, seed):
    """A transport invoice at the rate card, then the surcharges: a line
    bills full containers, the forwarder shared space or a flight, and KNG
    a truck from Santos in the runs without Brazil."""
    from simulation import freight

    rng = pricing.seeded(seed)
    issued = _issue_date(rng)
    number = _number(rng, carrier, issued)
    origin = rng.choice([lane.port for lane in lanes.LANES.values()])
    density = rng.uniform(150, 330)

    def cargo(low, high):
        m3 = Decimal(f'{rng.uniform(low, high):.2f}')
        return m3, Decimal(f'{float(m3) * density:.1f}')

    if carrier.mode == 'road':
        bill = _road_haulage(rng, carrier, issued, number)
    elif carrier.mode == 'ocean':
        bill = freight.fcl_invoice(carrier, issued, origin, *cargo(20, 140),
                                   number=number)
    elif rng.random() < 0.5:
        bill = freight.air_invoice(carrier, issued, origin, *cargo(0.4, 4),
                                   number=number)
    else:
        bill = freight.lcl_invoice(carrier, issued, origin, *cargo(2, 14),
                                   number=number)
    if carrier.mode != 'road':
        bill.reference = bill.shipment_id = _booking(rng, carrier)
        bill.shipment['vessel'] = _vessel(rng, carrier,
                                          flying=bill.lines[0].unit == 'kg')
    bill.due_date = issued + timedelta(days=rng.choice((15, 21, 30)))
    bill.lines += [_service_line(name, pricing.money(rng.uniform(55, 980)))
                   for name in carrier.surcharges if rng.random() < 0.82]
    return bill


def _road_haulage(rng, carrier, issued, number):
    """The truck from Santos to Louveira, per trip, in the runs that leave
    the Brazilian documents out."""
    trip = pricing.freight_rate(rng, 1420.0, carrier.price_bias,
                                carrier.price_spread)
    box = rng.choice(('20GP', '40GP', '40HC'))
    weight = Decimal(f'{rng.uniform(1800, 21000):.1f}')
    return Invoice(
        number=number, issue_date=issued, due_date=issued, issuer_code=carrier.code,
        lines=[Line(description=f'Road haulage {lanes.DESTINATION} to '
                                f'{lanes.INLAND}, {box}',
                    quantity=Decimal(1), unit_price=trip, unit='trip')],
        kind='freight', reference=_booking(rng, carrier),
        shipment={'origin': lanes.DESTINATION, 'destination': lanes.INLAND,
                  'container': box, 'weight_kg': str(weight),
                  'volume_m3': f'{float(weight) / 250:.2f}',
                  'vessel': _vessel(rng, carrier)})


def duty_statement(broker, seed):
    """The broker's duty statement for one shipment of goods, in reais."""
    from business.orders import Shipment
    from business import issuers
    from simulation import customs

    rng = pricing.seeded(seed)
    goods = goods_invoice(issuers.FACTORIES[seed % len(issuers.FACTORIES)], seed)
    # By sea: the statement charges AFRMM, which only ocean freight pays.
    freight = freight_invoice(issuers.by_code('MRK'), seed)
    # Nothing is dated after today.
    landed = min(goods.issue_date + timedelta(days=rng.randint(28, 40)),
                 date.today())
    shipment = Shipment(
        identifier=freight.reference, factory_code=goods.issuer_code,
        carrier_code=freight.issuer_code, mode='ocean',
        departed_on=goods.issue_date, arrived_on=landed, origin='Ningbo',
        destination='Santos', container='40GP',
        weight_kg=goods.total_weight_kg, volume_m3=Decimal('30.0'))
    fx = Decimal(f'{rng.uniform(5.1, 5.6):.4f}')
    number = f'{broker.number_prefix}-{landed.year}-{rng.randint(1000, 9899)}'
    return customs.statement(rng, shipment, [goods], [freight], landed, fx,
                             number)


def invoice_for(issuer, seed):
    if issuer.kind == 'broker':
        return duty_statement(issuer, seed)
    builder = goods_invoice if issuer.kind == 'factory' else freight_invoice
    return builder(issuer, seed)


def _service_line(description, amount):
    """A charge billed as one lot, so it reconciles like any other line."""
    return Line(description=description, quantity=Decimal(1),
                unit_price=amount, unit='lot')


def _parts_for(rng, factory):
    pool = []
    for family in factory.families:
        pool.extend(catalogue.BY_FAMILY.get(family, []))
    count = min(len(pool),
                rng.choices((1, 2, 3, 4, 5), weights=(8, 22, 30, 25, 15))[0])
    return rng.sample(pool, count)


def _issue_date(rng):
    start = date(2026, 1, 6)
    return start + timedelta(days=rng.randint(0, 270))


def _number(rng, issuer, issued):
    return f'{issuer.number_prefix}-{issued.year}-{rng.randint(1000, 9899)}'


def _booking(rng, carrier):
    if carrier.mode == 'air':
        return f'AWB {rng.randint(100, 999)}-{rng.randint(10000000, 99999999)}'
    return f'B/L {carrier.code}{rng.randint(1000000, 9999999)}'


def _vessel(rng, carrier, flying=None):
    """The flight, truck or ship the move went on. A forwarder flies some
    loads and ships others, so the load decides, not the carrier."""
    if flying is None:
        flying = carrier.mode == 'air'
    if flying:
        return f'Flight {carrier.code}{rng.randint(100, 899)}'
    if carrier.mode == 'road':
        return f'Truck {rng.choice("ABCDEFG")}{rng.randint(100, 999)}'
    names = ('Ever Dawn', 'Pacific Lotus', 'Santos Express',
             'Nordic Trader', 'Blue Meridian', 'Hanjin Star')
    return f'MV {rng.choice(names)} / voy. {rng.randint(10, 89)}E'
