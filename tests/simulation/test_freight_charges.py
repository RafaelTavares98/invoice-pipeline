"""The rest of the freight bill: air, local charges in Santos, storage.

Checked by hand against the sources in docs/reference.md.
"""

from datetime import date
from decimal import Decimal

from business import issuers
from simulation import freight

D = Decimal
DAY = date(2026, 5, 4)


class TestAir:
    def test_charged_on_the_greater_of_kg_and_volume(self):
        """2 m³ is 334 kg by volume (×167), more than the 250 kg real."""
        bill = freight.air_invoice(issuers.by_code('DHI'), DAY, 'Ningbo',
                                   D('2'), D('250'))

        line = bill.lines[0]
        assert (line.unit, line.quantity) == ('kg', D('334.0'))
        assert line.unit_price == freight.AIR_RATE

    def test_the_rate_is_what_2026_says(self):
        """US$8.30 to 9.00 per kg, China to Brazil, 2026 (BSI)."""
        assert D('8.30') <= freight.AIR_RATE <= D('9.00')


class TestLocalCharges:
    def test_fcl_pays_handling_per_container_and_one_release(self):
        bill = freight.local_charges(issuers.by_code('MRK'), DAY,
                                     containers=['40GP', '20GP'])

        lines = {l.description: l for l in bill.lines}
        assert lines['Terminal handling (capatazia), per container'].quantity == D(2)
        assert lines['Terminal handling (capatazia), per container'].unit_price == D('3700.00')
        assert lines['B/L release'].net == D('1000.00')
        assert bill.currency == 'BRL'
        assert bill.kind == 'local'

    def test_lcl_pays_handling_per_wm_with_a_minimum(self):
        bill = freight.local_charges(issuers.by_code('DHI'), DAY, wm=D('1.20'))

        handling = bill.lines[0]
        assert handling.net == D('150.00')

    def test_lcl_handling_above_the_minimum(self):
        bill = freight.local_charges(issuers.by_code('DHI'), DAY, wm=D('6.80'))

        assert bill.lines[0].net == D('544.00')


class TestStorage:
    def test_fcl_first_week_is_a_share_of_cif_with_a_minimum(self):
        """0.48% of R$100,000 is R$480, under the R$1,881.43 minimum for a
        40' (Santos Brasil)."""
        bill = freight.storage_invoice(DAY, D('100000'), containers=['40GP'])

        assert bill.grand_total == D('1881.43')

    def test_fcl_above_the_minimum(self):
        bill = freight.storage_invoice(DAY, D('800000'), containers=['40GP'])

        assert bill.grand_total == D('3840.00')

    def test_lcl_first_period(self):
        """1.16% of CIF for the first period (Clif)."""
        bill = freight.storage_invoice(DAY, D('120000'))

        assert bill.grand_total == D('1392.00')

    def test_it_comes_from_the_terminal_in_reais(self):
        bill = freight.storage_invoice(DAY, D('120000'))

        assert bill.issuer_code == 'TVA'
        assert bill.currency == 'BRL'
        assert bill.kind == 'storage'


def test_the_terminal_is_an_issuer():
    terminal = issuers.by_code('TVA')

    assert terminal.currency == 'BRL'
    assert terminal.kind == 'terminal'


def test_all_in_counts_every_charge_a_load_brings():
    """Freight, the Santos charges, the storage and the truck: a small
    cargo goes LCL, a large one FCL."""
    from decimal import Decimal
    from simulation import freight
    small = freight.all_in_usd(Decimal('5'), Decimal('900'), Decimal('5.40'),
                               Decimal('20000'))
    large = freight.all_in_usd(Decimal('60'), Decimal('9000'), Decimal('5.40'),
                               Decimal('90000'))

    assert small[1] < small[0]
    assert large[0] < large[1]


def test_lcl_local_charges_carry_the_deconsolidation():
    """US$ 200 a B/L, billed in reais at the day's rate."""
    from datetime import date
    from decimal import Decimal
    from business import issuers
    from simulation import freight
    bill = freight.local_charges(issuers.by_code('DHI'), date(2026, 5, 4),
                                 wm=Decimal('5'), fx=Decimal('5.00'))

    assert any(line.description.startswith('Desconsolidacao')
               and line.unit_price == Decimal('1000.00') for line in bill.lines)


def test_fcl_local_charges_carry_the_siscarga_fee():
    """US$ 60 a B/L, billed in reais at the day's rate."""
    from datetime import date
    from decimal import Decimal
    from business import issuers
    from simulation import freight
    bill = freight.local_charges(issuers.by_code('MRK'), date(2026, 5, 4),
                                 containers=['40GP'], fx=Decimal('5.00'))

    assert any(line.description.startswith('Siscarga')
               and line.unit_price == Decimal('300.00') for line in bill.lines)
