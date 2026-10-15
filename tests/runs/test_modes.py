"""The run modes: each one end to end, each in its own folder.

A test run that writes into the production folders mixes made-up
invoices with real ones, and nobody can tell them apart afterwards. So
every mode writes under its own folder in Invoices/ and refuses any other
place.
"""

from datetime import date

import pytest

from runs import modes


class TestFolders:
    def test_each_mode_has_its_own_folder(self, tmp_path):
        assert modes.folder_for(tmp_path, 'smoke') == \
            tmp_path / 'Invoices' / 'samples' / 'single'
        assert modes.folder_for(tmp_path, 'batch') == \
            tmp_path / 'Invoices' / 'samples' / 'batch'
        assert modes.folder_for(tmp_path, 'dataset') == \
            tmp_path / 'Invoices' / 'datasets'

    def test_an_unknown_mode_is_refused(self, tmp_path):
        with pytest.raises(modes.UnknownMode):
            modes.folder_for(tmp_path, 'production')

    def test_writing_outside_the_mode_folder_is_refused(self, tmp_path):
        home = modes.folder_for(tmp_path, 'smoke')

        with pytest.raises(modes.OutsideItsFolder):
            modes.guard(home, tmp_path / 'data' / 'invoices.csv')

    def test_writing_inside_is_allowed(self, tmp_path):
        home = modes.folder_for(tmp_path, 'smoke')

        assert modes.guard(home, home / 'data' / 'x.csv') == home / 'data' / 'x.csv'


class TestSmoke:
    def test_one_invoice_goes_end_to_end_and_is_scored(self, tmp_path):
        score = modes.smoke(tmp_path)

        assert score.total == 1
        assert score.correct == 1

    def test_it_touches_nothing_outside_its_folder(self, tmp_path):
        modes.smoke(tmp_path)

        assert [p.name for p in tmp_path.iterdir()] == ['Invoices']
        assert [p.name for p in (tmp_path / 'Invoices' / 'samples').iterdir()] \
            == ['single']


class TestBatch:
    def test_every_invoice_is_scored(self, tmp_path):
        score = modes.batch(tmp_path, count=5)

        assert score.total == 5
        assert score.correct == 5

    def test_a_second_batch_starts_clean(self, tmp_path):
        """A score over two runs mixed together measures nothing."""
        modes.batch(tmp_path, count=3)

        assert modes.batch(tmp_path, count=2).total == 2


class TestLive:
    START = date(2026, 4, 6)

    def test_one_tick_releases_one_day(self, tmp_path):
        released = modes.live_step(tmp_path, start=self.START).invoices

        assert {invoice.issue_date for invoice in released} <= {self.START}

    def test_the_clock_moves_on(self, tmp_path):
        modes.live_step(tmp_path, start=self.START).invoices

        assert modes.live_day(tmp_path, start=self.START) == date(2026, 4, 7)

    def test_it_resumes_where_it_stopped(self, tmp_path):
        """Stopped and started again, it carries on from the next day
        instead of mailing the first days again."""
        for _ in range(3):
            modes.live_step(tmp_path, start=self.START).invoices

        assert modes.live_day(tmp_path, start=self.START) == date(2026, 4, 9)

    def test_a_tick_opens_only_its_own_mail(self, tmp_path, monkeypatch):
        """Reading the whole inbox every tick made each tick slower than
        the last. A tick opens the messages it mailed, nothing older."""
        from mail import sources
        for _ in range(3):
            modes.live_step(tmp_path, start=self.START).invoices
        opened = []
        real = sources._read_message

        def counting(raw, name):
            opened.append(name)
            return real(raw, name)
        monkeypatch.setattr(sources, '_read_message', counting)

        released = modes.live_step(tmp_path, start=self.START).invoices

        assert len(opened) == len(released)
        assert all(name.startswith('2026-04-09') for name in opened)

    def test_no_invoice_is_mailed_twice(self, tmp_path):
        mailed = []
        for _ in range(10):
            mailed += [i.number + i.issue_date.isoformat()
                       for i in modes.live_step(tmp_path, start=self.START).invoices]

        inbox = modes.folder_for(tmp_path, 'live') / 'inbox'
        assert len(list(inbox.glob('*.eml'))) == len(mailed)


@pytest.mark.ocr
class TestScans:
    def test_a_batch_carries_scans_and_scores_them_apart(self, tmp_path):
        """ARL scans most of its invoices; their score is kept apart, so a
        drop in OCR is never hidden inside the overall figure."""
        score = modes.batch(tmp_path, count=30)

        assert score.scanned_total > 0
        assert score.scanned_correct <= score.scanned_total

    def test_the_scanned_files_really_have_no_text(self, tmp_path):
        import pdfplumber
        from drawing import scan
        modes.batch(tmp_path, count=12)
        out = modes.folder_for(tmp_path, 'batch') / 'out'

        for pdf in out.glob('*.pdf'):
            if scan.chosen(pdf.stem):
                with pdfplumber.open(pdf) as document:
                    assert not (document.pages[0].extract_text() or '').strip()


class TestTheRecordsOfTheDay:
    def test_a_tick_writes_the_records_as_they_stood_that_day(self, tmp_path):
        import csv
        start = date(2026, 4, 6)
        modes.live_step(tmp_path, start=start)
        erp_folder = modes.folder_for(tmp_path, 'live') / 'erp'

        with open(erp_folder / 'purchase_orders.csv', encoding='utf-8') as f:
            raised = [row['raised_on'] for row in csv.DictReader(f)]
        assert raised and max(raised) <= start.isoformat()


class TestTheCostOfTheDay:
    def test_a_tick_refreshes_the_cost_report(self, tmp_path):
        import json
        modes.live_step(tmp_path, start=date(2026, 4, 6))
        cost = modes.folder_for(tmp_path, 'live') / 'cost'

        assert (cost / 'landed_cost.csv').exists()
        assert (cost / 'operations.csv').exists()
        summary = json.loads((cost / 'kpis.json').read_text(encoding='utf-8'))
        assert 'analysed_same_day' in summary
