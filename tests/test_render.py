import pytest
from pypdf import PdfReader

import invoice_builder
import issuers
import render
from buyer import MOTY


@pytest.fixture(params=[issuer.code for issuer in issuers.ALL_ISSUERS])
def rendered(request, tmp_path):
    issuer = issuers.by_code(request.param)
    invoice = invoice_builder.invoice_for(issuer, seed=42)
    path = render.build_invoice(tmp_path, invoice, issuer)
    return issuer, invoice, path, PdfReader(path).pages[0].extract_text()


class TestFileFormat:
    def test_the_invoice_is_a_pdf_file(self, rendered):
        _, _, path, _ = rendered

        assert path.read_bytes().startswith(b'%PDF')

    def test_the_invoice_is_a_single_page(self, rendered):
        _, _, path, _ = rendered

        assert len(PdfReader(path).pages) == 1


class TestWhoIsOnThePage:
    def test_the_issuer_is_named(self, rendered):
        issuer, _, _, text = rendered

        assert issuer.name in text

    def test_moty_is_always_the_one_billed(self, rendered):
        _, _, _, text = rendered

        assert MOTY.name in text
        assert MOTY.tax_id in text

    def test_moty_never_issues(self):
        for issuer in issuers.ALL_ISSUERS:
            assert issuer.name != MOTY.name


class TestWhatIsOnThePage:
    def test_the_invoice_number_is_printed(self, rendered):
        _, invoice, _, text = rendered

        assert invoice.number in text

    def test_the_tax_number_of_the_issuer_is_printed(self, rendered):
        issuer, _, _, text = rendered

        assert issuer.tax_id in text

    def test_every_line_description_is_printed(self, rendered):
        _, invoice, _, text = rendered

        for line in invoice.lines:
            assert line.description[:28] in text

    def test_the_grand_total_is_printed(self, rendered):
        issuer, invoice, _, text = rendered
        from formatting import format_amount

        assert format_amount(invoice.grand_total, issuer.decimal_mark) in text

    def test_the_subtotal_reconciles_with_the_printed_lines(self, rendered):
        _, invoice, _, _ = rendered
        from decimal import Decimal

        visible = sum((line.net for line in invoice.lines), Decimal('0.00'))

        assert visible == invoice.subtotal


class TestCurrency:
    def test_every_issuer_bills_in_dollars(self):
        for issuer in issuers.ALL_ISSUERS:
            assert issuer.currency == 'USD'

    def test_the_page_says_the_amounts_are_in_dollars(self, rendered):
        _, _, _, text = rendered

        assert 'United States dollars' in text

    def test_no_other_currency_code_reaches_the_page(self, rendered):
        _, _, _, text = rendered

        for code in ('BRL', 'CNY', 'EUR', 'KRW', 'CHF', 'INR', 'HKD'):
            assert code not in text


class TestIssuerHabits:
    def test_a_freight_invoice_is_landscape(self):
        from layouts import layout_for

        for carrier in issuers.CARRIERS:
            assert layout_for(carrier).landscape

    def test_a_goods_invoice_is_portrait(self):
        from layouts import layout_for

        for factory in issuers.FACTORIES:
            assert not layout_for(factory).landscape

    def test_no_two_issuers_share_a_code(self):
        codes = [issuer.code for issuer in issuers.ALL_ISSUERS]

        assert len(codes) == len(set(codes))

    def test_every_style_has_a_table_and_a_totals_block(self):
        import page_styles

        for issuer in issuers.ALL_ISSUERS:
            assert issuer.style in page_styles.TABLES
            assert issuer.style in page_styles.TOTALS
