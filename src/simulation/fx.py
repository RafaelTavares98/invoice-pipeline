"""The dollar in reais, day by day: a simulated PTAX.

The Central Bank publishes the PTAX rate every business day. This series
is simulated and says so wherever it is shown: a random walk around 5.40,
moving about 0.6% a day, held over weekends. The same seed always gives
the same series.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

START = date(2025, 10, 1)
OPENING = 5.40
OPENING_RATE = Decimal('5.4000')
DAILY = 0.006


def series(until, seed=2026):
    """{day: rate} from START to until, both included."""
    rng = random.Random(f'ptax-{seed}')
    rate = OPENING
    found = {}
    day = START
    while day <= until:
        if day.weekday() < 5:
            rate *= 1 + rng.gauss(0, DAILY)
        found[day] = Decimal(f'{rate:.4f}')
        day += timedelta(days=1)
    return found


def ptax(day, seed=2026):
    return series(day, seed)[day]
