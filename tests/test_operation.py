"""The eight weeks have to behave like a business, not like a dice roll."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

import issuers
import lanes
from operation import WEEKS, Operation

START = date(2026, 4, 6)


@pytest.fixture(scope='module')
def run():
    return Operation(START, seed=4242).run()


class TestTheWindow:
    def test_every_invoice_falls_inside_the_eight_weeks(self, run):
        last = START + timedelta(weeks=WEEKS)

        for invoice in run.invoices:
            assert START <= invoice.issue_date < last

    def test_the_window_is_not_empty_in_any_week(self, run):
        weeks = {(invoice.issue_date - START).days // 7
                 for invoice in run.invoices}

        assert weeks == set(range(WEEKS))

    def test_orders_were_raised_before_the_window_too(self, run):
        assert any(order.raised_on < START for order in run.orders)


class TestTheChain:
    def test_every_goods_invoice_names_an_order_that_exists(self, run):
        numbers = {order.number for order in run.orders}

        for invoice in run.invoices:
            if invoice.kind == 'goods':
                assert invoice.order_number in numbers

    def test_every_goods_invoice_names_a_shipment_that_exists(self, run):
        identifiers = {ship.identifier for ship in run.shipments}

        for invoice in run.invoices:
            if invoice.kind == 'goods':
                assert invoice.shipment_id in identifiers

    def test_every_freight_invoice_names_a_shipment_that_exists(self, run):
        identifiers = {ship.identifier for ship in run.shipments}

        for invoice in run.invoices:
            if invoice.kind == 'freight':
                assert invoice.shipment_id in identifiers

    def test_a_shipment_carries_the_orders_it_says_it_does(self, run):
        numbers = {order.number for order in run.orders}

        for ship in run.shipments:
            assert ship.covers
            assert set(ship.covers) <= numbers


class TestTheGeography:
    def test_a_factory_sails_from_its_own_port(self, run):
        for ship in run.shipments:
            assert ship.origin == lanes.lane_for(ship.factory_code).port

    def test_an_ocean_shipment_uses_a_carrier_that_serves_the_lane(self, run):
        for ship in run.shipments:
            if ship.mode != 'ocean':
                continue
            assert ship.carrier_code in lanes.lane_for(
                ship.factory_code).ocean_carriers

    def test_only_one_carrier_flies(self, run):
        flown = {ship.carrier_code for ship in run.shipments
                 if ship.mode == 'air'}

        assert flown <= {lanes.AIR_CARRIER}

    def test_the_last_leg_is_always_the_same_carrier(self, run):
        inland = [i for i in run.invoices
                  if i.kind == 'freight'
                  and i.shipment.get('destination') == lanes.INLAND]

        assert inland
        assert {i.issuer_code for i in inland} == {lanes.INLAND_CARRIER}


class TestTheClock:
    def test_a_shipment_arrives_after_it_leaves(self, run):
        for ship in run.shipments:
            assert ship.transit_days > 0

    def test_air_beats_the_water(self, run):
        air = [s.transit_days for s in run.shipments if s.mode == 'air']
        ocean = [s.transit_days for s in run.shipments if s.mode == 'ocean']

        assert air, 'no air shipment was ever triggered'
        assert max(air) < min(ocean)

    def test_a_goods_invoice_is_dated_the_day_the_box_left(self, run):
        departures = {s.identifier: s.departed_on for s in run.shipments}
        originals = [i for i in run.invoices
                     if i.kind == 'goods' and not i.revises
                     and run.invoices.count(i) == 1]

        for invoice in originals[:40]:
            assert invoice.issue_date >= departures[invoice.shipment_id]


class TestTheMoney:
    def test_freight_is_a_sane_share_of_the_goods(self, run):
        import ledger

        chains = ledger.chains(run)
        goods = sum(Decimal(c['goods_total']) for c in chains)
        freight = sum(Decimal(c['freight_total']) for c in chains)

        assert Decimal('0.05') < freight / goods < Decimal('0.45')

    def test_a_goods_invoice_charges_the_price_the_order_agreed(self, run):
        by_number = {order.number: order for order in run.orders}

        for invoice in run.invoices:
            if invoice.kind != 'goods':
                continue
            order = by_number[invoice.order_number]
            agreed = {line.code: line.agreed_price for line in order.lines}
            for line in invoice.lines:
                if line.code:
                    assert line.unit_price == agreed[line.code]

    def test_no_invoice_is_free(self, run):
        for invoice in run.invoices:
            if invoice.kind == 'credit':
                assert invoice.grand_total < 0
            else:
                assert invoice.grand_total > 0


class TestTheIssuers:
    def test_every_issuer_bills_at_least_once(self, run):
        billed = {invoice.issuer_code for invoice in run.invoices}

        assert billed == {issuer.code for issuer in issuers.ALL_ISSUERS}

    def test_a_factory_only_ever_bills_for_goods(self, run):
        codes = {f.code for f in issuers.FACTORIES}

        for invoice in run.invoices:
            if invoice.issuer_code in codes:
                assert invoice.kind in ('goods', 'credit')

    def test_a_carrier_only_ever_bills_for_freight(self, run):
        codes = {c.code for c in issuers.CARRIERS}

        for invoice in run.invoices:
            if invoice.issuer_code in codes:
                assert invoice.kind == 'freight'


class TestItRepeats:
    def test_the_same_seed_gives_the_same_eight_weeks(self):
        first = Operation(START, seed=7).run()
        second = Operation(START, seed=7).run()

        assert [i.number for i in first.invoices] == \
               [i.number for i in second.invoices]

    def test_a_different_seed_gives_a_different_eight_weeks(self):
        first = Operation(START, seed=7).run()
        second = Operation(START, seed=8).run()

        assert [i.number for i in first.invoices] != \
               [i.number for i in second.invoices]
