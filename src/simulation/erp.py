"""What the payables desk holds besides the invoices.

Three-way match, the core control of accounts payable, checks an invoice
against the purchase order and the goods receipt. The vendor master says
who may be paid and into which account. The rate card says what freight
should cost. A model needs the same records, so a run writes them out as
plain CSV files, one per table.

Nothing here carries an answer. The labels live in labels.py.
"""

import csv
from datetime import date
from pathlib import Path

from business import catalogue, issuers, tariffs
from simulation import anomalies, customs, lookalikes

#: Every vendor on file before the period opens was onboarded long ago.
LONG_AGO = date(2019, 1, 1)

TABLES = ('vendors', 'vendor_changes', 'purchase_orders', 'po_lines',
          'contracts', 'receipts', 'shipments', 'rate_card',
          'approval_policy', 'items', 'tariffs', 'ptax')


def tables(operation, as_of=None):
    """Every table, as lists of plain rows. Given a day, only what the desk
    could have had on that day: later rows go, and a shipment still at sea
    has no arrival date yet."""
    found = _all_tables(operation)
    if as_of is None:
        return found
    for rows in found.values():
        for row in rows:
            if 'arrived_on' in row and row['arrived_on'] > as_of:
                row['arrived_on'] = ''
    return {name: [row for row in rows if _known_by(row, as_of)]
            for name, rows in found.items()}


def _known_by(row, day):
    return all(value <= day for value in row.values()
               if isinstance(value, date))


def _all_tables(operation):
    return {
        'vendors': _vendors(operation),
        'vendor_changes': [dict(c) for c in operation.vendor_changes],
        'purchase_orders': [
            {'number': o.number, 'vendor': o.factory_code,
             'raised_on': o.raised_on, 'required_by': o.required_by,
             'value': o.value}
            for o in operation.orders],
        'po_lines': [
            {'order_number': o.number, 'code': l.code,
             'description': l.description, 'quantity': l.quantity,
             'agreed_price': l.agreed_price}
            for o in operation.orders for l in o.lines],
        'contracts': _contracts(operation),
        'receipts': [dict(r) for r in operation.receipts],
        'shipments': [
            {'identifier': s.identifier, 'vendor': s.factory_code,
             'carrier': s.carrier_code, 'mode': s.mode, 'origin': s.origin,
             'destination': s.destination, 'container': s.container,
             'weight_kg': s.weight_kg, 'volume_m3': s.volume_m3,
             'departed_on': s.departed_on, 'arrived_on': s.arrived_on}
            for s in operation.shipments],
        'rate_card': _rate_card(),
        'approval_policy': [
            {'limit': str(anomalies.APPROVAL_LIMIT),
             'approver': 'Purchasing coordinator'},
            {'limit': 'above', 'approver': 'Finance director, second signature'},
        ],
        'items': [
            {'code': part.code, 'description': part.description,
             'unit_weight_g': part.grams, 'unit_m3': part.unit_m3,
             'units_per_carton': part.carton.units,
             'carton_cm': ' x '.join(str(side) for side in part.carton.cm),
             'carton_kg': part.carton.kg, 'carton_source': part.carton.source,
             'hs_code': part.hs_code, 'ncm': tariffs.ncm_for(part.hs_code)}
            for part in catalogue.CATALOGUE],
        'tariffs': [
            {'ncm': rate.ncm, 'ii': rate.ii, 'ipi': rate.ipi,
             'pis': tariffs.PIS, 'cofins': rate.cofins,
             'effective_on': rate.effective_on, 'source': rate.source}
            for rate in list(tariffs.RATES) + list(operation.tariff_changes)],
        'ptax': [{'day': day, 'brl_per_usd': rate,
                  'source': 'simulated PTAX series'}
                 for day, rate in sorted(operation._fx.items())],
    }


def _vendors(operation):
    joined = {v['code']: v['onboarded_on'] for v in operation.joined}
    known = (list(issuers.ALL_ISSUERS)
             + (list(issuers.BRAZIL) + [issuers.TERMINAL]
                if operation.profile.brazil else [])
             + [issuers.by_code(c) for c in joined])
    return [
        {'code': i.code, 'name': i.name, 'country': i.country, 'kind': i.kind,
         'onboarded_on': joined.get(i.code, LONG_AGO),
         'bank_account': i.bank_line, 'email': issuers.address_for(i),
         'terms': i.terms}
        for i in known]


def _contracts(operation):
    """Version 1 is the price on the order; an amendment is version 2."""
    rows = [{'order_number': o.number, 'code': l.code, 'version': 1,
             'price': l.agreed_price, 'effective_on': o.raised_on}
            for o in operation.orders for l in o.lines]
    rows += [{'order_number': a['order_number'], 'code': a['code'],
              'version': 2, 'price': a['price'],
              'effective_on': a['effective_on']}
             for a in operation.amendments]
    return rows


def _rate(kind, issuer, mode, basis, description, amount):
    return {'kind': kind, 'issuer': issuer, 'mode': mode, 'basis': basis,
            'description': description, 'amount': str(amount)}


def _rate_card():
    """Every agreed charge: the freight by load, the Santos local charges,
    the terminal's storage, the truck, the broker's fees, and the
    surcharges and fixed fees the honest twins rely on."""
    from simulation import freight
    rows = []
    for line in ('MRK', 'CSM'):
        rows += [_rate('freight', line, 'FCL', 'container',
                       f'Ocean freight, {size}', amount)
                 for size, amount in freight.FCL_RATE.items()]
    rows += [_rate('freight', 'DHI', 'LCL', 'W/M', 'LCL ocean freight',
                   freight.LCL_RATE),
             _rate('freight', 'DHI', 'air', 'kg', 'Air freight, chargeable kg',
                   freight.AIR_RATE),
             _rate('freight', 'KNG', 'road', 'trip',
                   'Road haulage, in the runs without Brazil', '1420.00')]
    for agent in ('MRK', 'CSM', 'DHI'):
        rows += [_rate('local charge', agent, 'FCL', 'container',
                       'Terminal handling (capatazia)', freight.CAPATAZIA_FCL),
                 _rate('local charge', agent, 'FCL', 'B/L',
                       'Siscarga, US$ per B/L', freight.SISCARGA_USD),
                 _rate('local charge', agent, 'LCL', 'W/M',
                       'Terminal handling (capatazia), minimum '
                       f'{freight.CAPATAZIA_LCL_MINIMUM}', freight.CAPATAZIA_LCL),
                 _rate('local charge', agent, 'LCL', 'B/L',
                       'Desconsolidacao, US$ per B/L',
                       freight.DECONSOLIDATION_USD),
                 _rate('local charge', agent, 'all', 'B/L', 'B/L release',
                       freight.BL_RELEASE)]
    terminal = issuers.TERMINAL.code
    rows += [_rate('storage', terminal, 'FCL', 'CIF %',
                   'First 7 days, with a minimum per container',
                   freight.STORAGE_FCL),
             _rate('storage', terminal, 'LCL', 'CIF %', 'First period',
                   freight.STORAGE_LCL)]
    rows += [_rate('storage', terminal, 'FCL', 'container',
                   f'Minimum, {size}', amount)
             for size, amount in freight.STORAGE_MINIMUM.items()]
    rows += [_rate('surcharge', c.code, c.mode, 'lot', name, 'per tariff')
             for c in issuers.CARRIERS for name in c.surcharges]
    rows += [_rate('surcharge', 'any', '', 'lot', s['description'], s['basis'])
             for s in lookalikes.ALLOWED_SURCHARGES]
    rows += [_rate('fixed_fee', f['issuer'], '', 'lot', f['description'],
                   f['amount']) for f in lookalikes.FIXED_FEES]
    trucker = issuers.TRUCKER
    rows += [_rate('freight', trucker.code, 'FCL', 'container',
                   'Road haulage Santos to Louveira', f'{customs.TRUCK_PER_TRIP:.2f}'),
             _rate('freight', trucker.code, 'part load', 'trip',
                   'Road haulage Santos to Louveira, part load',
                   f'{customs.VAN_PER_TRIP:.2f}')]
    rows += [_rate('surcharge', trucker.code, '', 'lot', name, 'per tariff')
             for name in trucker.surcharges]
    rows += [_rate('fixed_fee', issuers.BROKER.code, '', 'lot', name, amount)
             for name, amount in customs.FEES.items()]
    low, high = customs.STORAGE_PER_DAY
    rows += [_rate('surcharge', issuers.BROKER.code, '', 'day',
                   'Port storage, per day', f'{low} to {high}')]
    return rows


def write_rows(path, rows):
    rows = [{k: _text(v) for k, v in row.items()} for row in rows]
    columns = list(rows[0]) if rows else ['empty']
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _text(value):
    return value.isoformat() if isinstance(value, date) else str(value)


def export(operation, folder, as_of=None):
    """One CSV per table, in folder; only what was known by as_of."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return [write_rows(folder / f'{name}.csv', rows)
            for name, rows in tables(operation, as_of).items()]
