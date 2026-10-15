"""Anomalies: errors a model should learn to catch later.

The rates come from the sources in docs/reference.md: about 1.5% of
payments duplicate or erroneous (APQC), and 5 to 10% of freight invoices
carrying an error (Tompkins Ventures). Each anomaly is written into the
answer key, so a model is scored against facts, not opinions.
"""

from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from simulation import anomalies, ledger
from simulation.operation import BUSY, Operation

START = date(2026, 4, 6)


@pytest.fixture(scope='module')
def busy():
    return Operation(START, profile=BUSY).run()


def kinds(run):
    return Counter(i.anomaly for i in run.invoices if i.anomaly)


class TestRates:
    def test_most_kinds_appear_in_eight_weeks(self, busy):
        """The rarest need a year; test_lookalikes.py checks that."""
        assert set(kinds(busy)) <= set(anomalies.KINDS)
        assert len(kinds(busy)) >= 5

    def test_freight_errors_sit_near_the_audited_rate(self, busy):
        freight = [i for i in busy.invoices if i.kind == 'freight']
        share = sum(i.anomaly == 'freight_overbill' for i in freight) / len(freight)

        assert 0.04 <= share <= 0.11

    def test_goods_anomalies_stay_rare(self, busy):
        goods = [i for i in busy.invoices if i.kind == 'goods']
        share = sum(bool(i.anomaly) for i in goods) / len(goods)

        assert share <= 0.06


class TestTheCustomsStage:
    """Two errors live on the import declaration and the broker's bill,
    and neither can happen anywhere else on the page.

    A duty charged at a rate the NCM does not carry, and a broker fee
    above the contract. Both are ordinary process errors: a tariff table
    that was not refreshed, a fee somebody keyed by hand.
    """

    def test_both_are_on_the_list_of_kinds(self):
        assert 'duty_rate_wrong' in anomalies.KINDS
        assert 'broker_fee_over' in anomalies.KINDS

    def test_a_wrong_duty_rate_is_only_on_a_declaration(self):
        """A factory's invoice carries no duty rate at all. At 3% of
        statements, eight weeks of Friday sailings may hold none, so a
        year is read."""
        from simulation.operation import YEAR
        year = Operation(START, profile=YEAR).run()
        wrong = [i for i in year.invoices if i.anomaly == 'duty_rate_wrong']

        assert wrong
        for invoice in wrong:
            assert invoice.kind == 'customs'

    def test_a_fee_over_contract_is_only_on_a_broker_bill(self, busy):
        over = [i for i in busy.invoices if i.anomaly == 'broker_fee_over']

        assert over
        for invoice in over:
            assert invoice.kind == 'broker'

    def test_a_wrong_duty_rate_differs_from_the_published_one(self):
        from business import tariffs
        from simulation.pricing import seeded

        line = anomalies.wrong_duty_rate(
            seeded(5), 'II 3923.30.00', Decimal('10000.00'),
            tariffs.rate_on('3923.30.00', START).ii)

        assert line != tariffs.rate_on('3923.30.00', START).ii

    def test_a_wrong_rate_stays_within_reach_of_the_real_one(self):
        """A rate ten times over is a typing slip anybody sees. The ones
        worth catching are a few points out: the wrong line of the
        table, or last year's."""
        from business import tariffs
        from simulation.pricing import seeded

        real = tariffs.rate_on('3923.30.00', START).ii
        for seed in range(20):
            wrong = anomalies.wrong_duty_rate(
                seeded(seed), 'II 3923.30.00', Decimal('10000.00'), real)

            assert abs(wrong - real) <= Decimal('0.10')
            assert wrong >= 0

    def test_a_broker_fee_over_contract_is_above_the_card(self):
        from simulation import customs
        from simulation.pricing import seeded

        name = 'Customs clearance fee'
        charged = anomalies.broker_fee_over(seeded(3), customs.FEES[name])

        assert charged > customs.FEES[name]

    def test_a_broker_fee_over_contract_is_not_absurd(self):
        """A fee at ten times the contract is caught by the first person
        to look. One at a third over is the one that gets paid."""
        from simulation import customs
        from simulation.pricing import seeded

        name = 'Customs clearance fee'
        for seed in range(20):
            charged = anomalies.broker_fee_over(seeded(seed),
                                                customs.FEES[name])

            assert charged <= customs.FEES[name] * 2


class TestWhatEachOneDoes:
    def test_a_price_drift_bills_above_the_agreed_price(self, busy):
        drifted = [i for i in busy.invoices if i.anomaly == 'price_drift']
        order = {o.number: o for o in busy.orders}
        for invoice in drifted:
            agreed = {l.code: l.agreed_price
                      for l in order[invoice.order_number].lines}
            assert any(l.code in agreed and l.unit_price > agreed[l.code]
                       for l in invoice.lines)

    def test_a_round_total_ends_in_thousands(self, busy):
        for invoice in busy.invoices:
            if invoice.anomaly == 'round_total':
                assert invoice.grand_total % 1000 == 0

    def test_a_near_duplicate_repeats_another_invoice(self, busy):
        """Same issuer and amount, new number: the hash cannot see it."""
        originals = {(i.issuer_code, i.grand_total)
                     for i in busy.invoices if i.anomaly != 'near_duplicate'}
        for invoice in busy.invoices:
            if invoice.anomaly == 'near_duplicate':
                assert (invoice.issuer_code, invoice.grand_total) in originals

    def test_an_overbilled_freight_carries_an_extra_charge(self, busy):
        for invoice in busy.invoices:
            if invoice.anomaly == 'freight_overbill':
                assert any(l.description.startswith(anomalies.OVERBILL)
                           for l in invoice.lines)


class TestTheAnswerKey:
    def test_the_ledger_names_each_anomaly(self, busy):
        built = ledger.build(busy)
        named = Counter(e['anomaly'] for e in built['invoices'] if e['anomaly'])

        assert named == kinds(busy)


class TestNothingElseMoves:
    def test_the_quiet_run_is_unchanged(self):
        """Only the busy profile carries anomalies, and they draw from their
        own dice, so the run every other test pins stays as it was."""
        run = Operation(START).run()

        assert len(run.invoices) == 106
        assert not any(i.anomaly for i in run.invoices)
