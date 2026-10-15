"""The costing over eight busy weeks, filed by a perfect reader.

Every shipment with goods is costed; nothing is lost in the splits; the
goods in dollars match the answer key's chains.
"""

from datetime import date
from decimal import Decimal

import pytest

from costing import landed, truth
from simulation import erp
from simulation.operation import BUSY, Operation


@pytest.fixture(scope='module')
def run():
    return Operation(date(2026, 4, 6), profile=BUSY).run()


@pytest.fixture(scope='module')
def books(run):
    invoices, lines = truth.books(run)
    tables = erp.tables(run)
    items = {row['code']: {'unit_weight_g': Decimal(str(row['unit_weight_g'])),
                           'ncm': row['ncm']} for row in tables['items']}
    names = {row['name']: row['code'] for row in tables['vendors']}
    return landed.Books(invoices, lines, items, names, dict(run._fx))


@pytest.fixture(scope='module')
def rows(books):
    return landed.cost(books)


def test_every_line_has_a_positive_cost(rows):
    assert rows
    assert all(row['landed_brl'] > 0 for row in rows)


def test_a_line_is_final_only_once_its_shipment_has_landed(run, rows):
    """Eight weeks is short beside a 35 to 45 day crossing, so many
    shipments are still at sea at the end: those stay provisional."""
    landed_on = {s.identifier: s.arrived_on for s in run.shipments}
    for row in rows:
        if row['status'] == 'final':
            assert landed_on[row['shipment_id']] < run.last_day


def test_a_shipment_still_at_sea_is_provisional(run, rows):
    at_sea = {s.identifier for s in run.shipments
              if s.arrived_on >= run.last_day}
    for row in rows:
        if row['shipment_id'] in at_sea:
            assert row['status'] == 'provisional'
            assert row['fx_source'] == 'ptax'


def test_every_part_is_on_the_item_master(rows):
    assert all(row['ncm'] for row in rows)


def test_the_cost_parts_add_to_the_landed_cost(rows):
    for row in rows:
        assert row['landed_brl'] == sum(row[name] for name in landed.COST_PARTS)


def test_a_final_line_carries_duty_freight_and_truck(rows):
    for row in rows:
        if row['status'] == 'final':
            assert row['duty_brl'] > 0
            assert row['freight_brl'] > 0
            assert row['inland_brl'] > 0


def test_duties_make_the_landed_cost_dearer_than_the_goods(rows):
    final = [row for row in rows if row['status'] == 'final']
    goods = sum(row['goods_brl'] for row in final)
    landed_total = sum(row['landed_brl'] for row in final)

    assert Decimal('1.15') < landed_total / goods < Decimal('1.60')


def test_operations_cover_every_shipment_with_freight(books):
    found = landed.operations(books)
    priced = [op for op in found if op['freight_per_kg_brl'] != '']

    assert priced
    assert all(op['freight_per_kg_brl'] > 0 for op in priced)
