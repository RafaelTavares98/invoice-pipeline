"""The answer key has to be an answer, not a restatement of the question."""

from datetime import date
from decimal import Decimal

import pytest

import ledger
from operation import Operation

START = date(2026, 4, 6)


@pytest.fixture(scope='module')
def run():
    return Operation(START, seed=4242).run()


@pytest.fixture(scope='module')
def book(run):
    return ledger.build(run)


class TestTheShape:
    def test_it_carries_every_part_of_the_chain(self, book):
        assert set(book) == {'window', 'orders', 'shipments',
                             'invoices', 'chains', 'counts'}

    def test_the_window_says_when_it_opened(self, book):
        assert book['window']['start'] == START.isoformat()
        assert book['window']['weeks'] == 8

    def test_there_is_one_record_per_invoice(self, book, run):
        assert len(book['invoices']) == len(run.invoices)


class TestTheChains:
    def test_a_chain_adds_up(self, book):
        for chain in book['chains']:
            landed = (Decimal(chain['goods_total'])
                      + Decimal(chain['freight_total'])
                      + Decimal(chain['credit_total']))

            assert Decimal(chain['landed_cost']) == landed

    def test_freight_is_split_between_the_orders_in_a_box(self, run):
        chains = ledger.chains(run)
        shared = [c for c in chains if len(c['freight_share']) > 1]

        assert shared, 'no chain ever had more than one freight invoice'
        for chain in shared:
            counted = sum(Decimal(v) for v in chain['freight_share'].values())

            assert abs(counted - Decimal(chain['freight_total'])) < Decimal('0.05')

    def test_a_container_is_not_billed_twice(self, run):
        """Every freight invoice may be spread across orders, but the
        slices must not add up to more than the invoice."""
        chains = ledger.chains(run)
        by_invoice = {}
        for chain in chains:
            for number, slice_ in chain['freight_share'].items():
                by_invoice[number] = by_invoice.get(number, Decimal('0')) \
                    + Decimal(slice_)

        payable = {i.number: i.grand_total for i in run.invoices
                   if i.kind == 'freight'}
        for number, counted in by_invoice.items():
            assert counted <= payable[number] + Decimal('0.05')

    def test_every_chain_points_at_a_real_order(self, book):
        numbers = {order['number'] for order in book['orders']}

        for chain in book['chains']:
            assert chain['order_number'] in numbers


class TestWhatMustNotBePaid:
    def test_the_invoice_a_revision_replaces_is_dropped(self, run):
        revised = {i.revises for i in run.invoices if i.number.endswith('-R1')}
        paid = {number
                for chain in ledger.chains(run)
                for number in chain['goods_invoices']}

        assert not (revised & paid)

    def test_a_credit_note_lowers_the_landed_cost(self, run):
        chains = ledger.chains(run)
        credited = [c for c in chains if c['credit_notes']]

        assert credited, 'no credit note was ever raised'
        for chain in credited:
            assert Decimal(chain['credit_total']) < 0


class TestTheCounts:
    def test_the_corpus_is_not_clean(self, book):
        counts = book['counts']

        assert counts['duplicate_numbers'] > 0
        assert counts['revisions'] > 0
        assert counts['wrong_order_quoted'] > 0

    def test_every_kind_of_document_appears(self, book):
        assert set(book['counts']['by_kind']) == {'goods', 'freight', 'credit'}

    def test_there_are_more_invoices_than_orders(self, book):
        counts = book['counts']

        assert counts['invoices'] > counts['orders']
