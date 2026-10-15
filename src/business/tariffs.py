"""What Brazil charges to let each part in.

Every part Moty imports has an NCM, the Mercosur code the duties hang on.
The import duty (II) comes from the TEC, the IPI from the TIPI; PIS and
COFINS on imports are set by law. The rates below were read on 2026-10-12
from the sources named beside them.

The classification is simplified in one place: the glass bottles hold 30
to 100 ml, which the TEC puts in a sister subheading of 7010.90.22; the
7010.90 family carries the same 9% II, checked on 7010.90.11 and
7010.90.22.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

#: The NCM each catalogue HS code is declared under.
NCM_BY_HS = {
    '7010.90': '7010.90.22',
    '3923.30': '3923.30.00',
    '3923.10': '3923.10.90',
    '7612.10': '7612.10.00',
    '3923.50': '3923.50.00',
    '8424.89': '8424.89.90',
    '4821.10': '4821.10.00',
    '4819.10': '4819.10.00',
}


@dataclass(frozen=True)
class Rate:
    ncm: str
    ii: Decimal
    ipi: Decimal
    cofins: Decimal
    effective_on: date
    source: str


SINCE = date(2019, 1, 1)

RATES = (
    Rate('7010.90.22', Decimal('0.09'), Decimal('0.0975'), Decimal('0.0965'),
         SINCE, 'fazcomex.com.br, NCM 7010.90.22'),
    Rate('3923.30.00', Decimal('0.18'), Decimal('0.15'), Decimal('0.0965'),
         SINCE, 'gainholder.com, NCM 3923.30.00'),
    Rate('3923.10.90', Decimal('0.18'), Decimal('0.15'), Decimal('0.0965'),
         SINCE, 'gainholder.com, NCM 3923.10.90'),
    Rate('7612.10.00', Decimal('0.16'), Decimal('0.10'), Decimal('0.0965'),
         SINCE, 'gainholder.com, NCM 7612.10.00'),
    Rate('3923.50.00', Decimal('0.18'), Decimal('0.05'), Decimal('0.0965'),
         SINCE, 'gainholder.com, NCM 3923.50.00'),
    Rate('8424.89.90', Decimal('0.14'), Decimal('0.05'), Decimal('0.1065'),
         SINCE, 'gainholder.com, NCM 8424.89.90'),
    Rate('4821.10.00', Decimal('0.16'), Decimal('0.00'), Decimal('0.0965'),
         SINCE, 'gainholder.com, NCM 4821.10.00'),
    Rate('4819.10.00', Decimal('0.16'), Decimal('0.15'), Decimal('0.0965'),
         SINCE, 'gainholder.com, NCM 4819.10.00'),
)

#: PIS-Importação, general rule (Lei 10.865/2004).
PIS = Decimal('0.021')

#: AFRMM on long-haul ocean freight (Lei 10.893/2004).
AFRMM = Decimal('0.08')

#: Siscomex fee for the first addition of a declaration.
SISCOMEX = Decimal('214.50')

#: ICMS in São Paulo, charged inside its own base.
ICMS = Decimal('0.18')

#: Insurance, as a share of the goods value, when the policy is annual.
INSURANCE = Decimal('0.003')


def ncm_for(hs_code):
    return NCM_BY_HS[hs_code]


def rate_on(ncm, day, changes=()):
    """The rate in force for an NCM on a day: the base table, overridden
    by any published change that took effect on or before it."""
    found = next(rate for rate in RATES if rate.ncm == ncm)
    for change in sorted(changes, key=lambda change: change.effective_on):
        if change.ncm == ncm and change.effective_on <= day:
            found = change
    return found
