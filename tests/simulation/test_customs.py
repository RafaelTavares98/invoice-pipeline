"""The Brazilian side of an import, checked by hand.

A landed cost in Louveira without the import duties, the broker and the
truck is not believable. These tests recompute a declaration from its own
inputs and the published rates, and hold the quiet run unchanged.
"""

from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from business import catalogue, issuers, tariffs
from simulation import customs, fx
from simulation.operation import BUSY, Operation

START = date(2026, 4, 6)


@pytest.fixture(scope='module')
def busy():
    return Operation(START, profile=BUSY).run()


def statements(run):
    return [i for i in run.invoices if i.kind == 'customs' and not i.revises]


class TestTheRates:
    def test_every_part_has_an_ncm_with_a_rate_and_a_source(self):
        for part in catalogue.CATALOGUE:
            rate = tariffs.rate_on(tariffs.ncm_for(part.hs_code), START)
            assert rate.source
            assert Decimal('0') <= rate.ii <= Decimal('0.35')

    def test_caps_pay_eighteen_percent_duty(self):
        assert tariffs.rate_on('3923.50.00', START).ii == Decimal('0.18')

    def test_a_published_change_applies_from_its_date(self):
        change = tariffs.Rate('7612.10.00', Decimal('0.112'), Decimal('0.10'),
                              Decimal('0.0965'), date(2026, 5, 1), 'test')
        assert tariffs.rate_on('7612.10.00', date(2026, 4, 30), [change]).ii == Decimal('0.16')
        assert tariffs.rate_on('7612.10.00', date(2026, 5, 1), [change]).ii == Decimal('0.112')


class TestTheRate:
    def test_the_series_is_the_same_every_time(self):
        assert fx.ptax(START) == fx.ptax(START)

    def test_it_stays_believable(self):
        rates = fx.series(date(2026, 12, 31)).values()
        assert all(Decimal('4.0') < rate < Decimal('7.0') for rate in rates)

    def test_a_weekend_holds_fridays_rate(self):
        assert fx.ptax(date(2026, 4, 11)) == fx.ptax(date(2026, 4, 10))


class TestTheDocuments:
    def test_every_landed_shipment_brings_three_documents_in_reais(self, busy):
        landed = {s.identifier for s in busy.shipments
                  if START <= s.arrived_on < busy.last_day}
        kinds = Counter((i.kind, i.issuer_code) for i in busy.invoices
                        if i.currency == 'BRL' and not i.revises
                        and i.shipment_id in landed)

        assert len(statements(busy)) >= len(landed) - 2
        assert kinds[('broker', 'SCA')] >= len(landed) - 2
        assert kinds[('freight', 'TLV')] >= len(landed) - 2

    def test_no_dollar_truck_is_left(self, busy):
        """The road leg is the Brazilian trucker's now; KNG keeps only its
        monthly warehouse rent."""
        assert not any(i.issuer_code == 'KNG'
                       and any(l.description.startswith('Road haulage')
                               for l in i.lines)
                       for i in busy.invoices)

    def test_afrmm_only_on_ocean(self, busy):
        mode = {s.identifier: s.mode for s in busy.shipments}
        for invoice in statements(busy):
            has = any(l.description == 'AFRMM' for l in invoice.lines)
            assert has == (mode[invoice.shipment_id] == 'ocean')

    def test_icms_is_charged_inside_its_own_base(self, busy):
        for invoice in statements(busy):
            icms = next(l for l in invoice.lines if l.description == 'ICMS SP')
            others = sum(l.net for l in invoice.lines if l is not icms)
            value = Decimal(dict(invoice.facts)['Customs value']
                            .replace('.', '').replace(',', '.'))
            expected = ((others + value) / (1 - tariffs.ICMS)).quantize(Decimal('0.01'))
            assert abs(icms.quantity - expected) <= Decimal('0.02')

    def test_each_duty_uses_the_rate_in_force(self, busy):
        for invoice in statements(busy):
            for line in invoice.lines:
                if line.description.startswith('II '):
                    ncm = line.description[3:]
                    rate = tariffs.rate_on(ncm, invoice.issue_date,
                                           busy.tariff_changes)
                    if not invoice.anomaly:
                        assert line.unit_price == rate.ii

    def test_the_statement_names_its_rate_and_value(self, busy):
        facts = dict(statements(busy)[0].facts)

        assert {'DUIMP', 'FX rate', 'Customs value'} <= set(facts)


class TestByHand:
    def test_a_small_declaration_recomputed(self):
        """US$ 1,000 of caps and US$ 200 of ocean freight at R$ 5.00."""
        lines, value = customs.statement_lines(
            {'3923.50.00': Decimal('1000')}, Decimal('200'), True,
            Decimal('5.00'), START)
        by = {l.description: l.net for l in lines}

        assert value == Decimal('6015.00')          # (1000 + 200 + 3) x 5
        assert by['II 3923.50.00'] == Decimal('1082.70')
        # 354.885 rounds half to even, as every line of every invoice does.
        assert by['IPI 3923.50.00'] == Decimal('354.88')
        assert by['PIS-Importacao 3923.50.00'] == Decimal('126.32')
        assert by['COFINS-Importacao 3923.50.00'] == Decimal('580.45')
        assert by['AFRMM'] == Decimal('80.00')
        assert by['Taxa Siscomex'] == Decimal('214.50')


class TestNothingElseMoves:
    def test_the_quiet_run_has_no_reais(self):
        run = Operation(START).run()

        assert len(run.invoices) == 106
        assert all(i.currency == 'USD' for i in run.invoices)

    def test_the_ten_issuers_stay_ten(self):
        assert len(issuers.ALL_ISSUERS) == 10
