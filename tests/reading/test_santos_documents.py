"""The Santos documents: local charges, storage and the duty statement,
and the closing rules the real run taught the reader.

Each prints its own title, and the reader files it under its own kind,
so the cost report can tell a terminal bill from a goods invoice.
"""

from decimal import Decimal

from reading import fields, intake

LOCAL = """LOCAL CHARGES
Invoice no. MRK-2026-7004
Invoice date 2026-05-04
Currency BRL
Description Qty Unit price Amount BRL
Terminal handling (capatazia), per container 1 3,700.00 3,700.00
B/L release 1 1,000.00 1,000.00
Total BRL 4,700.00
"""

STORAGE = LOCAL.replace('LOCAL CHARGES', 'STORAGE INVOICE')

SCANNED = """COMMERCIAL INVOICE
Invoice no. BDT-2026-7004
Total 15,693.90
All amounts in United States dollars.
"""


def test_local_charges_are_their_own_kind():
    assert fields.read(LOCAL).kind == 'local'


def test_storage_is_its_own_kind():
    assert fields.read(STORAGE).kind == 'storage'


def test_currency_comes_from_the_footer_when_the_label_is_lost():
    assert fields.read(SCANNED).currency == 'USD'


def test_currency_comes_from_the_total_label_when_the_footer_is_lost():
    text = SCANNED.replace('All amounts in United States dollars.', '')
    assert fields.read(text.replace('Total ', 'Total BRL ')).currency == 'BRL'


STATEMENT_WITHOUT_TITLE = """FROM
Santos Comissaria Aduaneira Ltda.
Statement no. SCA-2026-7002
Registered 04/05/2026
Currency BRL
DESCRIPTION BASE BRL RATE AMOUNT BRL
|| 8424.89.90 10.000,00 0,14 1.400,00
ll 3923.10.90 5.000,00 0,18 900,00
PIS-Importacao 8424.89.90 10.000,00 0,021 210,00
Total BRL 2.510,00
"""


def test_a_duty_statement_is_known_by_its_taxes_when_ocr_loses_the_title():
    assert fields.read(STATEMENT_WITHOUT_TITLE).kind == 'customs'


def test_the_import_duty_survives_ocr_reading_ii_as_bars():
    """II is the one tax that is a cost; read as || it would vanish from
    the landed cost without a word."""
    found = fields.read(STATEMENT_WITHOUT_TITLE)

    assert [line.description for line in found.lines[:2]] == \
        ['II 8424.89.90', 'II 3923.10.90']


GOODS = """FROM
Aravalli Labelworks Pvt. Ltd.
Invoice no. ARL-2026-7003
Date of issue 2026-05-04
PART NO. DESCRIPTION OF GOODS HS CODE QTY UNIT PRICE AMOUNT USD
LB-GL01 Adhesive label 4821.10 900,000 0.0207 18,630.00
Tooling and plate set-up 1 500.38 500.38
Subtotal 19,130.38
{discount}Total USD {total}
"""


def test_a_total_that_is_not_the_subtotal_less_the_discount_is_flagged():
    """OCR read a 9 as a 3 in the total only: the lines still close."""
    found = fields.read(GOODS.format(discount='', total='13,130.38'))

    assert any('total' in problem for problem in found.problems)


def test_a_total_that_is_the_subtotal_less_the_discount_is_clean():
    found = fields.read(GOODS.format(discount='Discount -130.38\n',
                                     total='19,000.00'))

    assert found.problems == []


def test_a_dash_ocr_hangs_on_a_number_is_dropped():
    number, _ = intake.reconcile_number('HCV-2026-7001—', 'HCV-2026-7001.pdf')
    assert number == 'HCV-2026-7001'


def test_lines_that_do_not_make_the_total_are_flagged_without_a_subtotal():
    """OCR lost the subtotal ("Suttotal") and read 6,448.00 as 448.00:
    the lines still add to 6,448.00, so the reading must not close."""
    page = GOODS.format(discount='', total='448.00').replace(
        'Subtotal 19,130.38\n', '')

    assert any('total' in problem for problem in fields.read(page).problems)


def test_a_reading_without_its_currency_does_not_close():
    lost = GOODS.format(discount='', total='19,130.38').replace(
        'Total USD', 'Total')
    good = lost + 'Currency USD\n'

    found, tries = intake.best_reading(iter([lost, good]), 'ARL-2026-7003.pdf')

    assert tries == 2 and found.currency == 'USD'


OCR_STATEMENT = """Statement no. SCA-2026-4154
Registered 04/05/2026
Currency BRL
FX rate {fx}
DESCRIPTION BASE BRL RATE AMOUNT BRL
ON 7010.90.22 ae 49.711,62 0,14 6.959,63
IPi 7010.90.22 . a 56.671,25 0,0975 5.525,45
PiS-importacao 7010.90.22 49.711,62 0,021 1.043,94
COFINS-Importacao 7010.90.22 49.711,62 0,0965 4.797,17
I! 3923.30.00 23.082,06 0,144 3.323,82
IP! 3923.30.00 26.405,88 0,15 3.960,88
PIS-Importacao 3923.30.00 23.082,06 0,021 484,72
COFINS-importacao 3923.30.00 ae 23.082,06 0,0965 2.227,42
AFRMM 12.381,58 0,08 990,53
Taxa Siscomex 1,00 214,50 214,50
Total BRL 29.527,54
"""


def test_each_tax_of_a_garbled_statement_is_named_by_its_place():
    """A duty statement lists II, IPI, PIS and COFINS for each NCM, in that
    order. OCR read II as "ON" and "I!"; the place still says what it is."""
    found = fields.read(OCR_STATEMENT.format(fx='5,3408'))

    assert [line.description for line in found.lines[:8]] == [
        'II 7010.90.22', 'IPI 7010.90.22', 'PIS-Importacao 7010.90.22',
        'COFINS-Importacao 7010.90.22', 'II 3923.30.00', 'IPI 3923.30.00',
        'PIS-Importacao 3923.30.00', 'COFINS-Importacao 3923.30.00']


def test_the_rate_is_read_with_its_four_decimals():
    assert fields.read(OCR_STATEMENT.format(fx='5,3408')).fx_rate == \
        Decimal('5.3408')
    assert fields.read(OCR_STATEMENT.format(fx='5.3408')).fx_rate == \
        Decimal('5.3408')


def test_a_rate_that_lost_its_decimals_is_not_taken():
    """OCR read 5,3408 as 3408: costing at that rate multiplies the goods
    a thousandfold. The rate is left empty and the row says so."""
    found = fields.read(OCR_STATEMENT.format(fx='3408'))

    assert found.fx_rate is None
    assert any('FX rate' in problem for problem in found.problems)


def test_a_document_dated_after_it_arrived_is_flagged(tmp_path):
    """OCR read 19/06/2026 as 2028: a page cannot be issued after it
    reached the inbox."""
    from datetime import date
    from business import issuers as known
    from drawing import render
    from simulation import builder
    invoice = builder.invoice_for(known.ALL_ISSUERS[0], seed=3)
    invoice.issue_date = date(2028, 6, 19)
    pdf = render.build_invoice(tmp_path, invoice)
    store = intake.Store(tmp_path / 'data')

    outcome = store.take(pdf.read_bytes(), pdf.name, '2026-10-14T08:00:00-03:00')

    assert any('after it arrived' in p for p in outcome.problems)


STRIP = """FREIGHT INVOICE
Invoice no. DHI-2026-3245
ORIGIN DESTINATION EQUIPMENT VESSEL / FLIGHT GROSS WEIGHT KG VOLUME M3
{line}
"""


def test_the_strip_reads_a_shared_container():
    found = fields.read(STRIP.format(line='Cat Lai Santos LCL MV Hanjin Star 4100 25.98'))

    assert (found.origin, found.container) == ('Cat Lai', 'LCL')


def test_the_strip_reads_every_container_booked():
    found = fields.read(STRIP.format(
        line='Ningbo Santos 40HC + 20GP MV Santos Express 31000 95.2'))

    assert found.container == '40HC + 20GP'
    assert found.vessel == 'MV Santos Express'


def test_the_incoterm_is_read_off_a_goods_invoice():
    page = GOODS.format(discount='', total='19,130.38') + 'Incoterm CIF Busan\n'

    assert fields.read(page).incoterm == 'CIF Busan'
