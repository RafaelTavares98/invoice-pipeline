"""The landed cost of every part, from what the reader filed.

This is the department's report: what each order line cost to land in
Louveira, in reais. It reads the two CSV files the reader writes, plus
the desk's records: the item master, the PTAX table, the dock receipts
and the shipments. It never looks at the answer key.

A goods invoice whose page names no B/L is tied to its shipment by the
dock receipt for its order and part; two equal parts of one order, by
the day the shipment left, which is the invoice's date.

The rules a cost team would use:

- goods and international freight go to reais at the declaration's
  rate, or at the PTAX of the invoice date while the declaration is not
  in yet;
- by sea, freight, the Santos local charges, the truck, the broker and
  AFRMM are split by volume, because a container and shared space are
  charged by the room cargo takes;
- by air, they are split by chargeable weight: a part's kilos or its
  volume weight at 167 kg a cubic metre, whichever is more;
- terminal storage is charged as a share of the CIF value, so it is split
  by value;
- each II line goes to the parts of its NCM, by value; Siscomex by value;
- IPI, PIS, COFINS and ICMS are recoverable for a manufacturer, so they
  are reported as credits beside the cost, never inside it;
- a line is `provisional` until its shipment has goods, international
  freight (none for a CIF price), the local charges, the storage, the
  duty statement and the truck; then it is `final`.
"""

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

ZERO = Decimal('0')
CENT = Decimal('0.01')
UNIT = Decimal('0.0001')

#: Documents that are no longer owed, or are not documents yet.
DROPPED = ('superseded', 'unreadable')

COST_PARTS = ('goods_brl', 'freight_brl', 'local_brl', 'inland_brl',
              'storage_brl', 'broker_brl', 'duty_brl', 'afrmm_brl',
              'siscomex_brl')


def _dec(text):
    try:
        return Decimal(str(text)) if str(text).strip() else ZERO
    except InvalidOperation:
        return ZERO


@dataclass
class Books:
    """What the desk has: the filed documents and two reference tables."""
    invoices: list
    lines: list
    items: dict = field(default_factory=dict)     # code -> {unit_weight_g, unit_m3, ncm}
    issuers: dict = field(default_factory=dict)   # printed name -> code
    ptax: dict = field(default_factory=dict)      # date -> BRL per USD
    #: What the dock signed for: order, part, shipment, quantity. It ties
    #: goods whose page names no B/L to the shipment they came on.
    receipts: list = field(default_factory=list)
    #: When each shipment left, from the desk's shipments record. A goods
    #: invoice is dated the day its box left, which tells two equal parts
    #: of one order apart.
    departures: dict = field(default_factory=dict)

    def rate_on(self, day):
        known = [d for d in self.ptax if d <= day]
        return self.ptax[max(known)] if known else None


def _live(books):
    return [row for row in books.invoices if row['status'] not in DROPPED]


def _lines_by_doc(books):
    found = {}
    for line in books.lines:
        found.setdefault(line['sha256'], []).append(line)
    return found


def _by_shipment(books):
    found = {}
    lines = _lines_by_doc(books)
    received = {}
    for receipt in books.receipts:
        key = (receipt['order_number'], receipt['code'])
        received.setdefault(key, []).append(receipt)
    for row in _live(books):
        shipment = row.get('shipment_id') or _received_on(
            received, row, lines, books.departures)
        if shipment:
            found.setdefault(shipment, []).append(row)
    return found


def _received_on(received, row, lines, departures=None):
    """The shipment the dock received a goods invoice's parts from, when
    the page names none: the receipt for the same order, part and
    quantity, or failing the quantity, the one shipment that order's part
    came on. Two equal parts of one order are told apart by the day the
    shipment left, which is the invoice's date. Nothing is guessed when
    the records still disagree."""
    if row.get('kind') not in ('goods', 'credit') or not received:
        return ''
    order = row.get('order_number', '')
    found = None
    for line in lines.get(row['sha256'], []):
        if not line.get('code'):
            continue
        same = received.get((order, line['code']), [])
        exact = [r for r in same
                 if _dec(r['quantity']) == abs(_dec(line['quantity']))]
        candidates = {r['shipment_id'] for r in exact or same}
        found = candidates if found is None else found & candidates
    if not found:
        return ''
    if len(found) > 1 and departures and row.get('issue_date'):
        from datetime import date
        issued = date.fromisoformat(row['issue_date'])
        found = {s for s in found if departures.get(s) == issued} or found
    return found.pop() if len(found) == 1 else ''


class _Shipment:
    """Everything filed against one shipment, summed by kind."""

    def __init__(self, books, docs, lines):
        from datetime import date
        self.docs = docs
        self.goods = [d for d in docs if d['kind'] in ('goods', 'credit')]
        self.freight = [d for d in docs if d['kind'] == 'freight'
                        and d['currency'] == 'USD']
        inland = [d for d in docs if d['kind'] == 'freight'
                  and d['currency'] == 'BRL']
        broker = [d for d in docs if d['kind'] == 'broker']
        statements = [d for d in docs if d['kind'] == 'customs']

        self.freight_usd = sum((_dec(d['grand_total']) for d in self.freight), ZERO)
        self.by_air = any(d.get('container') == 'LOOSE' for d in self.freight)
        self.inland = sum((_dec(d['grand_total']) for d in inland), ZERO)
        self.broker = sum((_dec(d['grand_total']) for d in broker), ZERO)
        self.local = sum((_dec(d['grand_total']) for d in docs
                          if d['kind'] == 'local'), ZERO)
        self.storage = sum((_dec(d['grand_total']) for d in docs
                            if d['kind'] == 'storage'), ZERO)
        self.duty, self.credits = {}, {}
        self.afrmm = self.siscomex = self.icms = ZERO
        for statement in statements:
            for line in lines.get(statement['sha256'], []):
                self._tax(line)
        self.declared = next((_dec(d['fx_rate']) for d in statements
                              if _dec(d['fx_rate'])), None)
        issued = [date.fromisoformat(d['issue_date']) for d in self.goods
                  if d.get('issue_date')]
        self.ptax = books.rate_on(max(issued)) if issued else None
        self.fx = self.declared or self.ptax
        self.fx_source = 'declaration' if self.declared else 'ptax'
        #: A CIF price carries the ocean freight, so no freight invoice
        #: comes; everything else must be filed for the cost to be final.
        self.cif = any(str(d.get('incoterm', '')).upper().startswith('CIF')
                       for d in self.goods)
        local = [d for d in docs if d['kind'] == 'local']
        storage = [d for d in docs if d['kind'] == 'storage']
        self.complete = bool(self.goods and (self.freight or self.cif)
                             and statements and inland and local and storage)

    def _tax(self, line):
        name, net = line['description'], _dec(line['net'])
        tax, _, ncm = name.partition(' ')
        if tax == 'II':
            self.duty[ncm] = self.duty.get(ncm, ZERO) + net
        elif tax in ('IPI', 'PIS-Importacao', 'COFINS-Importacao'):
            self.credits[ncm] = self.credits.get(ncm, ZERO) + net
        elif name == 'AFRMM':
            self.afrmm += net
        elif name == 'Taxa Siscomex':
            self.siscomex += net
        elif name.startswith('ICMS'):
            self.icms += net


def _goods_lines(shipment, lines, items):
    """Every coded line on the shipment, its service lines and discount
    spread over it by value, so the lines add up to what was billed."""
    found = []
    for doc in shipment.goods:
        coded = [l for l in lines.get(doc['sha256'], []) if l['code']]
        counted = sum((_dec(l['net']) for l in coded), ZERO)
        if not counted:
            continue
        factor = _dec(doc['grand_total']) / counted
        for line in coded:
            item = items.get(line['code'], {})
            quantity = _dec(line['quantity'])
            found.append({
                'order_number': doc.get('order_number', ''),
                'code': line['code'],
                'ncm': item.get('ncm', ''),
                'quantity': quantity,
                'usd': _dec(line['net']) * factor,
                'kg': quantity * _dec(item.get('unit_weight_g', 0)) / 1000,
                'm3': quantity * _dec(item.get('unit_m3', 0)),
            })
    return found


#: Volume weight by air: kilos per cubic metre, the IATA 1 to 6,000 rule.
AIR_KG_PER_M3 = Decimal('167')


def _room(line, by_air):
    """What a part is charged on: its chargeable kilos by air, its cubic
    metres by sea. With no volume in the item master, its kilos."""
    if by_air:
        return max(line['kg'], line['m3'] * AIR_KG_PER_M3)
    return line['m3'] or line['kg']


def _share(part, whole):
    return part / whole if whole else ZERO


def cost(books):
    """One row per order line and part on each shipment, in reais."""
    lines = _lines_by_doc(books)
    rows = []
    for shipment_id, docs in sorted(_by_shipment(books).items()):
        shipment = _Shipment(books, docs, lines)
        found = _merge(_goods_lines(shipment, lines, books.items))
        if not found or shipment.fx is None:
            continue
        fx = shipment.fx
        by_air = shipment.by_air
        room = sum((_room(g, by_air) for g in found), ZERO)
        brl = sum((g['usd'] for g in found), ZERO) * fx
        by_ncm = {}
        for g in found:
            by_ncm[g['ncm']] = by_ncm.get(g['ncm'], ZERO) + g['usd']
        for g in found:
            weight = _share(_room(g, by_air), room)
            value = _share(g['usd'] * fx, brl)
            in_ncm = _share(g['usd'], by_ncm[g['ncm']])
            row = {
                'shipment_id': shipment_id,
                'order_number': g['order_number'],
                'code': g['code'],
                'ncm': g['ncm'],
                'quantity': g['quantity'],
                'fx': fx,
                'fx_source': shipment.fx_source,
                'goods_brl': g['usd'] * fx,
                'freight_brl': shipment.freight_usd * fx * weight,
                'local_brl': shipment.local * weight,
                'inland_brl': shipment.inland * weight,
                'storage_brl': shipment.storage * value,
                'broker_brl': shipment.broker * weight,
                'duty_brl': shipment.duty.get(g['ncm'], ZERO) * in_ncm,
                'afrmm_brl': shipment.afrmm * weight,
                'siscomex_brl': shipment.siscomex * value,
                'credits_brl': (shipment.credits.get(g['ncm'], ZERO) * in_ncm
                                + shipment.icms * value),
                'status': 'final' if shipment.complete else 'provisional',
            }
            rows.append(row)
    return [_rounded(row) for row in rows]


def _merge(found):
    """One row per order and part: a credit note nets against its line."""
    merged = {}
    for g in found:
        key = (g['order_number'], g['code'])
        if key in merged:
            held = merged[key]
            for name in ('quantity', 'usd', 'kg'):
                held[name] += g[name]
        else:
            merged[key] = dict(g)
    return [g for g in merged.values() if g['quantity']]


def _rounded(row):
    for name in COST_PARTS + ('credits_brl',):
        row[name] = row[name].quantize(CENT)
    row['landed_brl'] = sum((row[name] for name in COST_PARTS), ZERO)
    row['unit_landed_brl'] = (row['landed_brl'] / row['quantity']).quantize(UNIT)
    return row


def operations(books):
    """One row per shipment: the operation, its carrier and its costs."""
    lines = _lines_by_doc(books)
    found = []
    for shipment_id, docs in sorted(_by_shipment(books).items()):
        shipment = _Shipment(books, docs, lines)
        main = shipment.freight[0] if shipment.freight else {}
        fx = shipment.fx or ZERO
        weight = _dec(main.get('gross_weight_kg', ''))
        freight_brl = shipment.freight_usd * fx
        issued = sorted(d['issue_date'] for d in shipment.goods
                        if d.get('issue_date'))
        found.append({
            'shipment_id': shipment_id,
            'month': issued[0][:7] if issued else '',
            'mode': _mode(main),
            'origin': main.get('origin', ''),
            'carrier': books.issuers.get(main.get('issuer', ''), main.get('issuer', '')),
            'container': main.get('container', ''),
            'gross_weight_kg': weight,
            'freight_usd': shipment.freight_usd,
            'fx': fx,
            'freight_brl': freight_brl.quantize(CENT),
            'freight_per_kg_brl': (freight_brl / weight).quantize(UNIT) if weight else '',
            'local_brl': shipment.local,
            'inland_brl': shipment.inland,
            'storage_brl': shipment.storage,
            'broker_brl': shipment.broker,
            'duty_brl': (sum(shipment.duty.values(), ZERO) + shipment.afrmm
                         + shipment.siscomex),
            'status': 'final' if shipment.complete else 'provisional',
        })
    return found


def _mode(freight):
    """How the shipment travelled, read off its freight invoice: air, LCL
    or FCL. With no freight invoice, the price was CIF: the factory paid
    the freight inside the goods."""
    if not freight:
        return 'CIF'
    container = freight.get('container', '')
    return {'LOOSE': 'air', 'LCL': 'LCL'}.get(container, 'FCL')


# --------------------------------------------------------------- the files


def _read(path):
    if not Path(path).exists():
        return []
    with open(path, encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def load(data, erp):
    """The reader's two CSV files and the desk's records, as Books."""
    from datetime import date
    items = {row['code']: {'unit_weight_g': _dec(row['unit_weight_g']),
                           'unit_m3': _dec(row.get('unit_m3', '')),
                           'ncm': row['ncm']}
             for row in _read(Path(erp) / 'items.csv')}
    issuers = {row['name']: row['code']
               for row in _read(Path(erp) / 'vendors.csv')}
    ptax = {date.fromisoformat(row['day']): _dec(row['brl_per_usd'])
            for row in _read(Path(erp) / 'ptax.csv')}
    departures = {row['identifier']: date.fromisoformat(row['departed_on'])
                  for row in _read(Path(erp) / 'shipments.csv')
                  if row.get('departed_on')}
    return Books(_read(Path(data) / 'invoices.csv'),
                 _read(Path(data) / 'invoice_lines.csv'), items, issuers, ptax,
                 _read(Path(erp) / 'receipts.csv'), departures)


def write(books, folder):
    """The department's report, in folder: landed_cost.csv,
    operations.csv, exceptions.csv and kpis.json."""
    import json
    from costing import kpis
    from simulation.erp import write_rows
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    lines = cost(books)
    shipments = operations(books)
    groups = _by_shipment(books)
    # The months are the shipments' goods months, so a date OCR misread
    # on one page never opens a month of its own.
    months = sorted({op['month'] for op in shipments if op['month']})
    summary = {
        'analysed_same_day': kpis.analysed_same_day(books.invoices),
        'our_error_rate': kpis.our_error_rate(books.invoices),
        'known_before_close': {
            month: kpis.known_before_close(lines, groups,
                                           int(month[:4]), int(month[5:]))
            for month in months},
    }
    (folder / 'kpis.json').write_text(json.dumps(summary, indent=2,
                                                 default=str),
                                      encoding='utf-8')
    return [write_rows(folder / 'landed_cost.csv', lines),
            write_rows(folder / 'operations.csv', shipments),
            write_rows(folder / 'exceptions.csv', kpis.exceptions(books.invoices)
                       or [{'invoice_number': '', 'origin': '', 'reason': ''}])]
