"""A training set without the pages: the records, the invoices, the labels.

Drawing and reading five thousand PDFs takes hours. A model in project 02
first needs the figures, so `run.py dataset` writes them straight from the
simulation, in seconds.
"""

import csv
from datetime import date

from runs import modes
from simulation import erp


def read(path):
    with open(path, newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def _span(rows, column):
    """Days between the first and the last date in a column."""
    days = sorted(row[column][:10] for row in rows if row.get(column))
    return (date.fromisoformat(days[-1])
            - date.fromisoformat(days[0])).days


def test_a_dataset_holds_records_invoices_lines_and_labels(tmp_path):
    folder = modes.dataset(tmp_path, 'busy', 7)

    for name in erp.TABLES:
        assert (folder / 'erp' / f'{name}.csv').exists()
    invoices = read(folder / 'invoices.csv')
    lines = read(folder / 'invoice_lines.csv')
    labels = read(folder / 'labels.csv')

    assert len(invoices) == len(labels) > 500
    assert {l['number'] for l in lines} <= {i['number'] for i in invoices}


def test_the_invoices_carry_no_answer(tmp_path):
    folder = modes.dataset(tmp_path, 'busy', 7)
    columns = set(read(folder / 'invoices.csv')[0])

    assert not columns & {'anomaly', 'lookalike_of'}


def test_it_files_the_run_as_a_perfect_reader_would(tmp_path):
    """The cost report reads the reader's columns, so the dataset keeps
    them too, under filed/, ready for `run.py cost`."""
    from costing import landed
    folder = modes.dataset(tmp_path, 'busy', 7)
    filed = read(folder / 'filed' / 'invoices.csv')

    assert {'invoice_number', 'status', 'sha256', 'kind'} <= set(filed[0])
    books = landed.load(folder / 'filed', folder / 'erp')
    assert landed.cost(books)


def test_the_folder_names_profile_and_seed(tmp_path):
    assert modes.dataset(tmp_path, 'busy', 7).name == 'busy-seed7'


def test_the_command_takes_a_profile_name():
    """The profile is a word; the command once tried to read it as a seed."""
    import subprocess
    import sys
    from pathlib import Path
    project = Path(__file__).resolve().parents[2]
    done = subprocess.run([sys.executable, 'run.py', 'dataset', 'busy', '7'],
                          cwd=project, capture_output=True, text=True)

    assert done.returncode == 0, done.stderr
    assert 'busy-seed7' in done.stdout


class TestADatasetOfWhatWasRead:
    """The figures straight from the simulation are perfect, and a model
    trained on perfect figures meets none of the reading mistakes it will
    actually be handed. This dataset is drawn, mailed and read back, so
    its invoices carry whatever the reader made of them.

    It is slow: about two seconds an invoice, most of it the scanned
    pages. Every test here uses a handful.
    """

    def test_its_invoices_come_from_the_reader(self, tmp_path):
        folder = modes.read_dataset(tmp_path, 'busy', 7, limit=12)
        invoices = read(folder / 'invoices.csv')

        assert 0 < len(invoices) <= 12
        assert 'sha256' in invoices[0]

    def test_it_keeps_the_answers_beside_them(self, tmp_path):
        folder = modes.read_dataset(tmp_path, 'busy', 7, limit=12)
        numbers = {row['number'] for row in read(folder / 'labels.csv')}
        invoices = read(folder / 'invoices.csv')

        assert {row['number'] for row in invoices} <= numbers

    def test_the_invoices_still_carry_no_answer(self, tmp_path):
        folder = modes.read_dataset(tmp_path, 'busy', 7, limit=12)
        columns = set(read(folder / 'invoices.csv')[0])

        assert not columns & {'anomaly', 'lookalike_of'}

    def test_the_records_of_the_desk_come_too(self, tmp_path):
        """Features need the vendor master and the contracts, and those
        were never read off a page: they are the desk's own records."""
        folder = modes.read_dataset(tmp_path, 'busy', 7, limit=12)

        for name in erp.TABLES:
            assert (folder / 'erp' / f'{name}.csv').exists()

    def test_the_lines_come_from_the_reader_too(self, tmp_path):
        folder = modes.read_dataset(tmp_path, 'busy', 7, limit=12)
        lines = read(folder / 'invoice_lines.csv')
        invoices = read(folder / 'invoices.csv')

        assert lines
        assert {row['number'] for row in lines} <= \
            {row['number'] for row in invoices}

    def test_the_folder_says_it_was_read(self, tmp_path):
        """A read dataset and a perfect one must never be confused for
        each other, so the name carries it."""
        folder = modes.read_dataset(tmp_path, 'busy', 7, limit=12)

        assert folder.name == 'read-busy-seed7'

    def test_a_count_spreads_over_the_whole_run(self, tmp_path):
        """Taking the first N invoices takes the first fortnight of a
        year. A model split by week then has one week of data and no
        week to test on. The count is spread instead, so the slice
        covers the same span as the run."""
        folder = modes.read_dataset(tmp_path, 'busy', 7, limit=20)
        sample = _span(read(folder / 'invoices.csv'), 'issue_date')
        whole = _span(read(folder / 'labels.csv'), 'issue_date')

        assert sample >= whole * 0.8

    def test_the_account_keeps_the_name_the_records_use(self, tmp_path):
        """The reader calls it bank_account and the desk's records call
        it pay_to. One loader reads both datasets, so they agree."""
        folder = modes.read_dataset(tmp_path, 'busy', 7, limit=12)
        columns = set(read(folder / 'invoices.csv')[0])

        assert 'pay_to' in columns

    def test_the_issuer_is_the_code_the_records_use(self, tmp_path):
        """The page says Ningbo Caplink Industrial Co., Ltd.; the vendor
        master says NCL. The code is the first field of the invoice
        number, which is also read off the page, so the dataset carries
        both: the code to join on, the name as it was printed."""
        folder = modes.read_dataset(tmp_path, 'busy', 7, limit=12)
        rows = read(folder / 'invoices.csv')
        first = next(r for r in rows if r['number'])

        assert first['issuer'] == first['number'].split('-')[0]
        assert len(first['issuer']) == 3
        assert first['issuer_name']

    def test_what_the_reader_got_wrong_is_written_down(self, tmp_path):
        """The point of this dataset is the mistakes. A run that reports
        none has read perfectly, which is worth knowing too."""
        import json
        folder = modes.read_dataset(tmp_path, 'busy', 7, limit=12)
        score = json.loads((folder / 'reading.json').read_text(
            encoding='utf-8'))

        assert score['invoices'] > 0
        assert 0 <= score['grand_total_right'] <= score['invoices']


def test_two_seeds_differ(tmp_path):
    one = read(modes.dataset(tmp_path, 'busy', 7) / 'invoices.csv')
    two = read(modes.dataset(tmp_path, 'busy', 8) / 'invoices.csv')

    assert [r['grand_total'] for r in one] != [r['grand_total'] for r in two]
