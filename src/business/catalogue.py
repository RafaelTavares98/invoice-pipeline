"""What Moty buys: the cosmetic packaging components, what they weigh, and
the cartons they ship in.

`base_price` is the price a well behaved supplier would quote for the smallest
order, in US dollars per unit. Real quotes move around it; `pricing.py` does
that part.

A container is charged by the room cargo takes, so each part carries its
export carton: units, outside size in centimetres, gross weight, and where
the figures came from. Where a supplier publishes its carton, that carton
is used. Where it publishes only the unit's size, the carton is the units
laid in a grid, plus two centimetres of board each way, and the source
says so.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Carton:
    units: int
    cm: tuple          # length, width, height, outside
    kg: Decimal        # gross, full
    source: str

    @property
    def m3(self):
        length, width, height = (Decimal(str(side)) for side in self.cm)
        return length * width * height / 1_000_000


CARTONS = {
    'GB-030A': Carton(168, (40, 47, 11), Decimal('10.9'),
                      'derived: 168 bottles of 31.5 x 86 mm, 12 x 14; '
                      'colouredbottles.co.uk/products/30ml-clear-dropper-bottle'),
    'GB-050A': Carton(162, (38, 74, 10), Decimal('14.8'),
                      'derived: 162 bottles of 40 x 83 mm, 9 x 18; '
                      'colouredbottles.co.uk/products/50ml-clear-glass-cosmetic-bottle-screw-neck'),
    'GB-100B': Carton(60, (32, 52, 13), Decimal('9.5'),
                      'derived: 60 bottles of 50 x 111 mm, 6 x 10, 60 a case; '
                      'containerandpackaging.com/products/glass-cylinder-bottle/g952clf'),
    'PB-200C': Carton(100, (52, 52, 16), Decimal('2.9'),
                      'derived: 100 bottles of 50.4 x 140 mm, 10 x 10; '
                      'packari.com/en/PET-bottle-RIGOLETTO-200-ml-clear.html'),
    'JA-050D': Carton(200, (58, 58, 13), Decimal('14.3'),
                      'derived: 200 jars of 56 x 56 mm, 10 x 10 x 2 layers; '
                      'aussiesoapsupplies.com.au/jar-double-wall-50ml/'),
    'TB-075E': Carton(300, (49, 39, 33), Decimal('8.1'),
                      'derived: 300 tubes of 31.2 x 185 mm lying, 15 x 2 x 10; '
                      'environdec.com/library/epd11868'),
    'CP-024F': Carton(2500, (57, 33, 39), Decimal('12.5'),
                      'carton songmile.com/?p=3861; units derived: caps of '
                      '27 x 20 mm in bags, half the carton filled'),
    'CP-FT20': Carton(2500, (57, 33, 39), Decimal('13.8'),
                      'carton songmile.com/?p=3861; units derived as CP-024F'),
    'PM-024G': Carton(1000, (54, 38, 39), Decimal('14'),
                      'plastemart.com, listing PR-3009: 1,000 a carton, '
                      '54 x 38 x 39 cm, 14 kg gross'),
    'SP-018H': Carton(1430, (54, 34, 37), Decimal('13'),
                      'plastemart.com, listing PR-3002: 1,430 a carton, '
                      '54 x 34 x 37 cm, 13 kg gross'),
    'DR-030J': Carton(1000, (54, 38, 39), Decimal('14.2'),
                      'derived: packed like the 24/410 pump, plastemart.com '
                      'PR-3009; droppers are of the same size'),
    'LB-GL01': Carton(20000, (40, 30, 25), Decimal('19'),
                      'derived: 10 rolls of 2,000 labels, 300 x 60 mm each'),
    'LB-MT02': Carton(20000, (40, 30, 25), Decimal('23'),
                      'derived: 10 rolls of 2,000 labels, 300 x 60 mm each'),
    'CT-F350': Carton(1000, (42, 32, 27), Decimal('13.5'),
                      'derived: 1,000 cartons shipped flat, 200 x 150 mm, '
                      'two stacks of 500 at 0.5 mm'),
    'CT-R500': Carton(100, (62, 62, 26), Decimal('6.3'),
                      'derived: 100 rigid boxes of 120 x 120 x 60 mm, '
                      '5 x 5 x 4, they do not fold'),
    'SH-C32K': Carton(50, (62, 42, 27), Decimal('16'),
                      'derived: a bundle of 50 shippers flat, 600 x 400 mm, '
                      '5 mm each'),
}


@dataclass(frozen=True)
class Component:
    code: str
    description: str
    family: str
    unit: str
    grams: float
    base_price: float
    pack_size: int
    hs_code: str

    @property
    def carton(self):
        return CARTONS[self.code]

    @property
    def unit_m3(self):
        """The room one unit takes: its share of its carton."""
        return self.carton.m3 / self.carton.units


CATALOGUE = (
    Component('GB-030A', 'Glass bottle, round, 30 ml, flint', 'bottle',
              'pcs', 58.0, 0.412, 2400, '7010.90'),
    Component('GB-050A', 'Glass bottle, round, 50 ml, flint', 'bottle',
              'pcs', 82.0, 0.515, 1800, '7010.90'),
    Component('GB-100B', 'Glass bottle, cylinder, 100 ml, frosted', 'bottle',
              'pcs', 141.0, 0.804, 1200, '7010.90'),
    Component('PB-200C', 'PET bottle, 200 ml, clear', 'bottle',
              'pcs', 19.0, 0.138, 6000, '3923.30'),
    Component('JA-050D', 'Acrylic jar, 50 g, double wall', 'jar',
              'pcs', 64.0, 0.667, 1500, '3923.10'),
    Component('TB-075E', 'Aluminium tube, 75 ml, internally lacquered', 'tube',
              'pcs', 23.0, 0.291, 3000, '7612.10'),
    Component('CP-024F', 'Screw cap, 24/410, matte black', 'closure',
              'pcs', 4.6, 0.062, 10000, '3923.50'),
    Component('CP-FT20', 'Flip-top cap, 20/410, white', 'closure',
              'pcs', 5.1, 0.074, 10000, '3923.50'),
    Component('PM-024G', 'Lotion pump, 24/410, 1.2 cc, silver collar', 'pump',
              'pcs', 11.8, 0.236, 5000, '8424.89'),
    Component('SP-018H', 'Fine mist sprayer, 18/415, 0.12 cc', 'pump',
              'pcs', 8.4, 0.198, 5000, '8424.89'),
    Component('DR-030J', 'Dropper assembly, 30 ml, graduated pipette', 'pump',
              'pcs', 13.2, 0.343, 3000, '7010.90'),
    Component('LB-GL01', 'Adhesive label, 4 colour, gloss laminate', 'label',
              'pcs', 0.9, 0.028, 20000, '4821.10'),
    Component('LB-MT02', 'Adhesive label, 2 colour, matte, textured', 'label',
              'pcs', 1.1, 0.034, 20000, '4821.10'),
    Component('CT-F350', 'Folding carton, 350 gsm, offset printed', 'carton',
              'pcs', 12.5, 0.091, 5000, '4819.10'),
    Component('CT-R500', 'Rigid gift box, 500 gsm, foil stamped', 'carton',
              'pcs', 48.0, 0.624, 1000, '4819.10'),
    Component('SH-C32K', 'Shipper carton, double wall, 32 ECT', 'carton',
              'pcs', 310.0, 0.472, 500, '4819.10'),
)

BY_FAMILY = {}
for part in CATALOGUE:
    BY_FAMILY.setdefault(part.family, []).append(part)


def by_code(code):
    for part in CATALOGUE:
        if part.code == code:
            return part
    raise KeyError(code)
