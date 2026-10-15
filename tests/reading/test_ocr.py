"""Reading a scan: the picture is turned into text, then read as usual.

The reader stays blind. OCR only replaces the missing text layer; the
same field reader then works on whatever OCR saw.
"""

import pytest

from business import issuers
from drawing import render, scan
from reading import intake, ocr
from simulation import builder

needs_tesseract = pytest.mark.skipif(
    ocr.tesseract() is None, reason='Tesseract is not installed')


def _scanned(folder, code='NCL', seed=3):
    issuer = issuers.by_code(code)
    invoice = builder.invoice_for(issuer, seed=seed)
    pdf = render.build_invoice(folder, invoice, issuer)
    return invoice, scan.scan(pdf, seed=seed)


@needs_tesseract
class TestOcr:
    def test_a_scan_becomes_text(self, tmp_path):
        invoice, pdf = _scanned(tmp_path)

        text = next(ocr.readings(pdf.read_bytes()))

        assert invoice.number in text

    def test_the_store_reads_a_scan_instead_of_giving_up(self, tmp_path):
        invoice, pdf = _scanned(tmp_path)
        store = intake.Store(tmp_path / 'data')

        outcome = store.take(pdf.read_bytes(), pdf.name, '2026-04-06')

        assert outcome.status == 'new'
        row = store.invoices[-1]
        assert row['read_by'] == 'ocr'
        assert row['invoice_number'] == invoice.number

    def test_the_total_survives_the_scan(self, tmp_path):
        invoice, pdf = _scanned(tmp_path)
        store = intake.Store(tmp_path / 'data')

        store.take(pdf.read_bytes(), pdf.name, '2026-04-06')

        assert str(store.invoices[-1]['grand_total']) == \
            str(invoice.grand_total)


def _askew_arl(folder):
    """An ARL invoice the generator scans poor and lays askew."""
    issuer = issuers.by_code('ARL')
    seed = 0
    while True:
        invoice = builder.invoice_for(issuer, seed=seed)
        if scan.chosen(invoice.number) and scan.askew(invoice.number):
            break
        seed += 1
    pdf, _ = render.draw(folder, invoice, issuer)
    return invoice, pdf


class TestAskewPages:
    """ARL lays pages on the glass up to 15 degrees askew. The reader turns
    the page back upright before OCR, or the rows run downhill and break."""

    def test_the_turn_of_an_askew_page_is_found(self, tmp_path):
        page = scan.render_page(_scanned(tmp_path)[1], dpi=100)
        turned = page.rotate(10, expand=True, fillcolor=255)

        assert abs(ocr.skew_of(turned) - 10) <= 1

    def test_a_straight_page_is_left_straight(self, tmp_path):
        page = scan.render_page(_scanned(tmp_path)[1], dpi=100)

        assert abs(ocr.skew_of(page)) <= 1.5

    @needs_tesseract
    @pytest.mark.ocr
    def test_an_askew_poor_scan_is_read_or_flagged_never_wrong(self, tmp_path):
        """At 150 dpi in black and white, OCR reads a 5 as a 6. The sums
        then fail to close, and the row goes to a person."""
        invoice, pdf = _askew_arl(tmp_path)
        store = intake.Store(tmp_path / 'data')

        store.take(pdf.read_bytes(), pdf.name, '2026-04-06')

        row = store.invoices[-1]
        assert row['invoice_number'] == invoice.number
        assert str(row['grand_total']) == str(invoice.grand_total) \
            or row['problems']

    @needs_tesseract
    @pytest.mark.ocr
    def test_an_askew_poor_scan_finds_its_table(self, tmp_path):
        invoice, pdf = _askew_arl(tmp_path)
        store = intake.Store(tmp_path / 'data')

        store.take(pdf.read_bytes(), pdf.name, '2026-04-06')

        assert int(store.invoices[-1]['line_count']) == len(invoice.lines)


class TestTextPdfs:
    def test_a_normal_pdf_is_read_from_its_text(self, tmp_path):
        issuer = issuers.ALL_ISSUERS[0]
        invoice = builder.invoice_for(issuer, seed=3)
        pdf = render.build_invoice(tmp_path, invoice, issuer)
        store = intake.Store(tmp_path / 'data')

        store.take(pdf.read_bytes(), pdf.name, '2026-04-06')

        assert store.invoices[-1]['read_by'] == 'text'


def test_without_tesseract_a_scan_is_unreadable_not_a_crash(tmp_path,
                                                            monkeypatch):
    """A machine with no OCR still files the scan, for a person."""
    monkeypatch.setattr(ocr, 'tesseract', lambda: None)
    _, pdf = _scanned(tmp_path)
    store = intake.Store(tmp_path / 'data')

    outcome = store.take(pdf.read_bytes(), pdf.name, '2026-04-06')

    assert outcome.status == 'unreadable'


class TestOcrSlips:
    """OCR swaps look-alike letters: D for O, 0 for O, 8 for B. An
    invoice number one letter away from the attachment's own name is a
    slip, not a new invoice. The attachment name wins, and the row says
    so, for a person to check."""

    def test_a_one_letter_slip_is_corrected_from_the_attachment(self):
        assert intake.reconcile_number('BOT-2026-1142',
                                       'BDT-2026-1142.pdf') == (
            'BDT-2026-1142',
            'OCR read BOT-2026-1142; the attachment says BDT-2026-1142')

    def test_a_matching_number_is_left_alone(self):
        assert intake.reconcile_number('BDT-2026-1142',
                                       'BDT-2026-1142.pdf') == (
            'BDT-2026-1142', '')

    def test_a_different_invoice_is_not_forced_to_match(self):
        """Two letters apart is another document, not a slip."""
        assert intake.reconcile_number('KNG-2026-3157',
                                       'BDT-2026-1142.pdf') == (
            'KNG-2026-3157', '')

    def test_an_attachment_with_a_plain_name_changes_nothing(self):
        assert intake.reconcile_number('BOT-2026-1142', 'scan001.pdf') == (
            'BOT-2026-1142', '')

    def test_specks_around_the_number_are_wiped(self):
        """A speck of dirt reads as a dot or a dash beside the number."""
        assert intake.reconcile_number('. HCV-2026-4239',
                                       'HCV-2026-4239.pdf')[0] == \
            'HCV-2026-4239'
        assert intake.reconcile_number('-ARL-2026-4195',
                                       'scan.pdf')[0] == 'ARL-2026-4195'

    @pytest.mark.parametrize('read', [
        'SCA-2026-3563Oo', 'ARL-2026-3868|', 'SCA-2026-3943‘',
        'Statementno.SCA-2026-3773'])
    def test_noise_glued_to_the_number_is_cut_off(self, read):
        """Found in the real run: OCR glued a label or a speck to the
        number, and the row went in under a number that does not exist."""
        number = read.replace('Statementno.', '')[:13]
        assert intake.reconcile_number(read, 'scan.pdf')[0] == number

    def test_a_credit_note_and_a_revision_keep_their_marks(self):
        assert intake.reconcile_number('NCL-CN-2026-3123.', 'x.pdf')[0] == \
            'NCL-CN-2026-3123'
        assert intake.reconcile_number('NCL-2026-3123-R1|', 'x.pdf')[0] == \
            'NCL-2026-3123-R1'

    def test_a_space_inside_the_number_is_closed(self):
        assert intake.reconcile_number('NCL-2026-44 16',
                                       'scan.pdf')[0] == 'NCL-2026-4416'


class TestChoosingAReading:
    """OCR is run several ways; the reading whose sums close wins."""

    GOOD = ('FROM\nAcme Ltd.\nInvoice no. ABC-1\nDate 2026-04-11\n'
            'Currency USD\n'
            'Description Qty Unit price Amount\nWidget 2 5.00 10.00\n'
            'Subtotal 10.00\nTotal 10.00\n')
    BAD = GOOD.replace('Widget 2 5.00 10.00', 'Widget 2 5.00 16.00')

    def test_the_first_reading_that_closes_wins(self):
        found, tries = intake.best_reading(iter([self.BAD, self.GOOD]),
                                           'x.pdf')

        assert found.problems == []
        assert tries == 2

    def test_it_stops_as_soon_as_one_closes(self):
        """Every extra pass costs a second of OCR."""
        def readings():
            yield self.GOOD
            raise AssertionError('read again after a clean reading')

        found, tries = intake.best_reading(readings(), 'x.pdf')

        assert tries == 1

    def test_when_none_closes_the_row_is_flagged(self):
        found, _ = intake.best_reading(iter([self.BAD, self.BAD]), 'x.pdf')

        assert any('no OCR reading closed' in p for p in found.problems)
