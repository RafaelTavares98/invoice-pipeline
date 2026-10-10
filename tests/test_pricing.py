import statistics

import catalogue
import pricing


class TestUnitPrice:
    def test_a_quote_sits_near_the_catalogue_price(self):
        rng = pricing.seeded(7)
        part = catalogue.by_code('CP-024F')

        drawn = [
            float(pricing.unit_price(rng, part, 1.0, 0.09, part.pack_size))
            for _ in range(400)
        ]

        assert abs(statistics.mean(drawn) - part.base_price) < part.base_price * 0.05

    def test_a_quote_lands_on_many_different_ticks(self):
        rng = pricing.seeded(11)
        part = catalogue.by_code('GB-050A')

        drawn = {
            pricing.unit_price(rng, part, 1.0, 0.09, part.pack_size)
            for _ in range(200)
        }

        assert len(drawn) > 100

    def test_an_expensive_supplier_quotes_higher(self):
        part = catalogue.by_code('GB-050A')
        cheap = [float(pricing.unit_price(pricing.seeded(i), part, 0.85, 0.09,
                                          part.pack_size)) for i in range(200)]
        dear = [float(pricing.unit_price(pricing.seeded(i), part, 1.20, 0.09,
                                         part.pack_size)) for i in range(200)]

        assert statistics.mean(dear) > statistics.mean(cheap)

    def test_a_large_order_lowers_the_unit_price(self):
        part = catalogue.by_code('CP-024F')
        small = [float(pricing.unit_price(pricing.seeded(i), part, 1.0, 0.05,
                                          part.pack_size)) for i in range(200)]
        large = [float(pricing.unit_price(pricing.seeded(i), part, 1.0, 0.05,
                                          part.pack_size * 30)) for i in range(200)]

        assert statistics.mean(large) < statistics.mean(small)

    def test_the_same_seed_gives_the_same_quote(self):
        part = catalogue.by_code('PM-024G')

        first = pricing.unit_price(pricing.seeded(99), part, 1.0, 0.09, 5000)
        second = pricing.unit_price(pricing.seeded(99), part, 1.0, 0.09, 5000)

        assert first == second


class TestOrderQuantity:
    def test_an_order_is_a_whole_number_of_packs(self):
        rng = pricing.seeded(3)
        part = catalogue.by_code('LB-GL01')

        for _ in range(100):
            assert pricing.order_quantity(rng, part) % part.pack_size == 0


class TestFreightRate:
    def test_a_freight_rate_sits_near_its_base(self):
        drawn = [float(pricing.freight_rate(pricing.seeded(i), 1850.0, 1.0, 0.12))
                 for i in range(300)]

        assert abs(statistics.mean(drawn) - 1850.0) < 1850.0 * 0.05

    def test_freight_moves_more_than_a_component_price(self):
        rng = pricing.seeded(4)
        part = catalogue.by_code('GB-050A')

        freight = [float(pricing.freight_rate(pricing.seeded(i), 1850.0, 1.0, 0.17))
                   for i in range(300)]
        goods = [float(pricing.unit_price(rng, part, 1.0, 0.07, part.pack_size))
                 for _ in range(300)]

        spread = lambda values: statistics.pstdev(values) / statistics.mean(values)

        assert spread(freight) > spread(goods)
