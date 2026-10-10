"""Two invoices are almost never the same, which is the point of the set."""

from decimal import Decimal

import invoice_builder
import issuers


def _batch(issuer, count=120):
    return [invoice_builder.invoice_for(issuer, seed=seed)
            for seed in range(count)]


class TestEveryInvoiceIsItsOwn:
    def test_two_invoices_from_one_factory_differ(self):
        for factory in issuers.FACTORIES:
            totals = {invoice.grand_total for invoice in _batch(factory)}

            assert len(totals) > 110, factory.code

    def test_two_invoices_from_one_carrier_differ(self):
        for carrier in issuers.CARRIERS:
            totals = {invoice.grand_total for invoice in _batch(carrier)}

            assert len(totals) > 110, carrier.code

    def test_numbers_do_not_collide(self):
        numbers = [invoice.number
                   for issuer in issuers.ALL_ISSUERS
                   for invoice in _batch(issuer, 60)]

        assert len(set(numbers)) > len(numbers) * 0.97


class TestItStaysSane:
    def test_the_same_seed_rebuilds_the_same_invoice(self):
        first = invoice_builder.invoice_for(issuers.FACTORIES[0], seed=5)
        second = invoice_builder.invoice_for(issuers.FACTORIES[0], seed=5)

        assert first.number == second.number
        assert first.grand_total == second.grand_total

    def test_every_invoice_has_at_least_one_line(self):
        for issuer in issuers.ALL_ISSUERS:
            for invoice in _batch(issuer, 40):
                assert invoice.lines

    def test_the_total_is_never_negative(self):
        for issuer in issuers.ALL_ISSUERS:
            for invoice in _batch(issuer, 40):
                assert invoice.grand_total > Decimal('0')

    def test_the_due_date_follows_the_issue_date(self):
        for issuer in issuers.ALL_ISSUERS:
            for invoice in _batch(issuer, 40):
                assert invoice.due_date > invoice.issue_date

    def test_a_factory_only_sells_what_it_makes(self):
        import catalogue

        for factory in issuers.FACTORIES:
            allowed = {part.code for family in factory.families
                       for part in catalogue.BY_FAMILY[family]}
            for invoice in _batch(factory, 40):
                for line in invoice.lines:
                    if not line.code:
                        continue        # tooling and samples carry no part no.
                    assert line.code in allowed

    def test_a_factory_ships_from_its_own_port(self):
        for factory in issuers.FACTORIES:
            port = invoice_builder.LOADING_PORT[factory.code]
            invoice = invoice_builder.invoice_for(factory, seed=1)

            assert invoice.incoterm.endswith(port)

    def test_an_air_consignment_is_smaller_than_an_ocean_one(self):
        air = [c for c in issuers.CARRIERS if c.mode == 'air'][0]
        ocean = [c for c in issuers.CARRIERS if c.mode == 'ocean'][0]

        air_weight = max(float(i.shipment['weight_kg']) for i in _batch(air, 40))
        ocean_weight = min(float(i.shipment['weight_kg'])
                           for i in _batch(ocean, 40))

        assert air_weight < ocean_weight
