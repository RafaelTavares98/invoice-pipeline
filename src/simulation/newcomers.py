"""Companies that join the vendor master during a run.

Two kinds look alike on paper: a new name, few invoices, no history. A
new supplier comes with a purchase order and goods that arrive. An
unmatched vendor was entered in the master with no order behind it, so
its bills for services in round sums match no order and no receipt: an
error at the purchasing stage.
"""

from dataclasses import replace

from business import issuers

UNMATCHED_NAMES = (
    ('QPS', 'Quantum Pack Solutions Ltd.', 'Hong Kong'),
    ('GLC', 'Greenline Sourcing Consultants', 'Singapore'),
    ('APX', 'Apex Trade Services LLC', 'United Arab Emirates'),
    ('NVL', 'Novalink Packaging Advisory', 'Hong Kong'),
    ('SMV', 'Summit Vendor Services Ltd.', 'Singapore'),
    ('ORB', 'Orbis Supply Partners', 'Hong Kong'),
)

#: What an unmatched vendor bills for: nothing counted on arrival.
UNMATCHED_SERVICES = ('Packaging design consultancy', 'Supplier audit services',
                      'Sourcing support, monthly', 'Quality inspection services')

#: In the drift scenario, unmatched vendors bill as freight forwarders.
UNMATCHED_FREIGHT_SERVICES = ('Port coordination services',
                              'Documentation handling, consolidated')

NEW_SUPPLIERS = (
    ('TPK', 'Taizhou Primepack Plastics Co., Ltd.', 'China'),
    ('VNC', 'Vinacap Closures Joint Stock Co.', 'Vietnam'),
    ('KRB', 'Kyungbo Pump Systems Co., Ltd.', 'South Korea'),
    ('JHP', 'Jinhua Packtech Industrial Co., Ltd.', 'China'),
)


def _account(rng):
    return (f'{rng.choice(("HSBC", "Standard Chartered", "DBS Bank"))}  '
            f'Acct {rng.randint(100, 999)}-{rng.randint(100000, 999999)}-'
            f'{rng.randint(100, 999)}')


def _clone(rng, template, code, name, country):
    return issuers.register(replace(
        template,
        code=code,
        name=name,
        address=('Room 1203, Commerce Tower', country, country),
        country=country,
        tax_id=f'{rng.randint(10 ** 9, 10 ** 10 - 1)}',
        bank_line=_account(rng),
        number_prefix=code,
    ))


def unmatched(rng, index):
    """A vendor entered with no order, on a real factory's page design."""
    code, name, country = UNMATCHED_NAMES[index % len(UNMATCHED_NAMES)]
    template = rng.choice(issuers.FACTORIES)
    return _clone(rng, template, code, name, country)


def new_supplier(rng, index):
    """A real factory that wins business mid-run; it reuses the lane of a
    factory in its country, so its goods come by the same route."""
    code, name, country = NEW_SUPPLIERS[index % len(NEW_SUPPLIERS)]
    template = next((f for f in issuers.FACTORIES if f.country == country),
                    issuers.FACTORIES[0])
    return _clone(rng, template, code, name, country), template
