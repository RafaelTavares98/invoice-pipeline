"""Freight charged the way the cargo travels: per container, or per W/M.

Checked by hand. A full container (FCL) costs its rate however full; the
smallest set of containers that holds both the volume and the weight is
the one booked. A shared container (LCL) costs the rate times the greater
of cubic metres and tonnes, at least one.
"""

from datetime import date
from decimal import Decimal

import pytest

from business import issuers
from simulation import freight

D = Decimal


class TestWhichContainers:
    def test_a_small_load_fits_one_20_foot(self):
        assert freight.containers_for(D('20'), D('5000')) == ['20GP']

    def test_more_volume_takes_a_40_foot(self):
        assert freight.containers_for(D('58.4'), D('9850')) == ['40GP']

    def test_more_still_takes_a_high_cube(self):
        assert freight.containers_for(D('70'), D('9000')) == ['40HC']

    def test_too_much_for_one_takes_two(self):
        """90 m³: one high cube holds 76, the rest fits a 20'."""
        assert freight.containers_for(D('90'), D('12000')) == ['40HC', '20GP']

    def test_weight_can_rule_out_a_20_foot(self):
        """30 m³ fits a 20' by volume, but 24 t is over its 21 t."""
        assert freight.containers_for(D('30'), D('24000')) == ['40GP']


class TestWeightOrMeasure:
    def test_volume_wins_for_light_cargo(self):
        assert freight.wm(D('6.8'), D('1240')) == D('6.80')

    def test_weight_wins_for_heavy_cargo(self):
        assert freight.wm(D('2'), D('3500')) == D('3.50')

    def test_never_under_one(self):
        assert freight.wm(D('0.4'), D('200')) == D('1.00')


class TestTheRates:
    def test_a_40_foot_costs_what_2026_says(self):
        """About US$5,600 to 6,000 per 40', Asia to the east coast of
        South America, August 2026 (S&P Global)."""
        assert D('5600') <= freight.FCL_RATE['40GP'] <= D('6000')
        assert D('5600') <= freight.FCL_RATE['40HC'] <= D('6000')

    def test_a_20_foot_costs_less(self):
        assert freight.FCL_RATE['20GP'] < freight.FCL_RATE['40GP']

    def test_a_20_foot_costs_what_2026_says(self):
        """US$4,000 to 4,500 per 20', China to Brazil, 2026 (BSI)."""
        assert D('4000') <= freight.FCL_RATE['20GP'] <= D('4500')

    def test_lcl_costs_what_2026_says(self):
        """US$80 to 150 per m³, China to South America, 2026 (Delpa)."""
        assert D('80') <= freight.LCL_RATE <= D('150')


@pytest.fixture
def day():
    return date(2026, 5, 4)


class TestTheFclInvoice:
    def test_one_line_per_container_size(self, day):
        bill = freight.fcl_invoice(issuers.by_code('MRK'), day, 'Ningbo',
                                   D('90'), D('12000'))

        assert [(l.unit, l.quantity) for l in bill.lines] == \
            [('container', D(1)), ('container', D(1))]

    def test_the_total_is_containers_times_rate(self, day):
        bill = freight.fcl_invoice(issuers.by_code('MRK'), day, 'Ningbo',
                                   D('58.4'), D('9850'))

        assert bill.grand_total == freight.FCL_RATE['40GP']

    def test_it_is_a_freight_invoice_from_the_line(self, day):
        bill = freight.fcl_invoice(issuers.by_code('MRK'), day, 'Ningbo',
                                   D('58.4'), D('9850'))

        assert bill.kind == 'freight'
        assert bill.issuer_code == 'MRK'
        assert bill.shipment['container'] == '40GP'


class TestTheLclInvoice:
    def test_one_line_charged_per_wm(self, day):
        bill = freight.lcl_invoice(issuers.by_code('DHI'), day, 'Ningbo',
                                   D('6.8'), D('1240'))

        line = bill.lines[0]
        assert (line.unit, line.quantity) == ('W/M', D('6.80'))
        assert line.unit_price == freight.LCL_RATE

    def test_the_total_is_wm_times_rate(self, day):
        bill = freight.lcl_invoice(issuers.by_code('DHI'), day, 'Ningbo',
                                   D('6.8'), D('1240'))

        assert bill.grand_total == (D('6.80') * freight.LCL_RATE).quantize(D('0.01'))

    def test_it_says_lcl_on_the_page(self, day):
        bill = freight.lcl_invoice(issuers.by_code('DHI'), day, 'Ningbo',
                                   D('6.8'), D('1240'))

        assert bill.shipment['container'] == 'LCL'
