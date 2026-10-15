"""The three Brazilian documents, read back like any other invoice.

They print in reais, with a comma for the decimal mark and the day first.
The duty statement also carries the FX rate and the customs value, and
each tax line names its NCM.
"""

from datetime import date
from decimal import Decimal

import pytest

from business import issuers
from drawing import render
from reading import intake
from simulation.operation import BUSY, Operation

WHEN = '2026-05-01T09:00:00-03:00'


@pytest.fixture(scope='module')
def busy():
    return Operation(date(2026, 4, 6), profile=BUSY).run()


def _read(tmp_path, invoice):
    issuer = issuers.by_code(invoice.issuer_code)
    path = render.build_invoice(tmp_path, invoice, issuer, name='b.pdf')
    store = intake.Store(tmp_path / 'data')
    store.take(path.read_bytes(), 'b.pdf', WHEN)
    return store


def _first(run, kind, issuer):
    return next(i for i in run.invoices
                if i.kind == kind and i.issuer_code == issuer and not i.revises
                and not i.anomaly)


@pytest.mark.parametrize('kind, issuer', [('customs', 'SCA'),
                                          ('broker', 'SCA'),
                                          ('freight', 'TLV')])
def test_the_total_kind_and_currency_come_back(tmp_path, busy, kind, issuer):
    invoice = _first(busy, kind, issuer)
    row = _read(tmp_path, invoice).invoices[0]

    assert Decimal(row['grand_total']) == invoice.grand_total
    assert row['kind'] == kind
    assert row['currency'] == 'BRL'
    assert row['invoice_number'] == invoice.number
    assert row['shipment_id'] == invoice.shipment_id


def test_the_statement_gives_its_rate_and_customs_value(tmp_path, busy):
    invoice = _first(busy, 'customs', 'SCA')
    row = _read(tmp_path, invoice).invoices[0]
    facts = dict(invoice.facts)

    assert Decimal(row['fx_rate']) == Decimal(facts['FX rate'].replace(',', '.'))
    assert Decimal(row['customs_value']) == Decimal(
        facts['Customs value'].replace('.', '').replace(',', '.'))


def test_each_tax_line_keeps_its_ncm_base_and_rate(tmp_path, busy):
    invoice = _first(busy, 'customs', 'SCA')
    lines = _read(tmp_path, invoice).lines

    assert [l['description'] for l in lines] == [l.description for l in invoice.lines]
    assert [Decimal(l['quantity']) for l in lines] == [l.quantity for l in invoice.lines]
    assert [Decimal(l['unit_price']) for l in lines] == [l.unit_price for l in invoice.lines]
