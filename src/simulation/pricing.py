"""Where the numbers come from.

Two invoices for the same part are almost never identical. A quote sits in a
distribution: lognormal around the catalogue price, shifted by how expensive
that supplier is, and pulled down when the order is large.
"""

import math
import random
from decimal import Decimal


def money(value):
    """Two decimal places, as a Decimal, so the totals add up exactly."""
    return Decimal(f'{value:.2f}')


def unit_price(rng, part, supplier_bias, spread, quantity):
    """One quoted unit price, in the supplier's own currency."""
    centre = part.base_price * supplier_bias * _volume_discount(quantity, part)
    mu = math.log(centre) - (spread ** 2) / 2
    drawn = rng.lognormvariate(mu, spread)
    return _round_to_tick(drawn)


def _volume_discount(quantity, part):
    """Bigger orders cost less per unit, in steps, not continuously."""
    packs = quantity / part.pack_size
    if packs >= 20:
        return 0.86
    if packs >= 10:
        return 0.91
    if packs >= 4:
        return 0.95
    return 1.0


def _round_to_tick(value):
    """Quotes are published at a sane number of decimals, not at random.

    A cap costs fractions of a cent, so forcing every price to two places
    would throw the difference between 0.0615 and 0.0628 away.
    """
    if value >= 1:
        return Decimal(f'{value:.2f}')
    if value >= 0.1:
        return Decimal(f'{value:.3f}')
    return Decimal(f'{value:.4f}')


def order_quantity(rng, part):
    """A whole number of packs.

    A container is paid for whether it is full or not, so a buyer orders
    enough to fill one. Small orders happen, but they are the exception.
    """
    packs = rng.choices(
        (2, 4, 6, 8, 12, 20, 30, 45, 60),
        weights=(6, 9, 12, 14, 16, 16, 13, 9, 5),
    )[0]
    return packs * part.pack_size


#: What each surcharge actually costs, in US dollars per shipment. A
#: documentation fee is not the same size as inland haulage, and drawing
#: both from one wide band makes the freight bill nonsense.
SURCHARGE_BANDS = {
    'Bunker adjustment factor': (180, 420),
    'Congestion surcharge': (120, 350),
    'Terminal handling, origin': (140, 260),
    'Terminal handling, destination': (190, 340),
    'Documentation fee': (45, 90),
    'Seal and documentation': (40, 85),
    'Fuel surcharge': (150, 600),
    'Security surcharge': (60, 140),
    'Airport handling': (80, 200),
    'Export customs clearance': (90, 180),
    'Inland haulage': (300, 700),
    'Port storage': (120, 480),
    'Customs brokerage': (150, 400),
    'Cargo insurance': (80, 260),
}


def surcharge(rng, name):
    """One named surcharge, inside the band that name is worth."""
    low, high = SURCHARGE_BANDS.get(name, (55, 320))
    return money(rng.uniform(low, high))


def freight_rate(rng, base, bias, spread):
    """A freight charge, which moves far more than a component price."""
    mu = math.log(base * bias) - (spread ** 2) / 2
    return money(round(rng.lognormvariate(mu, spread), 2))


def seeded(seed):
    return random.Random(seed)
