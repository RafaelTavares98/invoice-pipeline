"""What Moty buys: the cosmetic packaging components, and what they weigh.

`base_price` is the price a well behaved supplier would quote for the smallest
order, in US dollars per unit. Real quotes move around it; `pricing.py` does
that part.
"""

from dataclasses import dataclass


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
              'pcs', 9.4, 0.198, 5000, '8424.89'),
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
