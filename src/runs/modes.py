"""The trial modes and the datasets, each in its own folder.

smoke     one invoice: drawn, mailed to a folder, read back, scored
batch     many invoices, the same way, scored together
live      the simulated ticks behind the dashboard's demonstration, one
          day at a time; the real run lives in runs/backlog.py
dataset   a run's figures for a model, no pages; readset, the same read
          back from drawn pages

Every mode writes under its own folder in Invoices/ and nowhere else, so
a trial never mixes its invoices with the real run.
"""

import json
from contextlib import contextmanager
import shutil
from datetime import date, timedelta
from pathlib import Path

from business import issuers
from drawing import render, scan
from mail import delivery, sources
from reading import intake
from simulation import builder
from simulation.operation import BUSY, Operation
from simulation.pricing import seeded

MODES = ('unit', 'smoke', 'batch', 'live', 'dataset')

#: The Monday the simulated business opens on.
OPENING_DAY = date(2026, 4, 6)


class UnknownMode(Exception):
    """A mode name that is not one of MODES."""


class OutsideItsFolder(Exception):
    """A mode tried to write somewhere other than its own folder."""


class Score:
    """How many invoices the reader got right, out of how many."""

    def __init__(self, correct, total, scanned_correct=0, scanned_total=0):
        self.correct = correct
        self.total = total
        #: Scans are scored apart too, so a fall in OCR is never hidden
        #: inside the overall figure.
        self.scanned_correct = scanned_correct
        self.scanned_total = scanned_total


#: Where each mode writes, inside Invoices/. Trials, the simulated live
#: ticks among them, stay under samples/ and datasets/, apart from the
#: real run in live/.
FOLDERS = {'unit': ('samples', 'unit'), 'smoke': ('samples', 'single'),
           'batch': ('samples', 'batch'), 'live': ('samples', 'live'),
           'dataset': ('datasets',)}


def folder_for(base, mode):
    if mode not in MODES:
        raise UnknownMode(f'{mode!r} is not one of {MODES}')
    return Path(base).joinpath('Invoices', *FOLDERS[mode])


def dataset(base, profile='year', seed=2026):
    """The figures of a whole run, without drawing a page: the desk's
    records under erp/, every invoice and line, and the labels apart.
    Returns the folder, Invoices/datasets/<profile>-seed<seed>/ under base."""
    from simulation import erp, labels
    from simulation.operation import PROFILES
    run = Operation(OPENING_DAY, seed=seed, profile=PROFILES[profile]).run()
    home = folder_for(base, 'dataset') / f'{profile}-seed{seed}'
    erp.export(run, home / 'erp')
    hidden = {'anomaly', 'lookalike_of'}
    erp.write_rows(home / 'invoices.csv', [
        {k: v for k, v in i.as_truth().items() if k not in hidden}
        | {'reference': i.reference}
        for i in run.invoices])
    erp.write_rows(home / 'invoice_lines.csv', [
        {'number': i.number, 'issue_date': i.issue_date, 'position': n,
         'code': l.code, 'description': l.description, 'quantity': l.quantity,
         'unit': l.unit, 'unit_price': l.unit_price, 'net': l.net}
        for i in run.invoices for n, l in enumerate(i.lines, start=1)])
    labels.write(run, home)
    # The same run in the reader's own columns, for the cost report.
    from costing import truth
    filed, filed_lines = truth.books(run)
    (home / 'filed').mkdir(exist_ok=True)
    erp.write_rows(home / 'filed' / 'invoices.csv', filed)
    erp.write_rows(home / 'filed' / 'invoice_lines.csv', filed_lines)
    return home


def _as_dataset_row(row):
    """One store row under the dataset's own column names.

    The reader and the desk's records name four things differently. A
    model joins the two, so the dataset speaks the records' language:

    - the reader's invoice_number is the records' number;
    - a line's row is its position;
    - the account read off the page is pay_to;
    - issuer is the three letter code the vendor master is keyed on,
      while the name printed on the page is kept beside it. The code is
      the first field of the invoice number, so it was read too: nothing
      here comes from the simulation.
    """
    renamed = dict(row)
    if 'invoice_number' in renamed:
        renamed['number'] = renamed.pop('invoice_number')
    if 'row' in renamed:
        renamed['position'] = renamed.pop('row')
    if 'bank_account' in renamed:
        renamed['pay_to'] = renamed.pop('bank_account')
    if 'issuer' in renamed:
        renamed['issuer_name'] = renamed['issuer']
        renamed['issuer'] = str(renamed.get('number', '')).split('-')[0]
    return renamed


def _spread(invoices, limit):
    """`limit` invoices taken evenly across the run, not off the front.

    The first N invoices are the first fortnight of a year. A model
    split by week would then have one week of data and no week left to
    test on, and the rarer anomalies would never appear at all.
    """
    if limit >= len(invoices):
        return list(invoices)
    step = len(invoices) / limit
    return [invoices[int(n * step)] for n in range(limit)]


def read_dataset(base, profile='year', seed=2026, limit=None):
    """The same run as `dataset`, but drawn, mailed and read back.

    `dataset` writes the simulation's own figures, which are perfect. A
    model trained on perfect figures never meets a misread total, a lost
    line or a scanned page, and those are most of what a payables desk
    is handed. This writes what the reader made of the pages instead.

    The desk's own records and the answers come from the simulation, as
    they should: nobody reads a vendor master off an invoice.

    It costs about two seconds an invoice, nearly all of it the scanned
    pages, so `limit` takes N invoices spread over the run. A whole
    year is around four hours and belongs in a background job.
    """
    from simulation import erp, labels
    from simulation.operation import PROFILES

    run = Operation(OPENING_DAY, seed=seed, profile=PROFILES[profile]).run()
    home = _fresh(folder_for(base, 'dataset') / f'read-{profile}-seed{seed}')

    chosen = run.invoices if limit is None else _spread(run.invoices, limit)
    pairs = [(issuers.by_code(invoice.number.split('-')[0]), invoice)
             for invoice in chosen]
    written = _draw(home, pairs)
    _mail(home, written)
    store = _read_back(home)

    erp.export(run, home / 'erp')
    labels.write(run, home)
    # The reader calls it invoice_number and the simulation calls it
    # number. Both datasets are read by the same loader in project 02,
    # so the read one answers to the same names.
    erp.write_rows(home / 'invoices.csv', [_as_dataset_row(row)
                                           for row in store.invoices])
    erp.write_rows(home / 'invoice_lines.csv', [_as_dataset_row(row)
                                                for row in store.lines])

    score = _score(store, chosen)
    (home / 'reading.json').write_text(json.dumps({
        'invoices': score.total,
        'grand_total_right': score.correct,
        'scans': score.scanned_total,
        'scans_right': score.scanned_correct,
    }, indent=2), encoding='utf-8')
    return home


def guard(home, path):
    """path, if it lies inside home; refused otherwise."""
    if not Path(path).resolve().is_relative_to(Path(home).resolve()):
        raise OutsideItsFolder(f'{path} is outside {home}')
    return Path(path)


def _fresh(home):
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    return home


def _mail(home, written, prefix=''):
    """Each invoice as one .eml in home/inbox."""
    inbox = guard(home, home / 'inbox')
    seen = set()
    for position, (issuer, invoice, pdf) in enumerate(written, start=1):
        sources.write_message(
            inbox, f'{prefix}{position:04d}-{invoice.number}',
            delivery.subject_for(issuer, invoice),
            [(pdf.name, pdf.read_bytes())],
            sender=delivery.sender_for(issuer, 'local@example.invalid'),
            sent_at=delivery.sent_at(invoice, position,
                                     again=invoice.number in seen))
        seen.add(invoice.number)
    return inbox


def _read_back(home, prefix=''):
    """The messages in home/inbox whose name starts with prefix, into
    home/data. A live tick passes its day, so it never reopens old mail."""
    store = intake.Store(guard(home, home / 'data'))
    for message in sources.LocalMailbox(home / 'inbox').messages(prefix):
        intake.replay(store, message)
    store.save()
    return store


def _score(store, invoices):
    found = {row['invoice_number']: str(row['grand_total'])
             for row in store.invoices}
    right = [found.get(invoice.number) == str(invoice.grand_total)
             for invoice in invoices]
    scanned = [ok for ok, invoice in zip(right, invoices)
               if scan.chosen(invoice.number)]
    return Score(sum(right), len(invoices), sum(scanned), len(scanned))


def _drawn(out, issuer, invoice):
    """One invoice as a PDF, scanned when its issuer's habit says so."""
    pdf, _ = render.draw(out, invoice, issuer)
    return pdf


def _draw(home, chosen):
    out = guard(home, home / 'out')
    out.mkdir(parents=True, exist_ok=True)
    return [(issuer, invoice, _drawn(out, issuer, invoice))
            for issuer, invoice in chosen]


def _end_to_end(home, chosen):
    written = _draw(home, chosen)
    (home / 'truth.json').write_text(json.dumps(
        [invoice.as_truth() for _, invoice, _ in written], indent=2),
        encoding='utf-8')
    _mail(home, written)
    return _score(_read_back(home), [invoice for _, invoice, _ in written])


def smoke(base):
    """One invoice from one issuer, all the way through."""
    home = _fresh(folder_for(base, 'smoke'))
    issuer = issuers.ALL_ISSUERS[0]
    return _end_to_end(home, [(issuer, builder.invoice_for(issuer, seed=1))])


def batch(base, count=100, seed=2026):
    """count invoices from random issuers, all the way through."""
    home = _fresh(folder_for(base, 'batch'))
    rng = seeded(seed)
    chosen = []
    numbers = set()
    while len(chosen) < count:
        issuer = rng.choice(issuers.ALL_ISSUERS)
        invoice = builder.invoice_for(issuer, seed=rng.randrange(10 ** 9))
        if invoice.number not in numbers:
            numbers.add(invoice.number)
            chosen.append((issuer, invoice))
    return _end_to_end(home, chosen)


def _clock(home):
    return home / 'clock.json'


def live_day(base, start=OPENING_DAY):
    """The next simulated day the live mode will release."""
    clock = _clock(folder_for(base, 'live'))
    if not clock.exists():
        return start
    return date.fromisoformat(json.loads(clock.read_text())['next_day'])


class Tick:
    """What one live tick did: the day, its invoices, the store, the score."""

    def __init__(self, day, invoices, store, score):
        self.day = day
        self.invoices = invoices
        self.store = store
        self.score = score


@contextmanager
def _untimed(stage):
    yield


def live_step(base, start=OPENING_DAY, timed=_untimed):
    """Release one simulated day, and report everything it did.

    timed(stage) wraps each stage, so a monitor can clock it without this
    module knowing monitors exist.
    """
    home = folder_for(base, 'live')
    home.mkdir(parents=True, exist_ok=True)
    day = live_day(base, start)
    run = Operation(start, profile=BUSY).run()
    todays = sorted((i for i in run.invoices if i.issue_date == day),
                    key=lambda i: i.number)
    chosen = [(issuers.by_code(i.issuer_code), i) for i in todays]
    with timed('draw'):
        written = _draw(home, chosen)
    with timed('mail'):
        _mail(home, written, prefix=f'{day.isoformat()}-')
    with timed('read'):
        store = _read_back(home, prefix=f'{day.isoformat()}-')
    # The desk's records as they stood that day, nothing later.
    from simulation import erp
    erp.export(run, guard(home, home / 'erp'), as_of=day)
    # The cost report, refreshed the day the documents arrived.
    from costing import landed
    landed.write(landed.load(home / 'data', home / 'erp'),
                 guard(home, home / 'cost'))
    _clock(home).write_text(json.dumps(
        {'next_day': (day + timedelta(days=1)).isoformat()}))
    return Tick(day, todays, store, _score(store, todays))
