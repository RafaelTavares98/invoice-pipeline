"""Smoke test 2: one mail from each sender, every flavour.

Every sender, every kind of document, scans of each quality, each error
and its honest twin. The mail is what is measured; these tests post it
to a folder.
"""

import email
import json

import pdfplumber
import pytest

from drawing import scan
from runs import smoke
from simulation import anomalies

#: The scans are one of the flavours, so the issuers keep their habits.
pytestmark = pytest.mark.scans

SENDERS = {'NCL', 'SBP', 'GZV', 'HCV', 'BDT', 'ARL', 'DHI', 'MRK', 'CSM',
           'KNG', 'TLV', 'SCA', 'TVA'}


@pytest.fixture(scope='module')
def home(tmp_path_factory):
    return smoke.senders(tmp_path_factory.mktemp('base'))


@pytest.fixture(scope='module')
def truth(home):
    return json.loads((home / 'truth.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def mails(home):
    return {path.stem: email.message_from_bytes(path.read_bytes())
            for path in (home / 'outbox').glob('*.eml')}


def _pdfs(mail):
    return [part.get_filename() for part in mail.walk()
            if part.get_content_type() == 'application/pdf']


def _body(mail):
    return next(part.get_payload(decode=True).decode('utf-8')
                for part in mail.walk() if part.get_content_type() == 'text/plain')


def test_it_lands_in_the_samples_folder_of_its_step(home):
    assert home.parts[-3:] == ('Invoices', 'samples', 'senders')


def test_one_mail_per_sender_and_per_newcomer(mails):
    assert SENDERS <= set(mails)
    assert len(mails) == len(SENDERS) + 2


def test_every_mail_carries_its_senders_documents(mails, truth):
    for code, mail in mails.items():
        mine = {t['file'] for t in truth if t['mail'] == code}
        assert set(_pdfs(mail)) == mine, code


def test_the_body_tells_who_the_sender_is(mails):
    for code, mail in mails.items():
        body = _body(mail)
        assert 'What it does' in body, code
        assert 'How the simulation draws it' in body, code
        assert 'invented' in body.lower(), code


def test_each_sender_sends_its_own_kinds(truth):
    kinds = {}
    for t in truth:
        kinds.setdefault(t['mail'], set()).add((t['kind'], t['currency']))
    for code in ('NCL', 'SBP', 'GZV', 'HCV', 'BDT', 'ARL'):
        assert ('goods', 'USD') in kinds[code], code
    for code in ('MRK', 'CSM'):
        assert {('freight', 'USD'), ('local', 'BRL')} <= kinds[code], code
    assert {('freight', 'USD'), ('local', 'BRL')} <= kinds['DHI']
    assert {('customs', 'BRL'), ('broker', 'BRL')} <= kinds['SCA']
    assert kinds['TVA'] == {('storage', 'BRL')}
    assert ('freight', 'BRL') in kinds['TLV']
    assert ('freight', 'USD') in kinds['KNG']


def test_dhi_sends_lcl_and_air(truth):
    units = {t['first_unit'] for t in truth
             if t['mail'] == 'DHI' and t['kind'] == 'freight'}

    assert units == {'W/M', 'kg'}


def test_every_error_and_every_twin_appears(truth):
    planted = {t['anomaly'] for t in truth if t['anomaly']}
    twins = {t['lookalike_of'] for t in truth if t['lookalike_of']}

    assert planted == set(anomalies.KINDS)
    assert twins == set(anomalies.KINDS)


def test_only_arl_and_sca_send_scans(truth):
    assert {t['issuer'] for t in truth if t['scan']} == {'ARL', 'SCA'}


def test_the_generator_decided_every_scan(truth):
    for t in truth:
        made = scan.quality(t['number']).name if scan.chosen(t['number']) else ''
        assert t['scan'] == made, t['file']
        assert t['askew'] == scan.askew(t['number']), t['file']


def test_arl_sends_a_poor_scan_laid_askew(truth):
    assert any(t['scan'] == 'poor' and t['askew']
               for t in truth if t['issuer'] == 'ARL')


def test_sca_sends_a_good_straight_scan(truth):
    assert any(t['scan'] == 'good' and not t['askew']
               for t in truth if t['issuer'] == 'SCA')


def test_nothing_on_a_scan_can_be_selected(home, truth):
    for t in truth:
        if t['scan']:
            assert not pdfplumber.open(home / t['file']).pages[0].chars, t['file']


def test_every_text_pdf_prints_its_total(home, truth):
    for t in truth:
        if t['scan']:
            continue
        text = pdfplumber.open(home / t['file']).pages[0].extract_text()
        total = t['grand_total']
        printed = {f'{float(total):,.2f}',
                   f'{float(total):,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')}
        assert any(p in text for p in printed), t['file']


def test_brl_pages_say_brl(home, truth):
    for t in truth:
        if t['currency'] == 'BRL' and not t['scan']:
            text = pdfplumber.open(home / t['file']).pages[0].extract_text()
            assert 'USD' not in text, t['file']


def test_each_sender_numbers_its_documents_without_a_gap(tmp_path):
    home = smoke.senders(tmp_path)
    truth = json.loads((home / 'truth.json').read_text(encoding='utf-8'))
    by_mail = {}
    for entry in truth:
        by_mail.setdefault(entry['mail'], []).append(int(entry['number'][-4:]))
    for mail, counts in by_mail.items():
        first = min(counts)
        assert sorted(counts) == list(range(first, first + len(counts))), mail
