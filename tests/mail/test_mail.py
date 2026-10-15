import email
import email.policy
from pathlib import Path

from simulation import builder
from business import issuers
from mail import delivery
from mail import sources
from drawing import render
from business.buyer import MOTY

ACCOUNT = 'someone@example.com'


def _one(issuer_code, tmp_path):
    issuer = issuers.by_code(issuer_code)
    invoice = builder.invoice_for(issuer, seed=3)
    pdf = render.build_invoice(tmp_path, invoice, issuer)
    return issuer, invoice, pdf


class TestTheEnvelope:
    def test_the_issuer_name_is_on_the_envelope(self, tmp_path):
        issuer, invoice, pdf = _one('NCL', tmp_path)

        mail = delivery.build_message(issuer, invoice, pdf, ACCOUNT, ACCOUNT)

        # A name holding a comma is quoted by the mail library, so the
        # header reads "Ningbo Caplink Industrial Co., Ltd." <...>
        assert issuer.name in mail['From']

    def test_the_address_underneath_is_the_one_real_account(self, tmp_path):
        issuer, invoice, pdf = _one('NCL', tmp_path)

        mail = delivery.build_message(issuer, invoice, pdf, ACCOUNT, ACCOUNT)

        assert 'someone+ncl@example.com' in mail['From']

    def test_every_issuer_gets_its_own_tag(self):
        tags = {delivery.tag_for(issuer) for issuer in issuers.ALL_ISSUERS}

        assert len(tags) == len(issuers.ALL_ISSUERS)

    def test_no_issuer_pretends_to_own_a_domain(self):
        for issuer in issuers.ALL_ISSUERS:
            sender = delivery.sender_for(issuer, ACCOUNT)

            assert sender.endswith('@example.com>')


class TestTheSubject:
    def test_the_invoice_number_is_always_in_the_subject(self, tmp_path):
        for issuer in issuers.ALL_ISSUERS:
            invoice = builder.invoice_for(issuer, seed=9)

            assert invoice.number in delivery.subject_for(issuer, invoice)

    def test_a_reference_is_never_prefixed_twice(self):
        for issuer in issuers.ALL_ISSUERS:
            invoice = builder.invoice_for(issuer, seed=9)
            line = delivery.subject_for(issuer, invoice)

            assert 'PO PO-' not in line
            assert 'B/L B/L' not in line
            assert 'AWB AWB' not in line

    def test_the_issuers_do_not_agree_on_a_format(self):
        shapes = set()
        for issuer in issuers.ALL_ISSUERS:
            invoice = builder.invoice_for(issuer, seed=9)
            line = delivery.subject_for(issuer, invoice)
            shapes.add(line.replace(invoice.number, '#')
                           .replace(invoice.reference, '@'))

        assert len(shapes) >= 8


class TestTheAttachment:
    def test_the_pdf_rides_along(self, tmp_path):
        issuer, invoice, pdf = _one('MRK', tmp_path)

        mail = delivery.build_message(issuer, invoice, pdf, ACCOUNT, ACCOUNT)
        attached = [part for part in mail.walk() if part.get_filename()]

        assert len(attached) == 1
        assert attached[0].get_payload(decode=True) == Path(pdf).read_bytes()

    def test_the_body_names_moty_and_the_total(self, tmp_path):
        issuer, invoice, pdf = _one('MRK', tmp_path)

        mail = delivery.build_message(issuer, invoice, pdf, ACCOUNT, ACCOUNT)
        body = mail.get_body(preferencelist=('plain',)).get_content()

        assert MOTY.name in body
        assert str(invoice.grand_total) in body


class TestTheFolderMailbox:
    def test_a_written_mail_reads_back(self, tmp_path):
        issuer, invoice, pdf = _one('SBP', tmp_path)
        box = tmp_path / 'inbox'

        sources.write_message(
            box, invoice.number, f'Invoice {invoice.number}',
            [(Path(pdf).name, Path(pdf).read_bytes())],
            sender=delivery.sender_for(issuer, ACCOUNT),
        )
        found = list(sources.LocalMailbox(box).messages())

        assert len(found) == 1
        assert invoice.number in found[0].subject
        assert issuer.name in found[0].sender

    def test_only_pdf_attachments_come_through(self, tmp_path):
        box = tmp_path / 'inbox'
        sources.write_message(box, 'M1', 'Invoice', [('a.pdf', b'%PDF-1')])
        raw = (box / 'M1.eml').read_bytes()
        parsed = email.message_from_bytes(raw, policy=email.policy.default)
        parsed.add_attachment(b'\x89PNG', maintype='image', subtype='png',
                              filename='signature.png')
        (box / 'M1.eml').write_bytes(parsed.as_bytes())

        found = list(sources.LocalMailbox(box).messages())

        assert [name for name, _ in found[0].attachments] == ['a.pdf']

    def test_an_empty_folder_yields_nothing(self, tmp_path):
        assert list(sources.LocalMailbox(tmp_path / 'nope').messages()) == []


class TestOneConnection:
    """A backlog is hundreds of mails. Logging in once per mail made the
    send take most of an hour; one connection carries them all, and a
    dropped one is opened again."""

    def test_many_mails_share_one_login(self, monkeypatch):
        from email.message import EmailMessage
        from mail import delivery
        logins, sent = [], []

        class Server:
            def send_message(self, mail):
                sent.append(mail)

            def quit(self):
                pass

        monkeypatch.setattr(delivery, '_account', lambda: ('a@b.c', 'pw'))
        monkeypatch.setattr(delivery, '_server',
                            lambda *a: logins.append(1) or Server())
        with delivery.Session() as session:
            for _ in range(5):
                session.send(EmailMessage())

        assert len(sent) == 5 and len(logins) == 1

    def test_a_dropped_connection_is_opened_again(self, monkeypatch):
        import smtplib
        from email.message import EmailMessage
        from mail import delivery
        logins, sent = [], []

        class Flaky:
            def __init__(self):
                self.calls = 0

            def send_message(self, mail):
                self.calls += 1
                if len(logins) == 1 and self.calls == 2:
                    raise smtplib.SMTPServerDisconnected('gone')
                sent.append(mail)

            def quit(self):
                pass

        monkeypatch.setattr(delivery, '_account', lambda: ('a@b.c', 'pw'))
        monkeypatch.setattr(delivery, '_server',
                            lambda *a: logins.append(1) or Flaky())
        with delivery.Session() as session:
            for _ in range(3):
                session.send(EmailMessage())

        assert len(sent) == 3 and len(logins) == 2
