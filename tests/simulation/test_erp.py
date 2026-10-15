"""The records a payables desk holds besides the invoices, and the labels.

Three-way match compares the invoice with the order and the goods receipt.
A model needs those records too, so a run exports them as plain CSV files,
with one label file a model can read.
"""

import csv
from datetime import date

import pytest

from simulation import anomalies, erp, labels
from simulation.operation import BUSY, Operation

START = date(2026, 4, 6)


@pytest.fixture(scope='module')
def busy():
    return Operation(START, profile=BUSY).run()


@pytest.fixture(scope='module')
def tables(busy):
    return erp.tables(busy)


class TestTheTables:
    def test_every_table_is_there(self, tables):
        assert set(tables) == set(erp.TABLES)

    def test_every_invoice_issuer_is_a_vendor(self, busy, tables):
        vendors = {v['code'] for v in tables['vendors']}

        assert {i.issuer_code for i in busy.invoices} <= vendors

    def test_every_quoted_order_exists(self, busy, tables):
        orders = {o['number'] for o in tables['purchase_orders']}

        assert {i.order_number for i in busy.invoices if i.order_number} <= orders

    def test_every_shipment_on_an_invoice_exists(self, busy, tables):
        shipments = {s['identifier'] for s in tables['shipments']}

        assert {i.shipment_id for i in busy.invoices if i.shipment_id} <= shipments

    def test_order_lines_join_to_orders(self, tables):
        orders = {o['number'] for o in tables['purchase_orders']}

        assert {l['order_number'] for l in tables['po_lines']} <= orders

    def test_receipts_join_to_order_lines(self, tables):
        lines = {(l['order_number'], l['code']) for l in tables['po_lines']}

        assert {(r['order_number'], r['code']) for r in tables['receipts']} <= lines

    def test_the_vendor_master_holds_the_usual_account(self, tables):
        assert all('bank_account' in v for v in tables['vendors'])

    def test_the_approval_limit_is_on_file(self, tables):
        limits = {p['limit'] for p in tables['approval_policy']}

        assert str(anomalies.APPROVAL_LIMIT) in limits

    def test_the_rate_card_lists_lanes_and_fees(self, tables):
        kinds = {r['kind'] for r in tables['rate_card']}

        assert {'freight', 'fixed_fee', 'surcharge'} <= kinds

    def test_no_answer_leaks_into_the_records(self, tables):
        """The tables are what a desk would have; the answers are elsewhere."""
        for rows in tables.values():
            for row in rows:
                assert 'anomaly' not in row and 'lookalike_of' not in row

    def test_export_writes_one_csv_per_table(self, busy, tmp_path):
        erp.export(busy, tmp_path)

        for name in erp.TABLES:
            with open(tmp_path / f'{name}.csv', newline='', encoding='utf-8') as f:
                assert next(csv.reader(f))


class TestTheLabels:
    def test_one_row_per_invoice(self, busy):
        assert len(labels.rows(busy)) == len(busy.invoices)

    def test_labels_match_the_invoices(self, busy):
        by_number = {}
        for row in labels.rows(busy):
            by_number.setdefault(row['number'], []).append(row)
        for invoice in busy.invoices:
            assert any(r['anomaly'] == invoice.anomaly
                       and r['lookalike_of'] == invoice.lookalike_of
                       for r in by_number[invoice.number])

    def test_only_anomalies_have_a_discovery_delay(self, busy):
        for row in labels.rows(busy):
            assert bool(row['found_after_days']) == bool(row['anomaly'])

    def test_a_vendor_without_order_is_found_later_than_a_duplicate(self):
        assert (min(labels.DELAYS['unmatched_vendor'])
                > max(labels.DELAYS['near_duplicate']))

    def test_the_delay_is_stable(self, busy):
        assert labels.rows(busy) == labels.rows(busy)

    def test_write_makes_a_csv(self, busy, tmp_path):
        path = labels.write(busy, tmp_path)

        with open(path, newline='', encoding='utf-8') as f:
            assert len(list(csv.DictReader(f))) == len(busy.invoices)


class TestAsOfADay:
    """A live run must never show a record dated after its own day."""

    DAY = date(2026, 5, 4)

    def test_no_table_carries_a_later_date(self, busy):
        for name, rows in erp.tables(busy, as_of=self.DAY).items():
            for row in rows:
                for key, value in row.items():
                    if isinstance(value, date):
                        assert value <= self.DAY, (name, key, value)

    def test_a_shipment_still_at_sea_has_no_arrival_yet(self, busy):
        at_sea = [s for s in erp.tables(busy, as_of=self.DAY)['shipments']
                  if s['departed_on'] <= self.DAY and s['arrived_on'] == '']

        assert at_sea

    def test_the_full_export_is_unchanged_without_a_day(self, busy):
        assert len(erp.tables(busy)['receipts']) == len(busy.receipts)
