"""Moty, the company being billed. It never issues, it only receives.

Its plant is in São Paulo state: the highway is real;
Moty, its warehouse, its CNPJ and its e-mail are invented.

The department named on every page turns these documents into cost
reports. It does not pay them; finance does.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Buyer:
    name: str
    department: str
    address: tuple
    tax_label: str
    tax_id: str
    contact: str


MOTY = Buyer(
    name='Moty Cosmeticos Ltda.',
    department='Production and Logistics Cost Management',
    address=(
        'Rodovia Anhanguera, km 94, Galpao 3',
        'Jundiai, SP 13200-000',
        'Brazil',
    ),
    tax_label='CNPJ',
    tax_id='18.442.907/0001-55',
    contact='costs@moty.example',
)

SHIP_TO = (
    'Moty Cosmeticos Ltda.',
    'Inbound Dock 2',
    'Rodovia Anhanguera, km 94',
    'Jundiai, SP 13200-000',
    'Brazil',
)
