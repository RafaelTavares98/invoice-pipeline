import email
import email.policy
from pathlib import Path

import invoice_builder
import issuers
import mail_delivery
import mail_sources
import render
from buyer import MOTY

ACCOUNT = 'someone@example.com'


def _one(issuer_code, tmp_path):
    issuer = issuers.by_code(issuer_code)
    invoice = invoice_builder.invoice_for(issuer, seed=3)
    pdf = render.build_invoice(tmp_path, invoice, issuer)
    return issuer, invoice, pdf


class TestTheEnvelope:
    def test_the_issuer_name_is_on_the_envelope(self, tmp_path):
        issuer, invoice, pdf = _one('NCL', tmp_path)

        mail = mail_delivery.build_message(issuer, invoice, pdf, ACCOUNT, ACCOUNT)

        # A name holding a comma is quoted by the mail library, so the
        # header reads "Ningbo Caplink Industrial Co., Ltd." <...>
        assert issuer.name in mail['From']

    def test_the_address_underneath_is_the_one_real_account(self, tmp_path):
        issuer, invoice, pdf = _one('NCL', tmp_path)

        mail = mail_delivery.build_message(issuer, invoice, pdf, ACCOUNT, ACCOUNT)

        assert 'someone+ncl@example.com' in mail['From']

    def test_every_issuer_gets_its_own_tag(self):
        tags = {mail_delivery.tag_for(issuer) for issuer in issuers.ALL_ISSUERS}

        assert len(tags) == len(issuers.ALL_ISSUERS)

    def test_no_issuer_pretends_to_own_a_domain(self):
        for issuer in issuers.ALL_ISSUERS:
            sender = mail_delivery.sender_for(issuer, ACCOUNT)

            assert sender.endswith('@example.com>')


class TestTheSubject:
    def test_the_invoice_number_is_always_in_the_subject(self, tmp_path):
        for issuer in issuers.ALL_ISSUERS:
            invoice = invoice_builder.invoice_for(issuer, seed=9)

            assert invoice.number in mail_delivery.subject_for(issuer, invoice)

    def test_a_reference_is_never_prefixed_twice(self):
        for issuer in issuers.ALL_ISSUERS:
            invoice = invoice_builder.invoice_for(issuer, seed=9)
            line = mail_delivery.subject_for(issuer, invoice)

            assert 'PO PO-' not in line
            assert 'B/L B/L' not in line
            assert 'AWB AWB' not in line

    def test_the_issuers_do_not_agree_on_a_format(self):
        shapes = set()
        for issuer in issuers.ALL_ISSUERS:
            invoice = invoice_builder.invoice_for(issuer, seed=9)
            line = mail_delivery.subject_for(issuer, invoice)
            shapes.add(line.replace(invoice.number, '#')
                           .replace(invoice.reference, '@'))

        assert len(shapes) >= 8


class TestTheAttachment:
    def test_the_pdf_rides_along(self, tmp_path):
        issuer, invoice, pdf = _one('MRK', tmp_path)

        mail = mail_delivery.build_message(issuer, invoice, pdf, ACCOUNT, ACCOUNT)
        attached = [part for part in mail.walk() if part.get_filename()]

        assert len(attached) == 1
        assert attached[0].get_payload(decode=True) == Path(pdf).read_bytes()

    def test_the_body_names_moty_and_the_total(self, tmp_path):
        issuer, invoice, pdf = _one('MRK', tmp_path)

        mail = mail_delivery.build_message(issuer, invoice, pdf, ACCOUNT, ACCOUNT)
        body = mail.get_body(preferencelist=('plain',)).get_content()

        assert MOTY.name in body
        assert str(invoice.grand_total) in body


class TestDryRun:
    def test_a_dry_run_opens_no_connection(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mail_delivery, '_account',
                            lambda: (ACCOUNT, 'not-used'))
        monkeypatch.setattr(mail_delivery, '_server', _explode)
        written = [_one(code, tmp_path) for code in ('NCL', 'MRK')]

        sent = mail_delivery.send_invoices(written, ACCOUNT, dry_run=True)

        assert len(sent) == 2
        assert sent[0].invoice_number == written[0][1].number


class TestTheFolderMailbox:
    def test_a_written_mail_reads_back(self, tmp_path):
        issuer, invoice, pdf = _one('SBP', tmp_path)
        box = tmp_path / 'inbox'

        mail_sources.write_message(
            box, invoice.number, f'Invoice {invoice.number}',
            [(Path(pdf).name, Path(pdf).read_bytes())],
            sender=mail_delivery.sender_for(issuer, ACCOUNT),
        )
        found = list(mail_sources.LocalMailbox(box).messages())

        assert len(found) == 1
        assert invoice.number in found[0].subject
        assert issuer.name in found[0].sender

    def test_only_pdf_attachments_come_through(self, tmp_path):
        box = tmp_path / 'inbox'
        mail_sources.write_message(box, 'M1', 'Invoice', [('a.pdf', b'%PDF-1')])
        raw = (box / 'M1.eml').read_bytes()
        parsed = email.message_from_bytes(raw, policy=email.policy.default)
        parsed.add_attachment(b'\x89PNG', maintype='image', subtype='png',
                              filename='signature.png')
        (box / 'M1.eml').write_bytes(parsed.as_bytes())

        found = list(mail_sources.LocalMailbox(box).messages())

        assert [name for name, _ in found[0].attachments] == ['a.pdf']

    def test_an_empty_folder_yields_nothing(self, tmp_path):
        assert list(mail_sources.LocalMailbox(tmp_path / 'nope').messages()) == []


def _explode(*_):
    raise AssertionError('a dry run must not open a connection')
