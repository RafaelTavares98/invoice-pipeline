"""How goods get from each factory to Louveira.

A lane is a factory's port, the carriers that serve it, and how long the
water takes. Nothing picks a route at random: a Vietnamese factory sails
from Cat Lai, not from Ningbo.
"""

from dataclasses import dataclass

DESTINATION = 'Santos'
INLAND = 'Louveira'


@dataclass(frozen=True)
class Lane:
    port: str
    ocean_carriers: tuple
    ocean_days: tuple
    air_days: tuple = (3, 6)


LANES = {
    'NCL': Lane('Ningbo', ('MRK', 'CSM'), (32, 41)),
    'SBP': Lane('Shantou', ('CSM', 'MRK'), (34, 44)),
    'GZV': Lane('Nansha', ('CSM', 'MRK'), (33, 42)),
    'HCV': Lane('Busan', ('MRK', 'CSM'), (35, 45)),
    'BDT': Lane('Cat Lai', ('MRK', 'CSM'), (36, 46)),
    'ARL': Lane('Nhava Sheva', ('MRK',), (30, 39)),
}

#: The carrier that runs the last leg, port to warehouse, in the runs
#: without Brazil; with Brazil, TLV trucks it in reais.
INLAND_CARRIER = 'KNG'

#: The one carrier that flies, when an order is already late.
AIR_CARRIER = 'DHI'


def lane_for(factory_code):
    return LANES[factory_code]


def ocean_carrier(rng, factory_code):
    return rng.choice(LANES[factory_code].ocean_carriers)


def transit_days(rng, factory_code, mode):
    lane = LANES[factory_code]
    span = lane.air_days if mode == 'air' else lane.ocean_days
    return rng.randint(*span)
