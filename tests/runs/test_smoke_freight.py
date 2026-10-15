"""Smoke test 1: one mail with an FCL and an LCL freight invoice.

What is measured is the mail: two PDFs attached, each the invoice its
answer key says. These tests post the mail to a folder; the real send to
Gmail is the same mail.
"""

import email
import json

from runs import smoke


def _the_mail(folder):
    files = list((folder / 'outbox').glob('*.eml'))
    assert len(files) == 1
    return email.message_from_bytes(files[0].read_bytes())


def test_it_lands_in_the_samples_folder_of_its_step(tmp_path):
    home = smoke.freight(tmp_path)

    assert home == tmp_path / 'Invoices' / 'samples' / 'freight'


def test_it_draws_two_pdfs_and_their_answers(tmp_path):
    home = smoke.freight(tmp_path)

    assert len(list(home.glob('*.pdf'))) == 2
    truth = json.loads((home / 'truth.json').read_text(encoding='utf-8'))
    assert sorted(t['issuer'] for t in truth) == ['DHI', 'MRK']


def test_the_mail_carries_both_pdfs(tmp_path):
    home = smoke.freight(tmp_path)
    mail = _the_mail(home)

    names = [part.get_filename() for part in mail.walk()
             if part.get_content_type() == 'application/pdf']
    assert sorted(names) == sorted(p.name for p in home.glob('*.pdf'))


def test_the_mail_says_what_it_is(tmp_path):
    mail = _the_mail(smoke.freight(tmp_path))

    assert 'FCL' in mail['Subject'] and 'LCL' in mail['Subject']


def test_the_lcl_page_shows_its_wm_with_cents(tmp_path):
    """6.80 W/M, not 6: the units column is what a person multiplies. The
    weight and volume columns show the cargo it was measured on."""
    import pdfplumber
    home = smoke.freight(tmp_path)
    page = pdfplumber.open(next(home.glob('DHI-*.pdf'))).pages[0]

    assert 'Ningbo to Santos 6.80 1,240.00 6.80 95.00 646.00' in \
        page.extract_text()


def test_the_answer_key_matches_the_charge(tmp_path):
    from decimal import Decimal
    from simulation import freight
    truth = json.loads((smoke.freight(tmp_path) / 'truth.json')
                       .read_text(encoding='utf-8'))
    totals = {t['issuer']: Decimal(t['grand_total']) for t in truth}

    assert totals['MRK'] == freight.FCL_RATE['40GP']
    assert totals['DHI'] == (Decimal('6.80') * freight.LCL_RATE).quantize(Decimal('0.01'))
