"""The landed cost, from what was read, checked to the cent.

One ocean shipment, written by hand: two parts on one goods invoice,
the ocean freight, the duty statement at R$ 5.00, the broker and the
truck. Every split can be done on paper.
"""

from datetime import date
from decimal import Decimal

import pytest

from costing import landed

D = Decimal


def doc(number, kind, issuer, currency, total, shipment='B/L MRK7000001',
        issued='2026-04-06', **extra):
    row = {'invoice_number': number, 'status': 'new', 'revises': '',
           'issuer': issuer, 'issue_date': issued, 'kind': kind,
           'currency': currency, 'grand_total': str(total),
           'shipment_id': shipment, 'order_number': extra.pop('order', ''),
           'sha256': number, 'fx_rate': '', 'customs_value': '',
           'container': '', 'origin': '', 'gross_weight_kg': '',
           'first_seen': f'{issued}T08:00:00-03:00',
           'registered_at': f'{issued}T08:01:00-03:00', 'problems': ''}
    row.update(extra)
    return row


def line(number, description, quantity, unit_price, net, code=''):
    return {'invoice_number': number, 'sha256': number,
            'description': description, 'quantity': str(quantity),
            'unit_price': str(unit_price), 'net': str(net), 'code': code,
            'hs_code': '', 'weight_kg': ''}


@pytest.fixture
def books():
    invoices = [
        doc('NCL-1', 'goods', 'Ningbo Caplink', 'USD', '1500.00', order='PO-1'),
        doc('MRK-1', 'freight', 'Marsk Line', 'USD', '300.00',
            container='40HC', origin='Ningbo', gross_weight_kg='1000'),
        doc('SCA-1', 'customs', 'Santos Comissaria', 'BRL', '0',
            issued='2026-05-10', fx_rate='5.00'),
        doc('SCA-2', 'broker', 'Santos Comissaria', 'BRL', '2000.00',
            issued='2026-05-10'),
        doc('TLV-1', 'freight', 'Transportes Louveira', 'BRL', '4000.00',
            issued='2026-05-10'),
        doc('MRK-2', 'local', 'Marsk Line', 'BRL', '1000.00',
            issued='2026-05-10'),
        doc('TVA-1', 'storage', 'Terminal Valongo', 'BRL', '600.00',
            issued='2026-05-10'),
    ]
    lines = [
        # 10,000 caps take 0.3 m3 and weigh 70 kg; 1,000 pumps take 0.7 m3
        # and weigh 30 kg. A container is charged by the room cargo takes,
        # so the volume decides, not the weight.
        line('NCL-1', 'CP-024F Screw cap', 10000, '0.05', '500.00', 'CP-024F'),
        line('NCL-1', 'PM-024G Lotion pump', 1000, '1.00', '1000.00', 'PM-024G'),
        line('MRK-1', 'Ocean freight Ningbo to Santos', 1, '300.00', '300.00'),
        line('SCA-1', 'II 3923.50.00', '2500.00', '0.18', '450.00'),
        line('SCA-1', 'IPI 3923.50.00', '2950.00', '0.05', '147.50'),
        line('SCA-1', 'II 8424.89.90', '5000.00', '0.14', '700.00'),
        line('SCA-1', 'AFRMM', '1500.00', '0.08', '120.00'),
        line('SCA-1', 'Taxa Siscomex', 1, '214.50', '214.50'),
        line('SCA-1', 'ICMS SP', '10000.00', '0.18', '1800.00'),
        line('SCA-2', 'Customs clearance fee', 1, '2000.00', '2000.00'),
        line('TLV-1', 'Road haulage Santos to Louveira, 40HC', 1, '4000.00', '4000.00'),
        line('MRK-2', 'Terminal handling (capatazia)', 1, '1000.00', '1000.00'),
        line('TVA-1', 'Armazenagem FCL, 1o periodo', 1, '600.00', '600.00'),
    ]
    items = {'CP-024F': {'unit_weight_g': D('7'), 'unit_m3': D('0.00003'),
                         'ncm': '3923.50.00'},
             'PM-024G': {'unit_weight_g': D('30'), 'unit_m3': D('0.0007'),
                         'ncm': '8424.89.90'}}
    issuers = {'Ningbo Caplink': 'NCL', 'Marsk Line': 'MRK',
               'Santos Comissaria': 'SCA', 'Transportes Louveira': 'TLV'}
    ptax = {date(2026, 4, 6): D('5.50')}
    return landed.Books(invoices, lines, items, issuers, ptax)


@pytest.fixture
def rows(books):
    return {row['code']: row for row in landed.cost(books)}


class TestTheSplits:
    def test_goods_at_the_declarations_rate(self, rows):
        assert rows['CP-024F']['goods_brl'] == D('2500.00')
        assert rows['PM-024G']['goods_brl'] == D('5000.00')
        assert rows['CP-024F']['fx_source'] == 'declaration'

    def test_freight_split_by_volume(self, rows):
        """R$ 1,500 of ocean freight; caps take 0.3 of 1.0 m3, though they
        weigh 70 of 100 kg."""
        assert rows['CP-024F']['freight_brl'] == D('450.00')
        assert rows['PM-024G']['freight_brl'] == D('1050.00')

    def test_local_charges_truck_broker_and_afrmm_follow_the_volume(self, rows):
        assert rows['CP-024F']['local_brl'] == D('300.00')
        assert rows['CP-024F']['inland_brl'] == D('1200.00')
        assert rows['CP-024F']['broker_brl'] == D('600.00')
        assert rows['CP-024F']['afrmm_brl'] == D('36.00')

    def test_storage_split_by_value(self, rows):
        """R$ 600 of storage; the caps are 2,500 of 7,500 reais of goods."""
        assert rows['CP-024F']['storage_brl'] == D('200.00')
        assert rows['PM-024G']['storage_brl'] == D('400.00')

    def test_duty_goes_to_the_parts_of_its_ncm(self, rows):
        assert rows['CP-024F']['duty_brl'] == D('450.00')
        assert rows['PM-024G']['duty_brl'] == D('700.00')

    def test_siscomex_split_by_value(self, rows):
        assert rows['CP-024F']['siscomex_brl'] == D('71.50')

    def test_recoverable_taxes_are_kept_apart(self, rows):
        """IPI and ICMS are credits for a manufacturer, not cost."""
        assert rows['CP-024F']['credits_brl'] == D('147.50') + D('600.00')

    def test_the_landed_cost_and_the_cost_per_unit(self, rows):
        caps = rows['CP-024F']
        total = D('2500.00') + D('450.00') + D('300.00') + D('1200.00') \
            + D('200.00') + D('600.00') + D('450.00') + D('36.00') + D('71.50')
        assert caps['landed_brl'] == total
        assert caps['unit_landed_brl'] == (total / 10000).quantize(D('0.0001'))

    def test_nothing_is_lost_in_the_split(self, books):
        rows = landed.cost(books)
        assert sum(r['landed_brl'] for r in rows) == (
            D('7500.00') + D('1500.00') + D('4000.00') + D('2000.00')
            + D('1150.00') + D('120.00') + D('214.50') + D('1000.00')
            + D('600.00'))

    def test_air_freight_split_by_chargeable_weight(self, books):
        """By air, a part pays for its kilos or its volume weight, at 167
        kg a cubic metre, whichever is more: caps 70 kg against 50.1 kg of
        volume weight, pumps 30 kg against 116.9."""
        books.invoices[1]['container'] = 'LOOSE'
        caps = {r['code']: r for r in landed.cost(books)}['CP-024F']

        assert caps['freight_brl'] == (D('1500') * D('70') / (D('70') + D('116.9'))
                                       ).quantize(D('0.01'))

    def test_a_complete_shipment_is_final(self, rows):
        assert rows['CP-024F']['status'] == 'final'


class TestBeforeTheDeclaration:
    def test_without_it_the_cost_is_provisional_at_the_ptax(self, books):
        books.invoices = [r for r in books.invoices if r['kind'] != 'customs']
        caps = {r['code']: r for r in landed.cost(books)}['CP-024F']

        assert caps['status'] == 'provisional'
        assert caps['fx_source'] == 'ptax'
        assert caps['goods_brl'] == D('2750.00')
        assert caps['duty_brl'] == D('0.00')


class TestCorrections:
    def test_a_superseded_document_is_not_costed(self, books):
        books.invoices[0]['status'] = 'superseded'

        assert landed.cost(books) == []

    def test_a_credit_note_lowers_the_cost(self, books):
        books.invoices.append(doc('NCL-CN-1', 'credit', 'Ningbo Caplink', 'USD',
                                  '-50.00', order='PO-1', revises='NCL-1'))
        books.lines.append(line('NCL-CN-1', 'Credit, rejected batch: CP-024F',
                                -1000, '0.05', '-50.00', 'CP-024F'))
        caps = {r['code']: r for r in landed.cost(books)}['CP-024F']

        assert caps['goods_brl'] == D('2250.00')
        assert caps['quantity'] == D('9000')


class TestTheOperations:
    def test_one_row_per_shipment_with_freight_per_kg(self, books):
        found = landed.operations(books)

        assert len(found) == 1
        assert found[0]['carrier'] == 'MRK'
        assert found[0]['mode'] == 'FCL'
        assert found[0]['freight_per_kg_brl'] == D('1.5000')

    def test_the_mode_is_fcl_lcl_air_or_cif(self, books):
        freight = books.invoices[1]
        modes = {}
        for container in ('LCL', 'LOOSE'):
            freight['container'] = container
            modes[container] = landed.operations(books)[0]['mode']
        books.invoices = [d for d in books.invoices
                          if not (d['kind'] == 'freight'
                                  and d['currency'] == 'USD')]
        modes['none'] = landed.operations(books)[0]['mode']

        assert modes == {'LCL': 'LCL', 'LOOSE': 'air', 'none': 'CIF'}

    def test_the_month_is_the_goods_month(self, books):
        """The close the cost belongs to is the month the goods were
        billed, not the month the truck arrived."""
        assert landed.operations(books)[0]['month'] == '2026-04'


class TestTheDockReceipt:
    """A goods invoice need not print its B/L. The dock's receipt ties
    the order and the part to the shipment they came on, as a cost desk
    ties them, so the goods still meet their freight."""

    def test_goods_without_a_bl_are_tied_by_the_receipt(self, books):
        books.invoices[0]['shipment_id'] = ''
        books.receipts = [
            {'order_number': 'PO-1', 'code': 'CP-024F',
             'shipment_id': 'B/L MRK7000001', 'quantity': '10000'},
            {'order_number': 'PO-1', 'code': 'PM-024G',
             'shipment_id': 'B/L MRK7000001', 'quantity': '1000'}]

        rows = {r['code']: r for r in landed.cost(books)}

        assert rows['CP-024F']['freight_brl'] == D('450.00')
        assert rows['CP-024F']['status'] == 'final'

    def test_the_receipts_are_read_with_the_desks_records(self, tmp_path):
        import csv
        erp = tmp_path / 'erp'
        erp.mkdir()
        with open(erp / 'receipts.csv', 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, ['order_number', 'code', 'shipment_id',
                                        'quantity', 'received_on'])
            writer.writeheader()
            writer.writerow({'order_number': 'PO-1', 'code': 'CP-024F',
                             'shipment_id': 'B/L X', 'quantity': '5',
                             'received_on': '2026-05-01'})

        found = landed.load(tmp_path / 'data', erp)

        assert found.receipts[0]['shipment_id'] == 'B/L X'


class TestWhenACostIsFinal:
    def test_it_waits_for_the_local_charges_and_the_storage(self, books):
        books.invoices = [d for d in books.invoices if d['kind'] != 'storage']

        assert {r['status'] for r in landed.cost(books)} == {'provisional'}

    def test_a_cif_shipment_needs_no_freight_invoice(self, books):
        """The factory paid the freight inside a CIF price."""
        books.invoices = [d for d in books.invoices
                          if not (d['kind'] == 'freight' and d['currency'] == 'USD')]
        books.invoices[0]['incoterm'] = 'CIF Busan'

        assert {r['status'] for r in landed.cost(books)} == {'final'}


    def test_two_parts_of_one_order_go_to_the_shipment_that_left_that_day(self, books):
        """An order shipped in two equal parts has two equal receipts. The
        goods invoice is dated the day its box left, which the shipments
        record says."""
        books.invoices[0]['shipment_id'] = ''
        books.receipts = [
            {'order_number': 'PO-1', 'code': code, 'shipment_id': shipment,
             'quantity': quantity}
            for shipment in ('B/L OTHER0001', 'B/L MRK7000001')
            for code, quantity in (('CP-024F', '10000'), ('PM-024G', '1000'))]
        books.departures = {'B/L OTHER0001': date(2026, 3, 1),
                            'B/L MRK7000001': date(2026, 4, 6)}

        rows = {r['code']: r for r in landed.cost(books)}

        assert rows['CP-024F']['shipment_id'] == 'B/L MRK7000001'
