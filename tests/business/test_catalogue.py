"""Every part ships in cartons, and the carton says how much room it takes.

The cost of a container is split by the room each part takes, so each
part needs its carton: how many units, how big, how heavy, and where the
figures came from.
"""

from decimal import Decimal

from business import catalogue


def test_every_part_has_a_carton_with_a_source():
    for part in catalogue.CATALOGUE:
        carton = part.carton
        assert carton.units > 0, part.code
        assert all(side > 0 for side in carton.cm), part.code
        assert carton.source, part.code


def test_a_carton_weighs_at_least_what_it_holds():
    for part in catalogue.CATALOGUE:
        held = Decimal(str(part.grams)) * part.carton.units / 1000
        assert part.carton.kg >= held, part.code


def test_the_room_one_unit_takes_is_its_share_of_the_carton():
    pump = catalogue.by_code('PM-024G')

    assert pump.unit_m3 == (Decimal('0.54') * Decimal('0.38')
                            * Decimal('0.39') / 1000)


def test_a_glass_bottle_takes_more_room_than_a_cap():
    assert catalogue.by_code('GB-100B').unit_m3 > \
        catalogue.by_code('CP-024F').unit_m3
