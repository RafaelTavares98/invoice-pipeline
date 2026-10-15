"""The three questions, and what each answer does to the store.

An invoice number is not an identity. A supplier resends a document, and a
supplier corrects one. Only the bytes of the PDF are unique.
"""

from reading import intake
from simulation import builder
from business import issuers
from drawing import render

WHEN = '2026-05-01T09:00:00'


def _pdf(tmp_path, code='NCL', seed=11, name=None):
    issuer = issuers.by_code(code)
    invoice = builder.invoice_for(issuer, seed=seed)
    if name:
        invoice.number = name
    path = render.build_invoice(tmp_path, invoice, issuer,
                                name=f'{invoice.number}.pdf')
    return invoice, path.read_bytes()


class TestANewDocument:
    def test_it_lands_as_a_new_row(self, tmp_path):
        store = intake.Store(tmp_path / 'data')
        invoice, payload = _pdf(tmp_path)

        outcome = store.take(payload, 'a.pdf', WHEN)

        assert outcome.status == 'new'
        assert outcome.invoice_number == invoice.number
        assert len(store.invoices) == 1

    def test_its_lines_land_too(self, tmp_path):
        store = intake.Store(tmp_path / 'data')
        invoice, payload = _pdf(tmp_path)

        store.take(payload, 'a.pdf', WHEN)

        assert len(store.lines) == len(invoice.lines)

    def test_the_hash_is_what_identifies_it(self, tmp_path):
        store = intake.Store(tmp_path / 'data')
        _, payload = _pdf(tmp_path)

        outcome = store.take(payload, 'a.pdf', WHEN)

        assert outcome.digest in store.state['seen']
        assert len(outcome.digest) == 64


def _spaced(text):
    """The page's text layer keeps one space where the drawing had two."""
    return ' '.join(text.split())


class TestWhereTheMoneyGoes:
    """A wrong account is invisible unless the account and the sender are kept."""

    def test_the_usual_account_is_read_off_the_page(self, tmp_path):
        store = intake.Store(tmp_path / 'data')
        _, payload = _pdf(tmp_path, code='NCL')

        store.take(payload, 'a.pdf', WHEN)

        assert store.invoices[0]['bank_account'] == _spaced(issuers.by_code('NCL').bank_line)

    def test_a_changed_account_is_read_off_the_page(self, tmp_path):
        issuer = issuers.by_code('NCL')
        invoice = builder.invoice_for(issuer, seed=11)
        invoice.pay_to = 'Wise Europe SA  IBAN BE71 9670 1234 5678 9012'
        path = render.build_invoice(tmp_path, invoice, issuer, name='b.pdf')
        store = intake.Store(tmp_path / 'data')

        store.take(path.read_bytes(), 'b.pdf', WHEN)

        assert store.invoices[0]['bank_account'] == _spaced(invoice.pay_to)

    def test_the_sender_is_kept(self, tmp_path):
        store = intake.Store(tmp_path / 'data')
        _, payload = _pdf(tmp_path)

        store.take(payload, 'a.pdf', WHEN, sender='billing@ncl-agent.example')

        assert store.invoices[0]['sender'] == 'billing@ncl-agent.example'


class TestAResend:
    def test_the_same_bytes_twice_is_a_duplicate(self, tmp_path):
        store = intake.Store(tmp_path / 'data')
        _, payload = _pdf(tmp_path)
        store.take(payload, 'a.pdf', WHEN)

        outcome = store.take(payload, 'a-again.pdf', WHEN)

        assert outcome.status == 'duplicate'

    def test_a_duplicate_adds_no_second_row(self, tmp_path):
        store = intake.Store(tmp_path / 'data')
        _, payload = _pdf(tmp_path)
        store.take(payload, 'a.pdf', WHEN)
        store.take(payload, 'a-again.pdf', WHEN)

        assert len(store.invoices) == 1

    def test_a_duplicate_adds_no_second_set_of_lines(self, tmp_path):
        store = intake.Store(tmp_path / 'data')
        invoice, payload = _pdf(tmp_path)
        store.take(payload, 'a.pdf', WHEN)
        store.take(payload, 'a-again.pdf', WHEN)

        assert len(store.lines) == len(invoice.lines)


class TestACorrection:
    def test_a_number_ending_r1_supersedes_the_original(self, tmp_path):
        store = intake.Store(tmp_path / 'data')
        invoice, original = _pdf(tmp_path, seed=11)
        store.take(original, 'a.pdf', WHEN)

        _, revised = _pdf(tmp_path, seed=11, name=f'{invoice.number}-R1')
        outcome = store.take(revised, 'b.pdf', WHEN)

        assert outcome.status == 'revised'
        statuses = {row['invoice_number']: row['status']
                    for row in store.invoices}
        assert statuses[invoice.number] == 'superseded'
        assert statuses[f'{invoice.number}-R1'] == 'revised'

    def test_the_revision_records_what_it_replaces(self, tmp_path):
        store = intake.Store(tmp_path / 'data')
        invoice, original = _pdf(tmp_path, seed=11)
        store.take(original, 'a.pdf', WHEN)
        _, revised = _pdf(tmp_path, seed=11, name=f'{invoice.number}-R1')
        store.take(revised, 'b.pdf', WHEN)

        row = [r for r in store.invoices if r['status'] == 'revised'][0]

        assert row['revises'] == invoice.number

    def test_an_orphan_revision_is_not_a_revision(self, tmp_path):
        """A correction for an invoice that never arrived supersedes
        nothing, because there is nothing to supersede."""
        store = intake.Store(tmp_path / 'data')
        invoice, revised = _pdf(tmp_path, name='NCL-2026-9999-R1')

        outcome = store.take(revised, 'b.pdf', WHEN)

        assert outcome.status == 'new'


class TestWhenItCannotBeRead:
    def test_a_file_that_is_not_a_pdf_still_gets_a_row(self, tmp_path):
        store = intake.Store(tmp_path / 'data')

        outcome = store.take(b'this is not a pdf', 'junk.pdf', WHEN)

        assert outcome.status == 'unreadable'
        assert len(store.invoices) == 1
        assert store.invoices[0]['problems']

    def test_nothing_is_ever_dropped(self, tmp_path):
        store = intake.Store(tmp_path / 'data')
        _, payload = _pdf(tmp_path)
        store.take(payload, 'a.pdf', WHEN)
        store.take(b'rubbish', 'junk.pdf', WHEN)

        assert len(store.invoices) == 2


class TestItSurvivesARestart:
    def test_the_store_reloads_what_it_wrote(self, tmp_path):
        folder = tmp_path / 'data'
        store = intake.Store(folder)
        _, payload = _pdf(tmp_path)
        store.take(payload, 'a.pdf', WHEN)
        store.save()

        reopened = intake.Store(folder)

        assert len(reopened.invoices) == 1
        assert reopened.state['seen'] == store.state['seen']

    def test_a_resend_after_a_restart_is_still_a_duplicate(self, tmp_path):
        folder = tmp_path / 'data'
        store = intake.Store(folder)
        _, payload = _pdf(tmp_path)
        store.take(payload, 'a.pdf', WHEN)
        store.save()

        outcome = intake.Store(folder).take(payload, 'a.pdf', WHEN)

        assert outcome.status == 'duplicate'
