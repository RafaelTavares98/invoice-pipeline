from datetime import date
from decimal import Decimal

from formatting import (format_amount, format_date, format_price,
                        format_quantity)


class TestAmount:
    def test_a_dot_country_groups_with_commas(self):
        assert format_amount(Decimal('1234567.5'), 'dot') == '1,234,567.50'

    def test_a_comma_country_swaps_both_marks(self):
        assert format_amount(Decimal('1234567.5'), 'comma') == '1.234.567,50'

    def test_two_decimal_places_always(self):
        assert format_amount(Decimal('8'), 'dot') == '8.00'


class TestPrice:
    def test_a_price_keeps_the_decimals_it_was_quoted_with(self):
        assert format_price(Decimal('0.0628'), 'dot') == '0.0628'

    def test_three_decimals_stay_three(self):
        assert format_price(Decimal('0.515'), 'dot') == '0.515'

    def test_a_whole_price_shows_two(self):
        assert format_price(Decimal('1850.00'), 'dot') == '1,850.00'

    def test_a_comma_country_swaps_the_mark(self):
        assert format_price(Decimal('1850.00'), 'comma') == '1.850,00'


class TestQuantity:
    def test_a_quantity_has_no_decimals(self):
        assert format_quantity(Decimal('12000'), 'dot') == '12,000'

    def test_a_comma_country_groups_with_dots(self):
        assert format_quantity(Decimal('12000'), 'comma') == '12.000'


class TestDate:
    day = date(2026, 3, 7)

    def test_iso(self):
        assert format_date(self.day, 'iso') == '2026-03-07'

    def test_day_first(self):
        assert format_date(self.day, 'day_first') == '07/03/2026'

    def test_month_first(self):
        assert format_date(self.day, 'month_first') == '03/07/2026'

    def test_the_same_day_reads_differently_in_each_order(self):
        written = {format_date(self.day, order)
                   for order in ('iso', 'day_first', 'month_first')}

        assert len(written) == 3
