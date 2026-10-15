"""What a cost report needs off the page, read back.

The page already prints the part number, the HS code, the weight, the
container and the route. A cost per part and a freight cost per kilo are
impossible without them, so the reader keeps them.
"""

from decimal import Decimal

import pytest

from business import issuers
from drawing import render
from reading import intake
from simulation import builder

WHEN = '2026-05-01T09:00:00+00:00'


def _stored(tmp_path, code, seed=11):
    issuer = issuers.by_code(code)
    invoice = builder.invoice_for(issuer, seed=seed)
    path = render.build_invoice(tmp_path, invoice, issuer, name='x.pdf')
    store = intake.Store(tmp_path / 'data')
    store.take(path.read_bytes(), 'x.pdf', WHEN)
    return invoice, store


@pytest.mark.parametrize('code', ['NCL', 'GZV', 'HCV', 'ARL'])
def test_each_goods_line_keeps_its_part_and_hs_code(tmp_path, code):
    invoice, store = _stored(tmp_path, code)
    coded = [l for l in invoice.lines if l.code]

    read = [l for l in store.lines if l['code']]
    assert [l['code'] for l in read] == [l.code for l in coded]
    assert [l['hs_code'] for l in read] == [l.hs_code for l in coded]


def test_a_service_line_has_no_part(tmp_path):
    invoice, store = _stored(tmp_path, 'NCL', seed=3)
    services = [l for l in invoice.lines if not l.code]

    assert len([l for l in store.lines if not l['code']]) == len(services)


@pytest.mark.parametrize('code', ['MRK', 'CSM', 'DHI', 'KNG'])
def test_a_freight_invoice_keeps_its_route_and_weight(tmp_path, code):
    invoice, store = _stored(tmp_path, code)
    row = store.invoices[0]
    box = invoice.shipment

    assert row['origin'] == box['origin']
    assert row['destination'] == box['destination']
    assert row['container'] == box['container']
    assert Decimal(row['gross_weight_kg']) == Decimal(box['weight_kg'])
    assert row['vessel'] == box['vessel']


def test_the_main_freight_line_keeps_its_weight(tmp_path):
    invoice, store = _stored(tmp_path, 'MRK')

    assert Decimal(store.lines[0]['weight_kg']) == invoice.lines[0].weight_kg


@pytest.mark.parametrize('code, kind', [('NCL', 'goods'), ('MRK', 'freight')])
def test_the_kind_and_currency_are_read(tmp_path, code, kind):
    _, store = _stored(tmp_path, code)

    assert store.invoices[0]['kind'] == kind
    assert store.invoices[0]['currency'] == 'USD'
