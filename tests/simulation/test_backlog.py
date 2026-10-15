"""The real run: the business from 1 January to the run date.

It ships the way the reference says: a factory sends what is ready each
week; the cargo's room comes from whole cartons; a sea shipment goes FCL
or LCL, whichever costs less all in, and a late one flies. Each landed
shipment brings its Santos documents, in reais.
"""

import math
from datetime import date
from decimal import Decimal

import pytest

from simulation import freight
from simulation.operation import BACKLOG, Operation

OPENS = date(2026, 1, 1)
RUN_DATE = date(2026, 10, 14)


@pytest.fixture(scope='module')
def run():
    return Operation(OPENS, profile=BACKLOG, until=RUN_DATE).run()


def _on(run, shipment, kind, currency=None):
    """The documents of one kind on a shipment; a revision or a planted
    near duplicate is an extra copy, not another document."""
    return [i for i in run.invoices if i.shipment_id == shipment.identifier
            and i.kind == kind and (currency is None or i.currency == currency)
            and not i.revises and i.anomaly != 'near_duplicate']


class TestThePeriod:
    def test_nothing_is_dated_after_the_run_date(self, run):
        assert max(i.issue_date for i in run.invoices) <= RUN_DATE

    def test_it_starts_on_1_january(self, run):
        assert min(i.issue_date for i in run.invoices) >= OPENS
        assert min(i.issue_date for i in run.invoices).month == 1

    def test_no_shipment_lands_after_the_run_date(self, run):
        landed = [i for i in run.invoices if i.kind == 'customs']
        assert all(i.issue_date <= RUN_DATE for i in landed)


class TestTheCargo:
    def test_the_room_and_weight_are_whole_cartons(self, run):
        for dispatch_group in _by_shipment(run).values():
            shipment, dispatches = dispatch_group
            m3 = kg = Decimal(0)
            for dispatch in dispatches:
                for part, quantity in dispatch.lines:
                    cartons = math.ceil(quantity / part.carton.units)
                    m3 += part.carton.m3 * cartons
                    kg += part.carton.kg * cartons
            assert shipment.volume_m3 == m3.quantize(Decimal('0.01'))
            assert shipment.weight_kg == kg.quantize(Decimal('0.01'))


def _by_shipment(run):
    found = {s.identifier: (s, []) for s in run.shipments}
    for dispatch in run.dispatches:
        if dispatch.shipment_id in found:
            found[dispatch.shipment_id][1].append(dispatch)
    return found


class TestTheMode:
    def test_every_load_is_fcl_lcl_or_air(self, run):
        loads = {s.load for s in run.shipments}
        assert loads == {'FCL', 'LCL', 'air'}

    def test_a_sea_shipment_takes_the_cheaper_load(self, run):
        for shipment in run.shipments:
            if shipment.mode != 'ocean':
                continue
            fcl, lcl = freight.all_in_usd(shipment.volume_m3,
                                          shipment.weight_kg, shipment.fx,
                                          shipment.cif_usd)
            chosen = fcl if shipment.load == 'FCL' else lcl
            assert chosen <= min(fcl, lcl), shipment.identifier

    def test_lcl_and_air_go_with_the_forwarder(self, run):
        for shipment in run.shipments:
            if shipment.load in ('LCL', 'air'):
                assert shipment.carrier_code == 'DHI'


class TestTheFreightInvoices:
    def test_hcv_sells_cif_so_its_shipments_bring_no_freight_invoice(self, run):
        hcv = [s for s in run.shipments if s.factory_code == 'HCV']
        assert hcv
        for shipment in hcv:
            assert not _on(run, shipment, 'freight', 'USD')

    def test_every_other_shipment_brings_one_freight_invoice(self, run):
        for shipment in run.shipments:
            if shipment.factory_code != 'HCV' and shipment.departed_on >= OPENS:
                bills = {i.number for i in _on(run, shipment, 'freight', 'USD')}
                assert len(bills) == 1, shipment.identifier

    def test_fcl_freight_is_charged_per_container_at_the_rate_card(self, run):
        for shipment in run.shipments:
            if shipment.load != 'FCL' or shipment.factory_code == 'HCV':
                continue
            bill = _on(run, shipment, 'freight', 'USD')[0]
            main = bill.lines[0]
            assert main.unit == 'container'
            assert main.unit_price in freight.FCL_RATE.values()


class TestTheSantosDocuments:
    def test_a_landed_shipment_brings_all_its_santos_documents(self, run):
        landed = [s for s in run.shipments
                  if OPENS <= s.arrived_on <= RUN_DATE]
        assert landed
        for shipment in landed:
            for kind, currency in (('local', 'BRL'), ('storage', 'BRL'),
                                   ('customs', 'BRL'), ('broker', 'BRL'),
                                   ('freight', 'BRL')):
                assert _on(run, shipment, kind, currency), \
                    (shipment.identifier, kind)

    def test_the_truck_is_tlv_and_kng_only_rents_the_warehouse(self, run):
        trucks = [i for i in run.invoices
                  if i.kind == 'freight' and i.currency == 'BRL']
        assert {i.issuer_code for i in trucks} == {'TLV'}
        kng = [i for i in run.invoices if i.issuer_code == 'KNG']
        assert all('rent' in i.lines[0].description.lower() for i in kng)


class TestTheVolume:
    def test_several_hundred_mails_worth_of_documents(self, run):
        """At most ten PDFs a mail, a few hundred mails: a real backlog."""
        assert 800 <= len(run.invoices) <= 3000


class TestWhatFlies:
    def test_only_a_small_load_flies(self, run):
        """A late load flies only when it is small: a container's worth of
        bottles by air costs more than the bottles."""
        from simulation.operation import AIR_MAX_CHARGEABLE_KG
        for shipment in run.shipments:
            if shipment.load == 'air':
                chargeable = max(shipment.weight_kg,
                                 shipment.volume_m3 * freight.AIR_KG_PER_M3)
                assert chargeable <= AIR_MAX_CHARGEABLE_KG


class TestTheRunDateOnlyCutsTheYear:
    def test_a_later_run_date_keeps_every_earlier_document(self):
        """Live carries on from the backlog: the documents up to the old
        run date must be the very same, number for number, total for
        total, whatever the new run date is."""
        early = Operation(OPENS, profile=BACKLOG, until=date(2026, 3, 31)).run()
        later = Operation(OPENS, profile=BACKLOG, until=date(2026, 4, 30)).run()
        before = [(i.number, i.grand_total) for i in later.invoices
                  if i.issue_date <= date(2026, 3, 31)]

        assert sorted(before) == sorted((i.number, i.grand_total)
                                        for i in early.invoices)

