"""The reader is blind, and these tests keep it that way.

Every case here is plain text. None of them imports `issuers`, `layouts` or
anything else the generator knows, because the moment the reader is allowed
to look those up it stops proving anything.
"""

from datetime import date
from decimal import Decimal

from reading import fields

GOODS_PAGE = """COMMERCIAL INVOICE
FROM
Ningbo Caplink Industrial Co., Ltd.
Invoice no. NCL-2026-3140
No. 288 Jiangnan Road, Yinzhou District
Ningbo, Zhejiang 315100
China
USCC: 91330212MA2AF3K17H
BILL TO SHIP TO Invoice no. NCL-2026-3140
Moty Cosmeticos Ltda. Moty Cosmeticos Ltda. Date of issue 2026-04-11
Attn: Production and Logistics Cost Management Inbound Dock 2 Payment due 2026-05-21
Rodovia Anhanguera, km 94, Galpao 3 Rodovia Anhanguera, km 94 Currency USD
Louveira, SP 13290-000 Louveira, SP 13290-000 Reference PO-41021
Brazil Brazil Incoterm FOB Ningbo
CNPJ: 18.442.907/0001-55
costs@moty.example
Part no. Description of goods HS code Qty Unit price Amount USD
PM-024G Lotion pump, 24/410, 1.2 cc, silver collar 8424.89 100,000 0.212 21,200.00
DR-030J Dropper assembly, 30 ml, graduated pipette 7010.90 60,000 0.324 19,440.00
Subtotal 40,640.00
Total USD 40,640.00
FOB Ningbo. T/T 30% deposit, balance against B/L copy.
Bank of Ningbo SWIFT BKNBCN2N Acct 7801 4455 2190
All amounts in United States dollars."""

FREIGHT_PAGE = """FREIGHT INVOICE
FROM
Marsk Line Agencies B.V.
Invoice no. MRK-2026-8743
Pier 9, Terminal Road
Rotterdam 3089 JS
Netherlands
VAT ID: NL 8201 55 913 B01
BILL TO SHIP TO Invoice no. MRK-2026-8743
Moty Cosmeticos Ltda. Moty Cosmeticos Ltda. Invoice date 2026-04-18
Attn: Production and Logistics Cost Management Inbound Dock 2 Due 2026-05-18
Rodovia Anhanguera, km 94, Galpao 3 Rodovia Anhanguera, km 94 Currency USD
Louveira, SP 13290-000 Louveira, SP 13290-000 Reference B/L MRK1558444
ORIGIN DESTINATION EQUIPMENT VESSEL GROSS WEIGHT KG VOLUME M3
Ningbo Santos 40GP MV Ever Dawn / voy. 43E 10116.6 34.06
Charge description Units Weight kg Volume m3 Rate Amount USD
Ocean freight Ningbo to Santos, 40GP 1 10,116.60 34.06 1,897.03 1,897.03
Bunker adjustment factor 1 915.36 915.36
Documentation fee 1 59.32 59.32
Subtotal 2,871.71
Total USD 2,871.71
Ocean freight per service contract MRK-2026-114.
All amounts in United States dollars."""

COMMA_PAGE = """COMMERCIAL INVOICE
FROM
Aravalli Labelworks Pvt. Ltd.
Invoice no. ARL-2026-3135
Plot 42, Sector 8, IMT Manesar
Gurugram, Haryana 122051
India
GSTIN: 06AAFCA9321L1ZP
BILL TO Invoice no. ARL-2026-3135
Moty Cosmeticos Ltda. Date of issue 23/04/2026
Louveira, SP 13290-000 Payment due 22/06/2026
Brazil Reference PO-41027
Part no. Description of goods HS code Qty Unit price Amount USD
LB-GL01 Adhesive label, 4 colour, gloss laminate 4821.10 400.000 0,0283 11.320,00
Subtotal 11.320,00
Total USD 11.320,00"""


class TestTheDecimalMark:
    def test_a_dot_page_is_read_as_a_dot_page(self):
        assert fields.read(GOODS_PAGE).decimal_mark == 'dot'

    def test_a_comma_page_is_read_as_a_comma_page(self):
        assert fields.read(COMMA_PAGE).decimal_mark == 'comma'

    def test_the_mark_decides_how_a_total_is_read(self):
        assert fields.read(COMMA_PAGE).grand_total == Decimal('11320.00')


class TestTheDateOrder:
    def test_iso_is_recognised(self):
        assert fields.read(GOODS_PAGE).date_order == 'iso'

    def test_a_day_above_twelve_settles_a_slashed_date(self):
        assert fields.read(COMMA_PAGE).date_order == 'day_first'

    def test_the_date_is_read_in_the_order_it_was_written(self):
        assert fields.read(COMMA_PAGE).issue_date == date(2026, 4, 23)


class TestTheHeader:
    def test_the_issuer_is_the_name_under_from(self):
        assert fields.read(GOODS_PAGE).issuer == \
               'Ningbo Caplink Industrial Co., Ltd.'

    def test_the_invoice_number_is_found(self):
        assert fields.read(GOODS_PAGE).number == 'NCL-2026-3140'

    def test_the_issue_date_is_found(self):
        assert fields.read(GOODS_PAGE).issue_date == date(2026, 4, 11)

    def test_the_due_date_is_found(self):
        assert fields.read(GOODS_PAGE).due_date == date(2026, 5, 21)

    def test_the_order_number_is_found_anywhere_on_the_page(self):
        assert fields.read(GOODS_PAGE).order_number == 'PO-41021'

    def test_a_bill_of_lading_is_found(self):
        assert fields.read(FREIGHT_PAGE).shipment_id == 'B/L MRK1558444'


class TestTheTotals:
    def test_the_subtotal_is_found(self):
        assert fields.read(GOODS_PAGE).subtotal == Decimal('40640.00')

    def test_the_grand_total_is_found(self):
        assert fields.read(GOODS_PAGE).grand_total == Decimal('40640.00')

    def test_total_usd_is_not_mistaken_for_subtotal(self):
        found = fields.read(FREIGHT_PAGE)

        assert found.subtotal == found.grand_total == Decimal('2871.71')


class TestTheTable:
    def test_a_goods_table_gives_one_row_per_item(self):
        assert len(fields.read(GOODS_PAGE).lines) == 2

    def test_a_row_carries_quantity_price_and_amount(self):
        line = fields.read(GOODS_PAGE).lines[0]

        assert line.quantity == Decimal('100000')
        assert line.unit_price == Decimal('0.212')
        assert line.net == Decimal('21200.00')

    def test_a_description_keeps_the_numbers_that_belong_to_it(self):
        line = fields.read(GOODS_PAGE).lines[0]

        assert '24/410' in line.description
        assert '1.2 cc' in line.description

    def test_the_rows_add_up_to_the_printed_subtotal(self):
        found = fields.read(GOODS_PAGE)

        assert sum(line.net for line in found.lines) == found.subtotal


class TestWhatIsNotATableRow:
    def test_an_address_is_not_a_row(self):
        descriptions = [l.description for l in fields.read(GOODS_PAGE).lines]

        assert not any('Rodovia' in text for text in descriptions)

    def test_a_tax_number_is_not_a_row(self):
        descriptions = [l.description for l in fields.read(GOODS_PAGE).lines]

        assert not any('CNPJ' in text for text in descriptions)

    def test_a_bank_account_below_the_table_is_not_a_row(self):
        """`Acct 3602 0012 9100` once read as a line item worth 9,100."""
        found = fields.read(GOODS_PAGE)

        assert not any('Acct' in l.description for l in found.lines)
        assert Decimal('9100') not in [l.net for l in found.lines]


class TestTheFreightTable:
    def test_a_container_is_one_unit_not_its_volume(self):
        """The quantity column sits five figures from the right here, not
        three, because weight and volume stand in between."""
        line = fields.read(FREIGHT_PAGE).lines[0]

        assert line.quantity == Decimal('1')

    def test_a_surcharge_row_with_empty_cells_still_reads(self):
        rows = fields.read(FREIGHT_PAGE).lines

        assert rows[1].description == 'Bunker adjustment factor'
        assert rows[1].net == Decimal('915.36')

    def test_the_shipment_strip_above_the_table_is_not_read_as_rows(self):
        descriptions = [l.description for l in fields.read(FREIGHT_PAGE).lines]

        assert not any('Ever Dawn' in text for text in descriptions)


class TestWhenThePageIsWrong:
    def test_an_empty_page_is_reported_not_invented(self):
        found = fields.read('')

        assert found.number == ''
        assert found.grand_total is None
        assert 'no invoice number' in found.problems
        assert 'no table rows' in found.problems

    def test_a_page_with_no_table_says_so(self):
        found = fields.read('FROM\nSomebody Ltd.\nInvoice no. ABC-1\n')

        assert 'no table rows' in found.problems

    def test_rows_that_do_not_reconcile_are_reported(self):
        page = GOODS_PAGE.replace('Subtotal 40,640.00', 'Subtotal 99,999.00')
        found = fields.read(page)

        assert any('page says subtotal' in note for note in found.problems)

    def test_a_clean_page_has_nothing_to_report(self):
        assert fields.read(GOODS_PAGE).problems == []


AMBIGUOUS_PAGE = """COMMERCIAL INVOICE
FROM
Hanil Cosmetic Vessels Co., Ltd.
Invoice no. HCV-2026-3216
77 Namdong-daero, Namdong-gu
Incheon 21632
Republic of Korea
Business reg.: 131-86-40925
BILL TO Invoice no. HCV-2026-3216
Moty Cosmeticos Ltda. Date of issue 05/12/2026
Louveira, SP 13290-000 Payment due 07/01/2026
Brazil Reference PO-41066
Part no. Description of goods HS code Qty Unit price Amount USD
JA-050D Acrylic jar, 50 g, double wall 3923.10 9,000 0.812 7,308.00
Subtotal 7,308.00
Total USD 7,308.00"""

REVISION_PAGE = GOODS_PAGE.replace('NCL-2026-3140', 'NCL-2026-3140-R1')


class TestAnAmbiguousDate:
    def test_a_page_where_every_number_is_under_thirteen(self):
        """`05/12/2026` could be 5 December or 12 May. One date cannot say."""
        found = fields.read(AMBIGUOUS_PAGE)

        assert found.date_order == 'month_first'

    def test_the_terms_break_the_tie(self):
        """Read day first, the due date would fall before the issue date."""
        found = fields.read(AMBIGUOUS_PAGE)

        assert found.issue_date == date(2026, 5, 12)
        assert found.due_date == date(2026, 7, 1)
        assert found.due_date > found.issue_date

    def test_an_unambiguous_date_still_wins_over_the_tie_breaker(self):
        page = AMBIGUOUS_PAGE.replace('05/12/2026', '23/04/2026')
        found = fields.read(page)

        assert found.date_order == 'day_first'
        assert found.issue_date == date(2026, 4, 23)


class TestARevision:
    def test_a_number_ending_r1_says_what_it_revises(self):
        found = fields.read(REVISION_PAGE)

        assert found.number == 'NCL-2026-3140-R1'
        assert found.revises == 'NCL-2026-3140'

    def test_an_ordinary_number_revises_nothing(self):
        assert fields.read(GOODS_PAGE).revises == ''


class TestItKnowsNothingOfTheGenerator:
    def test_the_reader_imports_no_generator_module(self):
        import inspect

        source = inspect.getsource(fields)
        for forbidden in ('business', 'simulation', 'drawing', 'issuers',
                          'layouts', 'catalogue', 'operation', 'builder',
                          'ledger'):
            assert f'import {forbidden}' not in source
            assert f'from {forbidden}' not in source
