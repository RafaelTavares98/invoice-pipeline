"""Smoke tests 4 to 7: the reader files what the senders mailed, and the
forwarded shipment becomes the landed cost of each part.

The tests read the mail each step wrote into its outbox; the real run
reads the same mail from Gmail.
"""

import json
from decimal import Decimal

import pytest

from mail import sources
from runs import smoke


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    base = tmp_path_factory.mktemp('base')
    smoke.freight(base)
    smoke.forward(base)
    return base


def _outbox(base, step):
    return sources.LocalMailbox(base / 'Invoices' / 'samples' / step / 'outbox')


@pytest.fixture(scope='module')
def forwarded(base):
    return smoke.read(base, 'forward', _outbox(base, 'forward'))


def test_reading_step_1_files_both_pdfs(base):
    score = smoke.read(base, 'freight', _outbox(base, 'freight'))
    assert (score['pdfs'], score['right']) == (2, 2)


def test_first_seen_is_when_the_mail_arrived(base):
    smoke.read(base, 'freight', _outbox(base, 'freight'))
    data = base / 'Invoices' / 'samples' / 'freight' / 'data' / 'invoices.csv'
    assert all(row.split(',')[16] for row in data.read_text().splitlines()[1:])


def test_reading_the_forward_misses_nothing_and_gets_nothing_wrong(forwarded):
    assert forwarded['pdfs'] == 10
    assert forwarded['missing'] == [] and forwarded['wrong'] == []


def test_a_page_the_reader_doubts_is_flagged_not_hidden(forwarded):
    assert forwarded['right'] + len(forwarded['flagged']) == 10


def test_the_score_is_written_beside_the_step(base, forwarded):
    written = base / 'Invoices' / 'samples' / 'forward' / 'score.json'
    assert json.loads(written.read_text(encoding='utf-8')) == forwarded


@pytest.fixture(scope='module')
def costed(base, forwarded):
    return smoke.cost(base)


def test_cost_lands_in_its_own_smoke_folder(costed):
    assert costed['folder'].parts[-3:] == ('Invoices', 'samples', 'cost')


def test_the_shipment_is_final(costed):
    assert {row['status'] for row in costed['rows']} == {'final'}


def test_every_cost_part_is_spread_over_the_parts(costed):
    for name in ('freight_brl', 'local_brl', 'inland_brl', 'storage_brl',
                 'broker_brl', 'duty_brl'):
        assert sum(Decimal(str(row[name])) for row in costed['rows']) > 0, name


def test_the_parts_add_up_to_the_documents(costed):
    assert abs(costed['parts_total'] - costed['documents_total']) <= Decimal('1.00')
