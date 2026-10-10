"""Compose one invoice for one issuer, drawing its numbers from pricing.py.

Every extra the supplier charges for, tooling or demurrage, is a line on the
page. Nothing is added to the subtotal that a reader cannot see.
"""

from datetime import date, timedelta
from decimal import Decimal

import catalogue
import pricing
from invoice import Invoice, Line, ZERO

PORTS = (
    ('Ningbo', 'Santos'), ('Shanghai', 'Santos'), ('Shenzhen', 'Itajai'),
    ('Busan', 'Santos'), ('Ho Chi Minh City', 'Santos'),
    ('Nhava Sheva', 'Santos'), ('Hong Kong', 'Paranagua'),
)

CONTAINERS = ('20GP', '40GP', '40HC')

# Where each factory actually ships from. An Incoterm names a real port.
LOADING_PORT = {
    'NCL': 'Ningbo',
    'SBP': 'Shantou',
    'GZV': 'Nansha',
    'HCV': 'Busan',
    'BDT': 'Cat Lai',
    'ARL': 'Nhava Sheva',
}


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
        incoterm=f'{factory.incoterm} {LOADING_PORT[factory.code]}',
    )


def freight_invoice(carrier, seed):
    """A transport invoice: the move itself, then the surcharges."""
    rng = pricing.seeded(seed)
    issued = _issue_date(rng)
    origin, destination = rng.choice(PORTS)
    container = rng.choice(CONTAINERS)

    # Air moves small, dense consignments. Sea and road move whole containers.
    span = (90, 1400) if carrier.mode == 'air' else (1800, 21000)
    weight = Decimal(f'{rng.uniform(*span):.1f}')
    volume = Decimal(f'{float(weight) / rng.uniform(190, 330):.2f}')

    base = {'ocean': 1850.0, 'air': 4.35, 'road': 1420.0}[carrier.mode]
    rate = pricing.freight_rate(rng, base, carrier.price_bias,
                                carrier.price_spread)

    if carrier.mode == 'air':
        chargeable = Decimal(f'{max(float(weight), float(volume) * 167):.1f}')
        main = Line(
            description=f'Air freight {origin} to {destination}, chargeable weight',
            quantity=chargeable,
            unit_price=rate,
            unit='kg',
            weight_kg=weight,
            volume_m3=volume,
        )
    else:
        main = Line(
            description=f'{carrier.mode.title()} freight {origin} to {destination}, {container}',
            quantity=Decimal(rng.choice((1, 1, 1, 2))),
            unit_price=rate,
            unit='container',
            weight_kg=weight,
            volume_m3=volume,
        )

    lines = [main]
    for name in carrier.surcharges:
        if rng.random() < 0.82:
            lines.append(_service_line(
                name, pricing.money(rng.uniform(55, 980))))

    if rng.random() < 0.25:
        days = rng.randint(2, 11)
        lines.append(_service_line(
            f'Demurrage, {days} days',
            pricing.money(days * rng.uniform(48, 135))))

    return Invoice(
        number=_number(rng, carrier, issued),
        issue_date=issued,
        due_date=issued + timedelta(days=rng.choice((15, 21, 30))),
        issuer_code=carrier.code,
        lines=lines,
        reference=_booking(rng, carrier),
        shipment={
            'origin': origin,
            'destination': destination,
            'container': container,
            'weight_kg': str(weight),
            'volume_m3': str(volume),
            'vessel': _vessel(rng, carrier),
        },
    )


def invoice_for(issuer, seed):
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


def _vessel(rng, carrier):
    if carrier.mode == 'air':
        return f'Flight {carrier.code}{rng.randint(100, 899)}'
    if carrier.mode == 'road':
        return f'Truck {rng.choice("ABCDEFG")}{rng.randint(100, 999)}'
    names = ('Ever Dawn', 'Pacific Lotus', 'Santos Express',
             'Nordic Trader', 'Blue Meridian', 'Hanjin Star')
    return f'MV {rng.choice(names)} / voy. {rng.randint(10, 89)}E'
