"""The answer key, as one flat file a model can read.

One row per invoice: what, if anything, is wrong with it, what honest case
it resembles, and how many days a real desk would take to find out. Labels
arrive late in real life (Le Borgne and Bontempi, practical handbook), so a model trained on
Monday must not see the answers for last week's invoices yet.
"""

import random
from pathlib import Path

from simulation import erp

#: Days until each anomaly would be discovered, as (fewest, most). A
#: duplicate shows up at the payment run; a vendor with no order can go a quarter or more.
DELAYS = {
    'near_duplicate': (5, 30),
    'freight_overbill': (14, 45),
    'price_drift': (10, 40),
    'quantity_over': (10, 40),
    'round_total': (20, 60),
    'account_mismatch': (20, 60),
    'split_billing': (30, 90),
    'unmatched_vendor': (60, 180),
    # A duty rate is checked against the tariff table at the close, so
    # it surfaces with the month. A broker fee waits for somebody to
    # hold the bill against the contract, which happens on review.
    'duty_rate_wrong': (15, 45),
    'broker_fee_over': (30, 90),
}


def _delay(invoice):
    """Stable: the same invoice always takes the same days to be found."""
    if not invoice.anomaly:
        return ''
    rng = random.Random(f'{invoice.number}|{invoice.anomaly}')
    return rng.randint(*DELAYS[invoice.anomaly])


def rows(operation):
    return [{'number': i.number, 'issuer': i.issuer_code, 'kind': i.kind,
             'issue_date': i.issue_date, 'anomaly': i.anomaly,
             'lookalike_of': i.lookalike_of,
             'found_after_days': _delay(i)}
            for i in operation.invoices]


def write(operation, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return erp.write_rows(folder / 'labels.csv', rows(operation))
