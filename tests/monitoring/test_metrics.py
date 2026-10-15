"""The numbers the monitoring dashboard reads.

Each live tick reports what every stage did: how many invoices were
drawn, mailed and read, what the reader made of them, how long each
stage took, and how many the reader got right. Prometheus scrapes these;
Grafana draws them.
"""

from datetime import date

import pytest
from prometheus_client import CollectorRegistry

from monitoring import metrics
from runs import modes

START = date(2026, 4, 6)


@pytest.fixture
def registry():
    return CollectorRegistry()


def value(registry, name, **labels):
    return registry.get_sample_value(name, labels) or 0


class TestOneTick:
    def test_every_stage_counts_the_same_invoices(self, tmp_path, registry):
        watch = metrics.Pipeline(registry)

        released = metrics.tick(tmp_path, watch, start=START)

        for stage in ('drawn', 'mailed', 'read'):
            assert value(registry, 'invoices_total', stage=stage) == \
                len(released)

    def test_the_reader_is_scored_against_the_answer_key(self, tmp_path,
                                                         registry):
        watch = metrics.Pipeline(registry)

        metrics.tick(tmp_path, watch, start=START)

        # A poor scan can be read wrong and flagged for a person, so the
        # ratio is the share right, not a promise of perfection.
        assert 0.9 <= value(registry, 'read_accuracy_ratio') <= 1.0

    def test_each_stage_is_timed(self, tmp_path, registry):
        watch = metrics.Pipeline(registry)

        metrics.tick(tmp_path, watch, start=START)

        for stage in ('draw', 'mail', 'read'):
            assert value(registry, 'stage_seconds_count', stage=stage) == 1

    def test_the_store_size_is_reported(self, tmp_path, registry):
        watch = metrics.Pipeline(registry)

        released = metrics.tick(tmp_path, watch, start=START)

        assert value(registry, 'stored_documents') == len(
            {invoice.number for invoice in released})

    def test_the_simulated_day_is_reported(self, tmp_path, registry):
        """The dashboard shows which day of the business it has reached."""
        watch = metrics.Pipeline(registry)

        metrics.tick(tmp_path, watch, start=START)

        assert value(registry, 'simulated_day_timestamp_seconds') > 0

    def test_a_good_tick_is_marked_as_one(self, tmp_path, registry):
        watch = metrics.Pipeline(registry)

        metrics.tick(tmp_path, watch, start=START)

        assert value(registry, 'last_tick_success') == 1


class TestManyTicks:
    def test_counts_add_up_across_ticks(self, tmp_path, registry):
        watch = metrics.Pipeline(registry)
        released = []
        for _ in range(4):
            released += metrics.tick(tmp_path, watch, start=START)

        assert value(registry, 'invoices_total', stage='drawn') == \
            len(released)

    def test_a_restart_does_not_count_old_documents_again(self, tmp_path):
        """The monitor restarts with empty counters; the store does not.
        Only documents new in this tick are counted by status."""
        metrics.tick(tmp_path, metrics.Pipeline(CollectorRegistry()),
                     start=START)
        fresh = CollectorRegistry()
        released = metrics.tick(tmp_path, metrics.Pipeline(fresh),
                                start=START)

        counted = sum(value(fresh, 'documents_by_status_total', status=s)
                      for s in ('new', 'revised', 'superseded',
                                'unreadable'))
        assert counted <= len(released)

    def test_a_failed_tick_is_counted_not_hidden(self, tmp_path, registry,
                                                 monkeypatch):
        watch = metrics.Pipeline(registry)

        def broken(*args, **kwargs):
            raise OSError('disk full')
        monkeypatch.setattr(modes, '_read_back', broken)

        metrics.tick(tmp_path, watch, start=START)

        assert value(registry, 'last_tick_success') == 0
        assert value(registry, 'tick_failures_total') == 1


class TestScansOnTheDashboard:
    def test_each_new_document_is_counted_by_how_it_was_read(self, tmp_path,
                                                             registry):
        watch = metrics.Pipeline(registry)

        released = metrics.tick(tmp_path, watch, start=START)

        by_text = value(registry, 'documents_read_total', method='text')
        by_ocr = value(registry, 'documents_read_total', method='ocr')
        assert by_text + by_ocr == value(registry, 'stored_documents')
        assert released

    def test_rows_left_for_a_person_are_counted(self, tmp_path, registry):
        """A flagged row is not an error, but somebody has to look."""
        watch = metrics.Pipeline(registry)

        metrics.tick(tmp_path, watch, start=START)

        assert registry.get_sample_value('documents_flagged_total') is not None


class TestTheOperationalTargets:
    """The department's own targets, on the same dashboard."""

    def test_the_same_day_share_and_our_error_rate_are_reported(
            self, tmp_path, registry):
        watch = metrics.Pipeline(registry)

        metrics.tick(tmp_path, watch, start=START)

        assert value(registry, 'analysed_same_day_ratio') == 1.0
        assert 0 <= value(registry, 'our_error_ratio') <= 0.1

    def test_the_landed_cost_is_reported_by_status(self, tmp_path, registry):
        watch = metrics.Pipeline(registry)

        metrics.tick(tmp_path, watch, start=START)

        provisional = value(registry, 'landed_cost_brl', status='provisional')
        assert provisional is not None and provisional >= 0

    def test_new_documents_are_counted_by_kind(self, tmp_path, registry):
        watch = metrics.Pipeline(registry)

        released = metrics.tick(tmp_path, watch, start=START)

        kinds = sum(value(registry, 'documents_by_kind_total', kind=kind) or 0
                    for kind in ('goods', 'freight', 'credit', 'customs', 'broker'))
        assert kinds == len({i.number for i in released})


def test_every_metric_on_the_dashboard_is_exported():
    """A panel over a metric nobody exports is a blank panel."""
    import json
    import re
    from pathlib import Path
    board = Path(__file__).resolve().parents[2] / 'monitoring' / 'grafana' \
        / 'dashboards' / 'pipeline.json'
    exprs = [t['expr'] for p in json.loads(board.read_text(encoding='utf-8'))['panels']
             for t in p.get('targets', [])]
    used = set(re.findall(r'[a-z_]+(?=\{|\[|\)| |$)', ' '.join(exprs)))
    registry = CollectorRegistry()
    metrics.Pipeline(registry)
    exported = set()
    for family in registry.collect():
        exported |= {family.name, f'{family.name}_total',
                     f'{family.name}_bucket'}
    names = {u for u in used if u.endswith(('_total', '_ratio', '_brl',
                                             '_seconds', '_bucket', '_documents',
                                             '_success'))}
    # Project 02's exporter serves these; the dashboard draws both.
    exported |= {'anomaly_flags', 'anomaly_decisions', 'anomaly_flagged_amount',
                 'anomaly_champion_average_precision'}
    missing = {n for n in names if n not in exported
               and n.removesuffix('_bucket') not in exported}
    assert not missing


class TestTheRealRun:
    """The watcher and the backlog send report as they go, so the
    dashboard shows the real run while it runs."""

    def test_each_filed_document_is_counted(self, tmp_path):
        from prometheus_client import CollectorRegistry
        from business import issuers as known
        from drawing import render
        from monitoring import metrics
        from reading import intake
        from simulation import builder
        registry = CollectorRegistry()
        watch = metrics.Pipeline(registry)
        store = intake.Store(tmp_path / 'data')
        invoice = builder.invoice_for(known.ALL_ISSUERS[0], seed=3)
        pdf = render.build_invoice(tmp_path, invoice)
        outcome = store.take(pdf.read_bytes(), pdf.name,
                             '2026-10-14T08:00:00-03:00',
                             registered_at='2026-10-14T08:00:02-03:00')

        metrics.filed(watch, store, outcome)

        assert registry.get_sample_value('documents_read_total',
                                         {'method': 'text'}) == 1
        assert registry.get_sample_value('stored_documents') == 1
        assert registry.get_sample_value('documents_by_status_total',
                                         {'status': 'new'}) == 1

    def test_each_mail_sent_is_counted_by_sender(self):
        from email.message import EmailMessage
        from prometheus_client import CollectorRegistry
        from monitoring import metrics
        registry = CollectorRegistry()
        watch = metrics.Pipeline(registry)
        mail = EmailMessage()
        mail['X-Reply-Id'] = '0001-NCL-r1'
        mail.add_attachment(b'%PDF', maintype='application', subtype='pdf',
                            filename='a.pdf')

        metrics.mailed(watch, mail)

        assert registry.get_sample_value('mails_sent_total',
                                         {'sender': 'NCL'}) == 1
        assert registry.get_sample_value('invoices_total',
                                         {'stage': 'mailed'}) == 1


def test_the_watcher_reports_the_desks_targets(tmp_path):
    """The real run has no ticks; the watcher reports the same-day share
    and our error rate itself, from the rows it has filed."""
    from prometheus_client import CollectorRegistry
    from business import issuers as known
    from drawing import render
    from monitoring import metrics
    from reading import intake
    from simulation import builder
    registry = CollectorRegistry()
    watch = metrics.Pipeline(registry)
    store = intake.Store(tmp_path / 'data')
    invoice = builder.invoice_for(known.ALL_ISSUERS[0], seed=3)
    pdf = render.build_invoice(tmp_path, invoice)
    outcome = store.take(pdf.read_bytes(), pdf.name,
                         '2026-10-14T08:00:00-03:00',
                         registered_at='2026-10-14T08:00:02-03:00')

    metrics.filed(watch, store, outcome)

    assert registry.get_sample_value('analysed_same_day_ratio') == 1.0
    assert registry.get_sample_value('our_error_ratio') == 0.0


def test_the_tick_panels_read_only_the_simulated_run():
    """A real run has no ticks: its panels would show FAILED and 1969."""
    import json
    from pathlib import Path
    board = json.loads((Path(__file__).resolve().parents[2] / 'monitoring'
                        / 'grafana' / 'dashboards' / 'pipeline.json')
                       .read_text(encoding='utf-8'))
    for panel in board['panels']:
        for target in panel.get('targets', []):
            for metric in ('last_tick_success', 'simulated_day_timestamp',
                           'read_accuracy_ratio', 'tick_failures'):
                if metric in target['expr']:
                    assert 'job="invoice-pipeline"' in target['expr'], \
                        panel['title']
