"""The Brazilian side of an import: the duties, the broker and the truck.

When a shipment lands in Santos, three documents follow it, all in reais:

- the duty statement the customs broker sends after registering the
  import declaration (DUIMP): the customs value, then each tax on its
  base, at its rate;
- the broker's own service invoice;
- the truck from the port to Louveira.

The customs value is the goods plus the international freight plus the
insurance, converted at the day's rate. II and IPI hang on each item's
NCM; PIS and COFINS on the customs value; AFRMM on ocean freight; ICMS is
charged inside its own base. The rates come from business/tariffs.py.
"""

from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from business import tariffs
from business.invoice import Invoice, Line
from drawing.formatting import format_amount, format_price

CENT = Decimal('0.01')

#: The broker's contract: what each service costs, in reais.
FEES = {
    'Customs clearance fee': Decimal('1450.00'),
    'Document handling': Decimal('180.00'),
    'Container handling, THC': Decimal('1150.00'),
    'Airport cargo handling': Decimal('650.00'),
}

#: Port storage, per day, in reais.
STORAGE_PER_DAY = (Decimal('380.00'), Decimal('520.00'))

#: The truck from Santos to Louveira, per trip, in reais.
TRUCK_PER_TRIP = 3900.0
VAN_PER_TRIP = 1200.0
GRIS = Decimal('0.003')


def _money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _line(description, base, rate):
    return Line(description=description, quantity=_money(base),
                unit_price=rate, unit='BRL')


def goods_by_ncm(goods):
    """The goods value on a shipment, in dollars, by NCM.

    Each invoice's service lines and discount are spread over its coded
    lines by value, so the NCM values add up to what the invoices bill."""
    found = OrderedDict()
    for invoice in goods:
        coded = [line for line in invoice.lines if line.code]
        counted = sum((line.net for line in coded), Decimal(0))
        if not counted:
            continue
        factor = invoice.grand_total / counted
        for line in coded:
            ncm = tariffs.ncm_for(line.hs_code)
            found[ncm] = found.get(ncm, Decimal(0)) + line.net * factor
    return found


def statement_lines(by_ncm, freight_usd, ocean, fx, day, changes=(),
                    duty_rate=None):
    """Every tax line of one declaration, and the customs value in reais.

    `duty_rate` may return a different II rate for an NCM. A declaration
    carrying a wrong rate must still add up: the IPI base and the ICMS
    are both built from the duty, so the slip has to happen here rather
    than be painted on afterwards. Otherwise the error is caught by
    arithmetic alone, and the point is to catch it against the tariff
    table.
    """
    goods_usd = sum(by_ncm.values(), Decimal(0))
    insurance = goods_usd * tariffs.INSURANCE
    lines, customs_value = [], Decimal(0)
    for ncm, value in by_ncm.items():
        share = value / goods_usd if goods_usd else Decimal(0)
        base = _money((value + (freight_usd + insurance) * share) * fx)
        customs_value += base
        rate = tariffs.rate_on(ncm, day, changes)
        ii = rate.ii if duty_rate is None else duty_rate(ncm, rate.ii)
        duty = _line(f'II {ncm}', base, ii)
        lines += [
            duty,
            _line(f'IPI {ncm}', base + duty.net, rate.ipi),
            _line(f'PIS-Importacao {ncm}', base, tariffs.PIS),
            _line(f'COFINS-Importacao {ncm}', base, rate.cofins),
        ]
    if ocean:
        lines.append(_line('AFRMM', freight_usd * fx, tariffs.AFRMM))
    lines.append(Line(description='Taxa Siscomex', quantity=Decimal(1),
                      unit_price=tariffs.SISCOMEX, unit='BRL'))
    before = sum((line.net for line in lines), Decimal(0)) + customs_value
    inside = _money(before / (1 - tariffs.ICMS))
    lines.append(_line('ICMS SP', inside, tariffs.ICMS))
    return lines, _money(customs_value)


def duimp_number(rng, day):
    return f'{day:%y}BR{rng.randint(10 ** 9, 10 ** 10 - 1)}'


def statement(rng, shipment, goods, freight, day, fx, number, changes=(),
              duty_rate=None):
    """The broker's duty statement for one shipment."""
    by_ncm = goods_by_ncm(goods)
    freight_usd = sum((invoice.grand_total for invoice in freight), Decimal(0))
    lines, value = statement_lines(by_ncm, freight_usd,
                                   shipment.mode == 'ocean', fx, day, changes,
                                   duty_rate)
    return Invoice(
        number=number,
        issue_date=day,
        due_date=day,
        issuer_code='SCA',
        lines=lines,
        reference=shipment.identifier,
        kind='customs',
        shipment_id=shipment.identifier,
        currency='BRL',
        facts=(('DUIMP', duimp_number(rng, day)),
               ('FX rate', format_price(fx, 'comma')),
               ('Customs value', format_amount(value, 'comma'))),
    )


def broker_invoice(rng, shipment, day, number):
    """The broker's own fees: clearance, documents, handling, storage."""
    handling = ('Container handling, THC' if shipment.mode == 'ocean'
                else 'Airport cargo handling')
    lines = [Line(description=name, quantity=Decimal(1),
                  unit_price=FEES[name], unit='lot')
             for name in ('Customs clearance fee', 'Document handling',
                          handling)]
    days = rng.randint(1, 9)
    per_day = _money(rng.uniform(*map(float, STORAGE_PER_DAY)))
    lines.append(Line(description=f'Port storage, {days} days',
                      quantity=Decimal(days), unit_price=per_day, unit='day'))
    return Invoice(
        number=number,
        issue_date=day,
        due_date=day + timedelta(days=15),
        issuer_code='SCA',
        lines=lines,
        reference=shipment.identifier,
        kind='broker',
        shipment_id=shipment.identifier,
        currency='BRL',
    )


def trucker_invoice(rng, shipment, day, cargo_brl, number, box):
    """The truck from Santos to Louveira, in reais: one truck per
    container for FCL, a van for a part load, shared space or air."""
    boxes = getattr(shipment, 'boxes', ())
    part_load = getattr(shipment, 'load', '') in ('LCL', 'air') or \
        shipment.mode != 'ocean'
    base = VAN_PER_TRIP if part_load else TRUCK_PER_TRIP
    trip = _money(rng.lognormvariate(0, 0.10) * base)
    lines = [Line(
        description=(f'Road haulage Santos to Louveira, '
                     f'{"part load" if part_load else shipment.container}'),
        quantity=Decimal(len(boxes) or 1), unit_price=trip, unit='trip',
        weight_kg=shipment.weight_kg, volume_m3=shipment.volume_m3)]
    lines.append(Line(description='Pedagio', quantity=Decimal(1),
                      unit_price=_money(rng.uniform(180, 260)), unit='lot'))
    lines.append(Line(description='GRIS, cargo insurance',
                      quantity=Decimal(1), unit_price=_money(cargo_brl * GRIS),
                      unit='lot'))
    if rng.random() < 0.4:
        lines.append(Line(description='Taxa de descarga', quantity=Decimal(1),
                          unit_price=Decimal('350.00'), unit='lot'))
    return Invoice(
        number=number,
        issue_date=day,
        due_date=day + timedelta(days=21),
        issuer_code='TLV',
        lines=lines,
        reference=shipment.identifier,
        kind='freight',
        shipment_id=shipment.identifier,
        shipment=box,
        currency='BRL',
    )
