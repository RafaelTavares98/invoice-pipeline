"""The numbers the monitoring dashboard reads.

Each live tick reports what every stage did. Prometheus scrapes these
from /metrics; Grafana draws them. Nothing here changes what the
pipeline does: it only counts and times it.
"""

import time
from contextlib import contextmanager
from datetime import datetime, timezone

from prometheus_client import Counter, Gauge, Histogram

from reading import intake
from runs import modes

#: Fine enough below three seconds that the 95th percentile is read off
#: the data, not guessed across a gap from one to two and a half seconds.
STAGE_BUCKETS = (0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0,
                 2.5, 3.0, 5.0, 10.0)

#: From a mail landing to its row: seconds when the watcher keeps up,
#: minutes when a scan queue builds. A top bucket of 10 s hid how long.
REGISTRATION_BUCKETS = (1, 2, 5, 10, 30, 60, 120, 300, 600, 1800)


class Pipeline:
    """Every metric, registered once in one registry."""

    def __init__(self, registry):
        self.invoices = Counter(
            'invoices', 'Invoices handled, by stage.', ['stage'],
            registry=registry)
        self.statuses = Counter(
            'documents_by_status', 'What the reader filed each new '
            'document as.', ['status'], registry=registry)
        self.stage_seconds = Histogram(
            'stage_seconds', 'Time each stage of a tick took.', ['stage'],
            buckets=STAGE_BUCKETS, registry=registry)
        self.accuracy = Gauge(
            'read_accuracy_ratio', 'Share of the last tick\'s invoices '
            'whose total the reader got right.', registry=registry)
        self.stored = Gauge(
            'stored_documents', 'Documents in invoices.csv.',
            registry=registry)
        self.day = Gauge(
            'simulated_day_timestamp_seconds', 'The business day the last '
            'tick released.', registry=registry)
        self.success = Gauge(
            'last_tick_success', '1 when the last tick finished, 0 when it '
            'failed.', registry=registry)
        self.read_by = Counter(
            'documents_read', 'New documents, by how they were read: from '
            'the text layer, or by OCR off a scan.', ['method'],
            registry=registry)
        self.flagged = Counter(
            'documents_flagged', 'New documents left for a person to '
            'check: OCR slips and readings whose sums never closed.',
            registry=registry)
        self.failures = Counter(
            'tick_failures', 'Ticks that raised an error.',
            registry=registry)
        # The department's operational targets.
        self.same_day = Gauge(
            'analysed_same_day_ratio', 'Share of stored documents registered '
            'on the Brasilia day they arrived.', registry=registry)
        self.our_errors = Gauge(
            'our_error_ratio', 'Share of stored documents the reader could '
            'not read or close, left for a person.', registry=registry)
        self.by_kind = Counter(
            'documents_by_kind', 'New documents, by kind: goods, freight, '
            'credit, customs, broker.', ['kind'], registry=registry)
        self.registration = Histogram(
            'registration_delay_seconds', 'From the mail arriving to its '
            'row being written.', buckets=REGISTRATION_BUCKETS,
            registry=registry)
        self.landed = Gauge(
            'landed_cost_brl', 'Landed cost in the cost report, in reais, by '
            'status: provisional or final.', ['status'], registry=registry)
        self.mails = Counter(
            'mails_sent', 'Replies sent to the real mailbox, by sender.',
            ['sender'], registry=registry)

    @contextmanager
    def timed(self, stage):
        began = time.perf_counter()
        yield
        self.stage_seconds.labels(stage).observe(time.perf_counter() - began)


def tick(base, watch, start=modes.OPENING_DAY):
    """One live tick, reported. A failure is counted, never hidden."""
    held = modes.folder_for(base, 'live') / 'data'
    stored_before = len(intake.Store(held).invoices) if held.exists() else 0
    try:
        step = modes.live_step(base, start, timed=watch.timed)
    except Exception:
        watch.success.set(0)
        watch.failures.inc()
        return []
    count = len(step.invoices)
    for stage in ('drawn', 'mailed', 'read'):
        watch.invoices.labels(stage).inc(count)
    watch.flagged.inc(0)
    for row in step.store.invoices[stored_before:]:
        watch.statuses.labels(row['status']).inc()
        if row.get('read_by'):
            watch.read_by.labels(row['read_by']).inc()
        if 'check by hand' in row['problems'] or 'OCR read' in row['problems']:
            watch.flagged.inc()
    watch.stored.set(len(step.store.invoices))
    _operational(watch, step.store.invoices, stored_before, base)
    if step.score.total:
        watch.accuracy.set(step.score.correct / step.score.total)
    watch.day.set(datetime(step.day.year, step.day.month, step.day.day,
                           12, tzinfo=timezone.utc).timestamp())
    watch.success.set(1)
    return step.invoices


def filed(watch, store, outcome):
    """One PDF the watcher took from the mailbox, counted as it lands."""
    if outcome.status == 'duplicate':
        watch.statuses.labels('duplicate').inc()
        return
    row = next((r for r in reversed(store.invoices)
                if r['sha256'] == outcome.digest), None)
    watch.invoices.labels('read').inc()
    watch.statuses.labels(outcome.status).inc()
    if row is None:
        return
    if row.get('read_by'):
        watch.read_by.labels(row['read_by']).inc()
    if row.get('kind'):
        watch.by_kind.labels(row['kind']).inc()
    if 'check by hand' in row['problems'] or 'OCR read' in row['problems'] \
            or row['status'] == 'unreadable':
        watch.flagged.inc()
    if row.get('first_seen') and row.get('registered_at'):
        spent = (datetime.fromisoformat(row['registered_at'])
                 - datetime.fromisoformat(row['first_seen']))
        watch.registration.observe(max(spent.total_seconds(), 0))
    watch.stored.set(len(store.invoices))
    _targets(watch, store.invoices)


def _targets(watch, rows):
    """The desk's targets, from every row filed so far."""
    from costing import kpis
    same = kpis.analysed_same_day(rows)
    errors = kpis.our_error_rate(rows)
    watch.same_day.set(float(same) / 100 if same is not None else 0)
    watch.our_errors.set(float(errors) / 100 if errors is not None else 0)


def mailed(watch, mail):
    """One reply sent to the real mailbox."""
    sender = mail['X-Reply-Id'].split('-')[1]
    watch.mails.labels(sender).inc()
    pdfs = sum(1 for part in mail.walk() if part.get_filename())
    watch.invoices.labels('mailed').inc(pdfs)


def _operational(watch, rows, stored_before, base):
    """The targets: same-day share, our error rate, the cost by status."""
    import csv
    from costing import kpis
    from decimal import Decimal
    same = kpis.analysed_same_day(rows)
    errors = kpis.our_error_rate(rows)
    watch.same_day.set(float(same) / 100 if same is not None else 0)
    watch.our_errors.set(float(errors) / 100 if errors is not None else 0)
    for row in rows[stored_before:]:
        if row.get('kind'):
            watch.by_kind.labels(row['kind']).inc()
        if row.get('first_seen') and row.get('registered_at'):
            spent = (datetime.fromisoformat(row['registered_at'])
                     - datetime.fromisoformat(row['first_seen']))
            watch.registration.observe(max(spent.total_seconds(), 0))
    report = modes.folder_for(base, 'live') / 'cost' / 'landed_cost.csv'
    totals = {'provisional': Decimal(0), 'final': Decimal(0)}
    if report.exists():
        with open(report, encoding='utf-8', newline='') as handle:
            for line in csv.DictReader(handle):
                if line.get('status') in totals:
                    totals[line['status']] += Decimal(line['landed_brl'])
    for status, amount in totals.items():
        watch.landed.labels(status).set(float(amount))
