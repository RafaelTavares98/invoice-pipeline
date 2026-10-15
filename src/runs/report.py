"""The one-run table in docs/reference.md, generated from the run itself.

Run `python run.py readme` after changing the simulation; the test in
tests/runs/test_report.py fails until the reference matches.
"""

from collections import Counter
from decimal import Decimal

from drawing import scan
from runs.modes import OPENING_DAY
from simulation import ledger
from simulation.operation import BUSY, Operation

START = '<!-- one-run:start -->'
END = '<!-- one-run:end -->'
SEED = 2026


def _freight_share(run):
    goods = sum((i.grand_total for i in run.invoices if i.kind == 'goods'),
                Decimal(0))
    freight = sum((i.grand_total for i in run.invoices
                   if i.kind == 'freight' and i.currency == 'USD'), Decimal(0))
    return round(100 * freight / goods) if goods else 0


def one_run_table():
    """The table, for the busy profile and the fixed seed."""
    run = Operation(OPENING_DAY, seed=SEED, profile=BUSY).run()
    counts = ledger.counts(run)
    kinds = counts['by_kind']
    rows = [
        ('Purchase orders raised', counts['orders']),
        ('Shipments that left a port', counts['shipments']),
        ('Invoices in the period', counts['invoices']),
        ('Goods invoices', kinds.get('goods', 0)),
        ('Freight invoices', kinds.get('freight', 0)),
        ('Credit notes', kinds.get('credit', 0)),
        ('Duty statements, in reais', kinds.get('customs', 0)),
        ('Broker invoices, in reais', kinds.get('broker', 0)),
        ('Resends: same number, same bytes', counts['duplicate_numbers']),
        ('Revisions, `-R1`', counts['revisions']),
        ('Invoices quoting the wrong order', counts['wrong_order_quoted']),
        ('Chains with a landed cost', len(ledger.chains(run))),
        ('International freight as a share of goods',
         f'about {_freight_share(run)}%'),
        ('Arriving as scans', sum(scan.chosen(i.number)
                                  for i in run.invoices)),
    ]
    planted = Counter(i.anomaly for i in run.invoices if i.anomaly)
    rows += [(f'Anomaly: {name.replace("_", " ")}', planted[name])
             for name in sorted(planted)]
    twins = Counter(i.lookalike_of for i in run.invoices if i.lookalike_of)
    rows += [(f'Honest look-alike of {name.replace("_", " ")}', twins[name])
             for name in sorted(twins)]
    lines = [f'One run: {BUSY.weeks} weeks from {OPENING_DAY}, '
             f'seed {SEED}.', '', '| | |', '|---|---|']
    lines += [f'| {label} | {value} |' for label, value in rows]
    return '\n'.join(lines)


def write_into(readme):
    """Replace whatever sits between the markers with the fresh table."""
    text = readme.read_text(encoding='utf-8')
    start = text.index(START) + len(START)
    end = text.index(END)
    readme.write_text(f'{text[:start]}\n{one_run_table()}\n{text[end:]}',
                      encoding='utf-8')
