from datetime import date
from decimal import Decimal

from business.invoice import Invoice, Line


def _invoice(**overrides):
    defaults = dict(
        number='TST-0001',
        issue_date=date(2026, 3, 2),
        due_date=date(2026, 4, 1),
        issuer_code='TST',
    )
    defaults.update(overrides)
    return Invoice(**defaults)


class TestLine:
    def test_net_is_quantity_times_unit_price(self):
        line = Line('Screw cap', Decimal(10000), Decimal('0.062'))

        assert line.net == Decimal('620.00')

    def test_a_fractional_price_still_lands_on_cents(self):
        line = Line('Label', Decimal(20000), Decimal('0.0283'))

        assert line.net == Decimal('566.00')


class TestTotals:
    def test_subtotal_is_the_sum_of_the_lines(self):
        invoice = _invoice(lines=[
            Line('A', Decimal(2), Decimal('10')),
            Line('B', Decimal(3), Decimal('5')),
        ])

        assert invoice.subtotal == Decimal('35.00')

    def test_subtotal_of_an_empty_invoice_is_zero(self):
        assert _invoice().subtotal == Decimal('0.00')

    def test_discount_comes_off_the_total(self):
        invoice = _invoice(
            lines=[Line('A', Decimal(1), Decimal('100'))],
            discount=Decimal('10.00'),
        )

        assert invoice.grand_total == Decimal('90.00')

    def test_without_a_discount_the_total_is_the_subtotal(self):
        invoice = _invoice(lines=[Line('A', Decimal(4), Decimal('25'))])

        assert invoice.grand_total == invoice.subtotal

    def test_weight_is_the_sum_of_the_lines(self):
        invoice = _invoice(lines=[
            Line('A', Decimal(1), Decimal('1'), weight_kg=Decimal('12.50')),
            Line('B', Decimal(1), Decimal('1'), weight_kg=Decimal('3.25')),
        ])

        assert invoice.total_weight_kg == Decimal('15.75')


class TestCurrency:
    def test_every_invoice_is_in_dollars(self):
        assert _invoice().currency == 'USD'


class TestAnswerKey:
    def test_the_truth_carries_the_grand_total_as_text(self):
        invoice = _invoice(lines=[Line('A', Decimal(1), Decimal('100'))])

        assert invoice.as_truth()['grand_total'] == '100.00'

    def test_the_truth_carries_the_line_count(self):
        invoice = _invoice(lines=[
            Line('A', Decimal(1), Decimal('1')),
            Line('B', Decimal(1), Decimal('1')),
        ])

        assert invoice.as_truth()['line_count'] == 2

    def test_the_truth_reconciles_with_the_lines(self):
        invoice = _invoice(
            lines=[Line('A', Decimal(3), Decimal('12.50'))],
            discount=Decimal('2.50'),
        )
        truth = invoice.as_truth()

        assert truth['subtotal'] == '37.50'
        assert truth['discount'] == '2.50'
        assert truth['grand_total'] == '35.00'
