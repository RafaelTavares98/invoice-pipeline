"""The three new anomalies, and an honest twin for every anomaly.

A model that flags whatever looks odd is useless to a payables desk: it
buries the real errors under false alarms. So every anomaly has a twin that
looks the same on the page and is legitimate, and the records of the
business are what tell the two apart.
"""

from collections import Counter
from datetime import date

import pytest

from business import issuers
from simulation import anomalies, lookalikes
from simulation.operation import DRIFT, YEAR, Operation

START = date(2026, 4, 6)


@pytest.fixture(scope='module')
def year():
    return Operation(START, profile=YEAR).run()


def named(run, field):
    return Counter(getattr(i, field) for i in run.invoices if getattr(i, field))


class TestTheCatalogue:
    def test_all_eight_anomalies_appear_in_a_year(self, year):
        assert set(named(year, 'anomaly')) == set(anomalies.KINDS)

    def test_every_anomaly_has_a_twin(self, year):
        assert set(named(year, 'lookalike_of')) == set(anomalies.KINDS)

    def test_no_invoice_is_both(self, year):
        assert not any(i.anomaly and i.lookalike_of for i in year.invoices)

    def test_twins_are_about_as_common_as_anomalies(self, year):
        planted = sum(named(year, 'anomaly').values())
        twins = sum(named(year, 'lookalike_of').values())

        assert 0.5 <= twins / planted <= 2.0


class TestUnmatchedVendor:
    def test_two_or_three_unmatched_vendors_a_year(self, year):
        unmatched = {i.issuer_code for i in year.invoices
                  if i.anomaly == 'unmatched_vendor'}

        assert 2 <= len(unmatched) <= 3

    def test_an_unmatched_vendor_bills_without_an_order(self, year):
        for invoice in year.invoices:
            if invoice.anomaly == 'unmatched_vendor':
                assert invoice.order_number == ''

    def test_an_unmatched_vendor_is_findable_by_its_code(self, year):
        code = next(i.issuer_code for i in year.invoices
                    if i.anomaly == 'unmatched_vendor')

        assert issuers.by_code(code).code == code

    def test_a_real_new_supplier_has_an_order(self, year):
        orders = {o.number for o in year.orders}
        twins = [i for i in year.invoices if i.lookalike_of == 'unmatched_vendor']

        assert twins
        assert all(i.order_number in orders for i in twins)

    def test_a_real_new_supplier_is_onboarded_first(self, year):
        onboarded = {v['code']: v['onboarded_on'] for v in year.joined}
        for invoice in year.invoices:
            if invoice.lookalike_of == 'unmatched_vendor':
                assert onboarded[invoice.issuer_code] <= invoice.issue_date

    def test_an_unmatched_vendor_is_onboarded_too(self, year):
        """It sits in the vendor master; the missing order is the error."""
        codes = {v['code'] for v in year.joined}
        unmatched = {i.issuer_code for i in year.invoices
                  if i.anomaly == 'unmatched_vendor'}

        assert unmatched <= codes


class TestAccountMismatch:
    def test_the_error_names_an_account_and_sender_not_on_file(self, year):
        for invoice in year.invoices:
            if invoice.anomaly == 'account_mismatch':
                issuer = issuers.by_code(invoice.issuer_code)
                assert invoice.pay_to and invoice.pay_to != issuer.bank_line
                assert invoice.sender == issuers.other_address(issuer)

    def test_the_error_has_no_change_on_file(self, year):
        changed = {(c['code'], c['new_value']) for c in year.vendor_changes}
        for invoice in year.invoices:
            if invoice.anomaly == 'account_mismatch':
                assert (invoice.issuer_code, invoice.pay_to) not in changed

    def test_an_honest_change_is_recorded_before_it_is_used(self, year):
        recorded = {(c['code'], c['new_value']): c['changed_on']
                    for c in year.vendor_changes}
        twins = [i for i in year.invoices if i.lookalike_of == 'account_mismatch']

        assert twins
        for invoice in twins:
            assert recorded[(invoice.issuer_code, invoice.pay_to)] <= invoice.issue_date
            issuer = issuers.by_code(invoice.issuer_code)
            assert invoice.sender == issuers.address_for(issuer)


class TestSplitBilling:
    def test_each_piece_sits_under_the_limit(self, year):
        for invoice in year.invoices:
            if invoice.anomaly == 'split_billing':
                assert invoice.grand_total < anomalies.APPROVAL_LIMIT

    def test_the_pieces_add_to_more_than_the_limit(self, year):
        pieces = {}
        for invoice in year.invoices:
            if invoice.anomaly == 'split_billing':
                pieces.setdefault((invoice.issuer_code, invoice.order_number),
                                  []).append(invoice.grand_total)
        assert pieces
        for amounts in pieces.values():
            assert len(amounts) >= 2
            assert sum(amounts) > anomalies.APPROVAL_LIMIT

    def test_partial_deliveries_are_the_twin(self, year):
        """Several invoices for one order, each tied to its own shipment."""
        twins = [i for i in year.invoices if i.lookalike_of == 'split_billing']

        assert twins
        for invoice in twins:
            assert invoice.shipment_id


class TestTheCustomsTwins:
    """Both customs errors have an honest version, and a model that
    cannot tell them apart will cry wolf at every import.

    A duty rate really does change: the table is published, it takes
    effect, and every declaration after it carries the new rate. A
    broker fee really does rise: the contract is amended first.
    """

    def test_a_rate_that_changed_is_backed_by_a_published_change(self, year):
        published = {(c.ncm, c.effective_on) for c in year.tariff_changes}
        twins = [i for i in year.invoices
                 if i.lookalike_of == 'duty_rate_wrong']

        assert twins
        for invoice in twins:
            assert any(ncm == line.description.split()[-1]
                       and effective <= invoice.issue_date
                       for ncm, effective in published
                       for line in invoice.lines
                       if line.description.startswith('II '))

    def test_a_higher_fee_is_backed_by_an_amended_contract(self, year):
        twins = [i for i in year.invoices
                 if i.lookalike_of == 'broker_fee_over']

        assert twins
        for invoice in twins:
            assert any(line.description.endswith('(amended)')
                       for line in invoice.lines)

    def test_neither_twin_is_also_an_anomaly(self, year):
        for invoice in year.invoices:
            if invoice.lookalike_of in ('duty_rate_wrong',
                                        'broker_fee_over'):
                assert not invoice.anomaly


class TestTheOtherTwins:
    def test_a_price_rise_is_backed_by_an_amendment(self, year):
        amended = {(a['order_number'], a['code']): a for a in year.amendments}
        twins = [i for i in year.invoices if i.lookalike_of == 'price_drift']

        assert twins
        for invoice in twins:
            assert any((invoice.order_number, l.code) in amended
                       and amended[(invoice.order_number, l.code)]['price'] == l.unit_price
                       and amended[(invoice.order_number, l.code)]['effective_on'] <= invoice.issue_date
                       for l in invoice.lines)

    def test_an_accepted_over_delivery_is_on_the_receipt(self, year):
        received = {(r['order_number'], r['code'], r['shipment_id']): r['quantity']
                    for r in year.receipts}
        for invoice in year.invoices:
            if invoice.lookalike_of != 'quantity_over':
                continue
            for line in invoice.lines:
                if line.code:
                    key = (invoice.order_number, line.code, invoice.shipment_id)
                    assert received[key] == line.quantity

    def test_a_round_fee_is_on_the_rate_card(self, year):
        card = {(f['issuer'], f['description']): f['amount']
                for f in lookalikes.FIXED_FEES}
        for invoice in year.invoices:
            if invoice.lookalike_of == 'round_total':
                assert invoice.grand_total % 1000 == 0
                assert any((invoice.issuer_code, l.description) in card
                           for l in invoice.lines)

    def test_a_recurring_charge_repeats_on_a_schedule(self, year):
        twins = sorted((i for i in year.invoices
                        if i.lookalike_of == 'near_duplicate'),
                       key=lambda i: i.issue_date)
        assert len(twins) >= 6
        assert len({i.grand_total for i in twins}) == 1
        gaps = {(b.issue_date - a.issue_date).days for a, b in zip(twins, twins[1:])}
        assert gaps == {lookalikes.RECURRING_DAYS}

    def test_an_allowed_surcharge_is_on_the_rate_card(self, year):
        allowed = {f['description'] for f in lookalikes.ALLOWED_SURCHARGES}
        for invoice in year.invoices:
            if invoice.lookalike_of == 'freight_overbill':
                assert any(l.description in allowed for l in invoice.lines)


class TestDrift:
    def test_the_drift_run_doubles_the_freight_errors_late(self):
        run = Operation(START, profile=DRIFT).run()
        half = START.toordinal() + DRIFT.weeks * 7 // 2

        def share(invoices):
            freight = [i for i in invoices if i.kind == 'freight']
            return sum(i.anomaly == 'freight_overbill' for i in freight) / len(freight)

        early = [i for i in run.invoices if i.issue_date.toordinal() < half]
        late = [i for i in run.invoices if i.issue_date.toordinal() >= half]

        assert share(late) > 1.5 * share(early)


class TestNothingElseMoves:
    def test_the_quiet_run_is_unchanged(self):
        run = Operation(START).run()

        assert len(run.invoices) == 106
        assert not any(i.anomaly or i.lookalike_of or i.pay_to or i.sender
                       for i in run.invoices)
