"""Smoke test 3: the broker forwards the file of one past shipment.

Ten PDFs in one mail, all from before today, all naming one B/L: the
goods, the freight, the Santos bills, the duties and the truck. Step 7
costs that shipment from what the reader makes of them.
"""

import email
import json
from datetime import date

import pytest

from drawing import scan
from runs import smoke

pytestmark = pytest.mark.scans

MAIL_LIMIT = 25 * 1024 * 1024


@pytest.fixture(scope='module')
def home(tmp_path_factory):
    return smoke.forward(tmp_path_factory.mktemp('base'))


@pytest.fixture(scope='module')
def truth(home):
    return json.loads((home / 'truth.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def mail(home):
    return email.message_from_bytes((home / 'outbox' / 'forward.eml').read_bytes())


def test_it_lands_in_the_samples_folder_of_its_step(home):
    assert home.parts[-3:] == ('Invoices', 'samples', 'forward')


def test_only_the_broker_holds_a_whole_shipment_file(tmp_path):
    with pytest.raises(ValueError):
        smoke.forward(tmp_path, sender='NCL')


def test_one_mail_carries_exactly_ten_pdfs(mail):
    names = [part.get_filename() for part in mail.walk()
             if part.get_content_type() == 'application/pdf']
    assert len(names) == 10


def test_the_mail_is_under_the_gmail_limit(home):
    assert (home / 'outbox' / 'forward.eml').stat().st_size < MAIL_LIMIT


def test_the_broker_forwards_it(mail):
    assert 'Santos Comissaria' in mail['From']
    assert mail['Subject'].startswith('Fwd: Smoke test 3')


def test_every_document_is_from_this_year_and_before_today(truth):
    for entry in truth:
        issued = date.fromisoformat(entry['issue_date'])
        assert date(2026, 1, 1) <= issued <= date.today()


def test_every_document_names_the_same_shipment(truth):
    assert len({entry['shipment_id'] for entry in truth}) == 1


def test_the_file_holds_every_kind_a_shipment_costs(truth):
    kinds = {(entry['kind'], entry['currency']) for entry in truth}
    assert kinds == {('goods', 'USD'), ('freight', 'USD'), ('local', 'BRL'),
                     ('customs', 'BRL'), ('broker', 'BRL'),
                     ('storage', 'BRL'), ('freight', 'BRL')}


def test_the_generator_decided_every_scan(truth):
    for entry in truth:
        made = (scan.quality(entry['number']).name
                if scan.chosen(entry['number']) else '')
        assert entry['scan'] == made, entry['file']
