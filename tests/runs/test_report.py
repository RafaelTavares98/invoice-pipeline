"""The reference's numbers, written by the code that made them.

A number typed into a document drifts the day the simulation changes.
The table is generated from the run itself, and this test fails when
the reference holds anything else.
"""

from pathlib import Path

import pytest

from runs import report
from runs.modes import OPENING_DAY
from simulation.operation import BUSY, Operation

#: The table counts scans at the real share; no OCR runs here.
pytestmark = pytest.mark.ocr

REFERENCE = Path(__file__).resolve().parents[2] / 'docs' / 'reference.md'


def test_the_table_names_its_seed():
    """A run is reproducible only if the seed is printed beside it."""
    assert 'seed 2026' in report.one_run_table()


def test_the_table_counts_the_busy_window():
    run = Operation(OPENING_DAY, profile=BUSY).run()

    assert f'| Invoices in the period | {len(run.invoices)} |' in \
        report.one_run_table()


def test_the_reference_holds_exactly_the_generated_table():
    text = REFERENCE.read_text(encoding='utf-8')
    start = text.index(report.START) + len(report.START)
    end = text.index(report.END)

    assert text[start:end].strip() == report.one_run_table().strip()
