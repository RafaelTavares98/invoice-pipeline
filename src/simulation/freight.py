"""Freight charged the way the cargo travels.

A full container (FCL) is one price per box, however full. The booking is
the smallest set of boxes that holds both the volume and the weight. A
shared container (LCL) is charged per W/M: the greater of cubic metres and
tonnes, never less than one.

Sources: container sizes, AB Group Shipping; FCL and LCL pricing rules,
iContainers; the 40' rate, S&P Global, August 2026. See docs/reference.md.
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from business.invoice import Invoice, Line
from drawing.formatting import format_amount

CENT = Decimal('0.01')

#: Volume in m³ and payload in kg, smallest first.
CONTAINERS = {
    '20GP': (Decimal('33'), Decimal('21000')),
    '40GP': (Decimal('67'), Decimal('26000')),
    '40HC': (Decimal('76'), Decimal('26000')),
}

#: Ocean freight per container, Asia to Santos. The 40' figures sit in the
#: US$5,600 to 6,000 S&P Global reported for August 2026; the 20' in the
#: US$4,000 to 4,500 BSI Freight quotes for China to Brazil in 2026.
FCL_RATE = {
    '20GP': Decimal('4250.00'),
    '40GP': Decimal('5800.00'),
    '40HC': Decimal('5950.00'),
}

#: LCL ocean freight per W/M. Delpa Group quotes US$80 to 150 per m³ from
#: China to Chile in 2026; no Santos figure was found, so the nearest South
#: American route stands in.
LCL_RATE = Decimal('95.00')

#: Air freight per chargeable kg, China to Brazil: BSI Freight quotes
#: US$8.30 to 9.00 in 2026.
AIR_RATE = Decimal('8.60')

#: kg per m³ of volume weight: the IATA 1 to 6,000 rule.
AIR_KG_PER_M3 = Decimal('167')

#: Local charges in Santos, in reais (General Noli tariff, August 2025).
CAPATAZIA_FCL = Decimal('3700.00')      # per container
CAPATAZIA_LCL = Decimal('80.00')        # per W/M
CAPATAZIA_LCL_MINIMUM = Decimal('150.00')
BL_RELEASE = Decimal('1000.00')         # per B/L
#: Charged in dollars per B/L, billed in reais at the day's rate.
SISCARGA_USD = Decimal('60.00')         # FCL, the cargo registration fee
DECONSOLIDATION_USD = Decimal('200.00')  # LCL, unpacking the shared box

#: Storage in the bonded terminal, first period, as a share of CIF.
#: FCL 0.48% for 7 days with a minimum per container (Santos Brasil);
#: LCL 1.16% for the first period (Clif).
STORAGE_FCL = Decimal('0.0048')
STORAGE_LCL = Decimal('0.0116')
STORAGE_MINIMUM = {'20GP': Decimal('1466.88'), '40GP': Decimal('1881.43'),
                   '40HC': Decimal('1881.43')}

DESTINATION = 'Santos'


def containers_for(m3, kg):
    """The smallest set of containers that holds the volume and the weight."""
    for size, (room, payload) in CONTAINERS.items():
        if m3 <= room and kg <= payload:
            return [size]
    room, payload = CONTAINERS['40HC']
    share = min(room / m3, payload / kg)
    return ['40HC'] + containers_for(m3 - room, max(kg - kg * share, Decimal(0)))


def wm(m3, kg):
    """Weight or measure: m³ or tonnes, whichever is greater, at least 1."""
    return max(Decimal(m3), Decimal(kg) / 1000, Decimal(1)).quantize(
        CENT, rounding=ROUND_HALF_UP)


def all_in_usd(m3, kg, fx, cif_usd=Decimal(0)):
    """What FCL and LCL would each cost, every charge the load brings, in
    dollars at fx reais a dollar: the freight, the Santos local charges,
    the first storage period on the CIF value, and the truck, one per
    container or a van for a part load. A sea shipment takes the cheaper."""
    from simulation.customs import TRUCK_PER_TRIP, VAN_PER_TRIP
    m3, kg, fx = Decimal(m3), Decimal(kg), Decimal(fx)
    cif_brl = Decimal(cif_usd) * fx
    boxes = containers_for(m3, kg)
    fcl_brl = (CAPATAZIA_FCL * len(boxes) + BL_RELEASE + SISCARGA_USD * fx
               + max(cif_brl * STORAGE_FCL,
                     sum((STORAGE_MINIMUM[c] for c in boxes), Decimal(0)))
               + Decimal(str(TRUCK_PER_TRIP)) * len(boxes))
    fcl = sum((FCL_RATE[size] for size in boxes), Decimal(0)) + fcl_brl / fx
    measure = wm(m3, kg)
    lcl_brl = (max(CAPATAZIA_LCL * measure, CAPATAZIA_LCL_MINIMUM)
               + BL_RELEASE + DECONSOLIDATION_USD * fx
               + cif_brl * STORAGE_LCL + Decimal(str(VAN_PER_TRIP)))
    lcl = LCL_RATE * measure + lcl_brl / fx
    return fcl.quantize(CENT), lcl.quantize(CENT)


def fcl_invoice(carrier, day, origin, m3, kg, number=None):
    """The line's invoice for a full-container shipment."""
    booked = containers_for(m3, kg)
    lines = [Line(description=f'Ocean freight {origin} to {DESTINATION}, {size}',
                  quantity=Decimal(booked.count(size)),
                  unit_price=FCL_RATE[size], unit='container')
             for size in dict.fromkeys(booked)]
    _carries(lines[0], m3, kg)
    return _invoice(carrier, day, origin, m3, kg, lines, ' + '.join(booked),
                    number)


def lcl_invoice(carrier, day, origin, m3, kg, number=None):
    """The forwarder's invoice for a shared-container shipment."""
    lines = [Line(description=f'LCL ocean freight {origin} to {DESTINATION}',
                  quantity=wm(m3, kg), unit_price=LCL_RATE, unit='W/M')]
    _carries(lines[0], m3, kg)
    return _invoice(carrier, day, origin, m3, kg, lines, 'LCL', number)


def air_invoice(carrier, day, origin, m3, kg, number=None):
    """The forwarder's invoice for a flight: per chargeable kg, the greater
    of the real weight and the volume weight."""
    chargeable = max(Decimal(kg), Decimal(m3) * AIR_KG_PER_M3).quantize(
        Decimal('0.1'), rounding=ROUND_HALF_UP)
    lines = [Line(description=f'Air freight {origin} to Viracopos, chargeable weight',
                  quantity=chargeable, unit_price=AIR_RATE, unit='kg')]
    _carries(lines[0], m3, kg)
    bill = _invoice(carrier, day, origin, m3, kg, lines, 'LOOSE', number)
    bill.shipment['destination'] = 'Viracopos'
    bill.shipment['vessel'] = f'Flight {carrier.code}318'
    bill.reference = f'AWB 160-{day:%y%m%d}01'
    return bill


def local_charges(agent, day, containers=None, wm=None, number=None,
                  shipment_id='', fx=Decimal('5.40')):
    """What the carrier's or forwarder's Santos office bills in reais:
    terminal handling, per container or per W/M, the B/L release, and the
    fee charged in dollars, converted at fx: Siscarga for FCL,
    deconsolidation for LCL."""
    if containers:
        lines = [Line(description='Terminal handling (capatazia), per container',
                      quantity=Decimal(len(containers)),
                      unit_price=CAPATAZIA_FCL, unit='container')]
        dollar_fee = ('Siscarga, US$ 60 per B/L', SISCARGA_USD)
    else:
        handling = max(CAPATAZIA_LCL * wm, CAPATAZIA_LCL_MINIMUM)
        lines = [Line(description='Terminal handling (capatazia), LCL',
                      quantity=Decimal(1), unit_price=handling.quantize(CENT),
                      unit='lot')]
        dollar_fee = ('Desconsolidacao, US$ 200 per B/L', DECONSOLIDATION_USD)
    lines.append(Line(description='B/L release', quantity=Decimal(1),
                      unit_price=BL_RELEASE, unit='lot'))
    lines.append(Line(description=dollar_fee[0], quantity=Decimal(1),
                      unit_price=(dollar_fee[1] * Decimal(fx)).quantize(CENT),
                      unit='lot'))
    return Invoice(number=number or f'{agent.number_prefix}-{day.year}-L{day:%m%d}',
                   issue_date=day, due_date=day + timedelta(days=10),
                   issuer_code=agent.code, lines=lines, kind='local',
                   currency='BRL', reference=shipment_id,
                   shipment_id=shipment_id)


def storage_invoice(day, cif_brl, containers=None, number=None,
                    shipment_id=''):
    """The bonded terminal's first storage period, as a share of the CIF
    value; FCL never under its minimum per container."""
    from business import issuers
    if containers:
        share = Decimal(cif_brl) * STORAGE_FCL
        minimum = sum((STORAGE_MINIMUM[c] for c in containers), Decimal(0))
        amount = max(share, minimum)
        what = f'Armazenagem FCL, 1o periodo de 7 dias, {len(containers)} cntr'
    else:
        amount = Decimal(cif_brl) * STORAGE_LCL
        what = 'Armazenagem LCL, 1o periodo'
    terminal = issuers.TERMINAL
    return Invoice(number=number or f'{terminal.number_prefix}-{day.year}-{day:%m%d}',
                   issue_date=day, due_date=day + timedelta(days=10),
                   issuer_code=terminal.code,
                   lines=[Line(description=what, quantity=Decimal(1),
                               unit_price=amount.quantize(CENT), unit='lot')],
                   kind='storage', currency='BRL', reference=shipment_id,
                   shipment_id=shipment_id,
                   facts=(('Valor CIF', format_amount(Decimal(cif_brl), 'comma')),))


def _carries(line, m3, kg):
    """The main freight line prints the cargo it moves: its kilos and
    cubic metres, in the page's weight and volume columns."""
    line.weight_kg = Decimal(kg).quantize(CENT)
    line.volume_m3 = Decimal(m3).quantize(CENT)


def _invoice(carrier, day, origin, m3, kg, lines, equipment, number):
    booking = f'B/L {carrier.code}{day:%y%m%d}01'
    return Invoice(
        number=number or f'{carrier.number_prefix}-{day.year}-{day:%m%d}',
        issue_date=day,
        due_date=day + timedelta(days=30),
        issuer_code=carrier.code,
        lines=lines,
        kind='freight',
        reference=booking,
        shipment_id=booking,
        shipment={'origin': origin, 'destination': DESTINATION,
                  'container': equipment, 'vessel': 'MV Santos Express',
                  'weight_kg': str(kg), 'volume_m3': str(m3)},
    )
