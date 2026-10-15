"""Some invoices arrive as scans: a picture of paper, with no text in it.

Scanning is the habit of two issuers, ARL and SCA, decided by the
invoice number so the same invoice is always scanned or always not. A
scan is tilted, speckled and blurred a little, the way an office scanner
leaves a page, and it carries no text layer: nothing can be selected or
copied out of it.
"""

import pdfplumber

from business import issuers
from drawing import render, scan
from simulation import builder


def _invoice_pdf(folder):
    issuer = issuers.ALL_ISSUERS[0]
    invoice = builder.invoice_for(issuer, seed=3)
    return render.build_invoice(folder, invoice, issuer)


def _share(code, test):
    numbers = [f'{code}-2026-{n:04d}' for n in range(3000)]
    return sum(test(n) for n in numbers) / len(numbers)


class TestChoosing:
    """Scanning is a habit of the issuer: ARL scans most, SCA now and
    then, everyone else never."""

    def test_arl_scans_about_six_in_ten(self):
        assert 0.55 <= _share('ARL', scan.chosen) <= 0.65

    def test_sca_scans_about_three_in_ten(self):
        assert 0.25 <= _share('SCA', scan.chosen) <= 0.35

    def test_the_others_never_scan(self):
        for code in ('NCL', 'SBP', 'GZV', 'HCV', 'BDT', 'DHI', 'MRK', 'CSM',
                     'KNG', 'TLV', 'TVA'):
            assert _share(code, scan.chosen) == 0, code

    def test_half_of_arl_pages_go_in_askew_and_sca_never(self):
        assert 0.45 <= _share('ARL', scan.askew) <= 0.55
        assert _share('SCA', scan.askew) == 0

    def test_the_choice_never_changes(self):
        """A resend of a scanned invoice is the same scan."""
        assert scan.chosen('ARL-2026-3157') == scan.chosen('ARL-2026-3157')


class TestScanning:
    def test_a_scan_has_no_text_layer(self, tmp_path):
        pdf = scan.scan(_invoice_pdf(tmp_path), seed=1)

        with pdfplumber.open(pdf) as document:
            text = ''.join(page.extract_text() or '' for page in document.pages)
        assert text.strip() == ''

    def test_a_scan_is_still_a_one_page_pdf(self, tmp_path):
        pdf = scan.scan(_invoice_pdf(tmp_path), seed=1)

        with pdfplumber.open(pdf) as document:
            assert len(document.pages) == 1

    def test_the_same_seed_gives_the_same_scan(self, tmp_path):
        (tmp_path / 'a').mkdir()
        (tmp_path / 'b').mkdir()
        first = scan.scan(_invoice_pdf(tmp_path / 'a'), seed=7).read_bytes()
        second = scan.scan(_invoice_pdf(tmp_path / 'b'), seed=7).read_bytes()

        assert first == second

    def test_the_page_is_not_left_perfectly_straight(self, tmp_path):
        """A scan that is a clean render teaches the reader nothing."""
        page = scan.degrade(scan.render_page(_invoice_pdf(tmp_path)), seed=1)

        assert page.mode == 'L'
        assert scan.tilt_degrees(seed=1) != 0


class TestQualities:
    """Scanners differ. SCA's office scanner sends clean grey pages; ARL's
    old machine, black and white at 150 dpi."""

    def test_each_issuer_keeps_its_own_scanner(self):
        assert scan.quality('ARL-2026-0001').name == 'poor'
        assert scan.quality('SCA-2026-0001').name == 'good'

    def test_the_poor_scan_is_black_and_white_at_150_dpi(self):
        poor = scan.QUALITIES['poor']

        assert poor.dpi == 150
        assert poor.black_and_white is True

    def test_a_poor_scan_really_is_black_and_white(self, tmp_path):
        page = scan.degrade(scan.render_page(_invoice_pdf(tmp_path),
                                             dpi=scan.QUALITIES['poor'].dpi),
                            seed=1, quality=scan.QUALITIES['poor'])

        assert page.mode == '1'


class TestAskew:
    """ARL lays pages on the glass up to 15 degrees off upright; the scan
    is still a portrait A4 sheet with every printed mark on it."""

    def test_an_askew_scan_is_a_portrait_a4_sheet(self, tmp_path):
        pdf = scan.scan(_invoice_pdf(tmp_path), seed=1,
                        chosen_quality=scan.QUALITIES['poor'], fed_askew=True)

        with pdfplumber.open(pdf) as document:
            page = document.pages[0]
            assert round(page.width / 72 * 25.4) == 210
            assert round(page.height / 72 * 25.4) == 297

    def test_the_turn_stays_within_15_degrees(self):
        for seed in range(200):
            assert 0 <= abs(scan.askew_degrees(seed)) <= 15

    def test_nothing_printed_falls_off_the_sheet(self, tmp_path):
        from PIL import ImageOps
        clean = scan._trimmed(scan.render_page(_invoice_pdf(tmp_path), dpi=150))
        for seed in range(20):
            sheet = scan._laid_askew(clean, seed, scan.a4_sheet(150))
            left, top, right, bottom = ImageOps.invert(sheet).getbbox()
            assert left > 0 and top > 0
            assert right < sheet.width and bottom < sheet.height
