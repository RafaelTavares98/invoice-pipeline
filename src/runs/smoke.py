"""The smoke tests of docs/tutorial.md, one function per step.

Everything a smoke test makes is invented and lands in
Invoices/samples/<step>/, apart from the real run.
"""

import json
import shutil
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from business import issuers
from drawing import render, scan
from mail import delivery
from simulation import freight as charges

#: The day the smoke invoices are dated: in the past, never after today.
DAY = date(2026, 5, 4)

#: Step 1's two cargoes: one that fills a 40', one that shares a box.
FCL_CARGO = (Decimal('58.4'), Decimal('9850'))
LCL_CARGO = (Decimal('6.8'), Decimal('1240'))

SUBJECT = 'Smoke test 1: an FCL and an LCL freight invoice'


def _samples(base):
    return Path(base) / 'Invoices' / 'samples'


def home_for(base, step):
    """The step's own folder among the samples, emptied for a fresh run."""
    home = _samples(base) / step
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    return home


def freight(base, send=False):
    """Step 1: one mail with an FCL and an LCL freight invoice."""
    home = home_for(base, 'freight')
    fcl = charges.fcl_invoice(issuers.by_code('MRK'), DAY, 'Ningbo', *FCL_CARGO)
    lcl = charges.lcl_invoice(issuers.by_code('DHI'), DAY, 'Ningbo', *LCL_CARGO)
    drawn = [render.draw(home, bill) for bill in (fcl, lcl)]
    pdfs = [pdf for pdf, _ in drawn]
    (home / 'truth.json').write_text(json.dumps(
        [bill.as_truth() | {'file': pdf.name, 'scan': scanned}
         for bill, (pdf, scanned) in zip((fcl, lcl), drawn)], indent=2),
        encoding='utf-8')
    _post(home, [('freight', 'Invoice pipeline smoke test', 'smoke', SUBJECT,
                  _body(fcl, lcl), pdfs)], send)
    return home


# ------------------------------------------------------------ step 2


#: The day's dollar rate for the Brazilian documents of step 2.
FX = Decimal('5.40')


class _Numbers:
    """Fresh invoice numbers, one counter per issuer."""

    def __init__(self, start=7001):
        self.start = start
        self.next = {}

    def __call__(self, issuer, day):
        count = self.next.get(issuer.code, self.start)
        self.next[issuer.code] = count + 1
        return f'{issuer.number_prefix}-{day.year}-{count}'


def _service(description, amount):
    from business.invoice import Line
    return Line(description=description, quantity=Decimal(1),
                unit_price=amount, unit='lot')


def _goods(factory, seed, number):
    from simulation import builder
    invoice = builder.goods_invoice(factory, seed=seed)
    invoice.number = number(factory, invoice.issue_date)
    return invoice


def _scaled(invoice, target):
    """The same invoice with its coded lines scaled to about target."""
    import math
    factor = float(target) / float(invoice.subtotal)
    for line in invoice.lines:
        if line.code:
            line.quantity = Decimal(max(1, math.ceil(float(line.quantity) * factor)))
    return invoice


def _factories(rng, number):
    """Each factory's documents, with the goods-stage errors and twins."""
    import copy
    from types import SimpleNamespace
    from simulation import anomalies, builder, lookalikes, newcomers

    by = issuers.by_code
    found = []

    drift = _goods(by('NCL'), 11, number)
    anomalies._price_drift(rng, drift)
    drift.anomaly = 'price_drift'
    rise = _goods(by('NCL'), 12, number)
    lookalikes.price_rise(rng, rise, SimpleNamespace(
        number=rise.reference, raised_on=rise.issue_date - timedelta(days=60)))
    found += [('NCL', drift, 'a price above the contract'),
              ('NCL', rise, 'a price rise under a signed amendment')]

    over = _goods(by('SBP'), 21, number)
    anomalies._quantity_over(rng, over)
    over.anomaly = 'quantity_over'
    accepted = _goods(by('SBP'), 22, number)
    lookalikes.accepted_over_delivery(rng, accepted)
    found += [('SBP', over, 'more billed than the dock received'),
              ('SBP', accepted, 'an over-delivery the dock accepted')]

    rounded = _goods(by('GZV'), 31, number)
    anomalies._round_total(rounded, _service)
    rounded.anomaly = 'round_total'
    # The quote takes its own number; the template it copies takes none.
    quote = lookalikes.tooling_quote(rng, builder.goods_invoice(by('GZV'), seed=32),
                                     by('GZV'), number, _service)
    found += [('GZV', rounded, 'an adjustment to a round total'),
              ('GZV', quote, 'a fixed tooling quote')]

    found.append(('HCV', _goods(by('HCV'), 41, number),
                  'a goods invoice, CIF Santos'))

    whole = _scaled(_goods(by('BDT'), 51, number), Decimal('48000'))
    pieces = anomalies._split(rng, whole, by('BDT'), number)
    found.append(('BDT', whole, 'one delivery billed in pieces, part 1'))
    found += [('BDT', piece, f'one delivery billed in pieces, part {n}')
              for n, piece in enumerate(pieces, start=2)]
    first = _scaled(_goods(by('BDT'), 52, number), Decimal('16000'))
    first.order_number, first.shipment_id = 'PO-46102', 'B/L MRK26050411'
    first.lookalike_of = 'split_billing'
    second = copy.deepcopy(first)
    second.number = number(by('BDT'), second.issue_date)
    second.shipment_id = 'B/L CSM26050412'
    found += [('BDT', first, 'an order shipped in parts, first shipment'),
              ('BDT', second, 'an order shipped in parts, second shipment')]

    other = _goods(by('ARL'), 61, number)
    anomalies._account_mismatch(rng, other, by('ARL'))
    other.anomaly = 'account_mismatch'
    changed = _goods(by('ARL'), 62, number)
    changed.pay_to = newcomers._account(rng)
    changed.lookalike_of = 'account_mismatch'
    found += [('ARL', other, 'an account and sender not on file'),
              ('ARL', changed, 'a bank change confirmed by call-back')]
    return found


def _carriers(rng, number):
    """Freight by mode, local charges, the road haul and its twins."""
    from business.invoice import Invoice, Line
    from simulation import anomalies, lookalikes

    by = issuers.by_code
    found = []

    plain = charges.fcl_invoice(by('MRK'), DAY, 'Ningbo', *FCL_CARGO,
                                number=number(by('MRK'), DAY))
    overbilled = charges.fcl_invoice(by('MRK'), DAY, 'Shanghai',
                                     Decimal('62.0'), Decimal('11200'),
                                     number=number(by('MRK'), DAY))
    anomalies._freight_overbill(rng, overbilled, _service)
    overbilled.anomaly = 'freight_overbill'
    allowed = charges.fcl_invoice(by('MRK'), DAY, 'Busan', Decimal('70.0'),
                                  Decimal('12400'),
                                  number=number(by('MRK'), DAY))
    lookalikes.allowed_surcharge(rng, allowed, _service)
    local = charges.local_charges(by('MRK'), DAY, containers=['40GP'],
                                  number=number(by('MRK'), DAY))
    found += [('MRK', plain, 'FCL freight, one 40\''),
              ('MRK', overbilled, 'FCL freight with a charge not on the rate card'),
              ('MRK', allowed, 'FCL freight with a surcharge the rate card allows'),
              ('MRK', local, 'local charges in Santos, in reais')]

    box20 = charges.fcl_invoice(by('CSM'), DAY, 'Shantou', Decimal('24.5'),
                                Decimal('6100'), number=number(by('CSM'), DAY))
    found += [('CSM', box20, 'FCL freight, one 20\''),
              ('CSM', charges.local_charges(by('CSM'), DAY, containers=['20GP'],
                                            number=number(by('CSM'), DAY)),
               'local charges in Santos, in reais')]

    lcl = charges.lcl_invoice(by('DHI'), DAY, 'Ningbo', *LCL_CARGO,
                              number=number(by('DHI'), DAY))
    air = charges.air_invoice(by('DHI'), DAY, 'Busan', Decimal('2.0'),
                              Decimal('250'), number=number(by('DHI'), DAY))
    found += [('DHI', lcl, 'LCL freight, per W/M'),
              ('DHI', air, 'air freight, per chargeable kg'),
              ('DHI', charges.local_charges(by('DHI'), DAY, wm=lcl.lines[0].quantity,
                                            number=number(by('DHI'), DAY)),
               'LCL local charges in Santos, in reais')]

    haul = Invoice(number=number(by('KNG'), DAY), issue_date=DAY,
                   due_date=DAY + timedelta(days=21), issuer_code='KNG',
                   kind='freight', reference='B/L MRK26050401',
                   lines=[Line(description='Road haulage Santos to Louveira, 40GP',
                               quantity=Decimal(1), unit_price=Decimal('1420.00'),
                               unit='trip'),
                          _service('Port storage', Decimal('310.00'))])
    again = anomalies._near_duplicate(rng, haul, by('KNG'), number)
    rent = Invoice(number=number(by('KNG'), DAY), issue_date=DAY,
                   due_date=DAY + timedelta(days=15), issuer_code='KNG',
                   kind='freight', reference='Contract KNG-WH-2026, May 2026',
                   lines=[_service(lookalikes.RECURRING['description'],
                                   lookalikes.RECURRING['amount'])],
                   lookalike_of='near_duplicate')
    found += [('KNG', haul, 'road haulage'),
              ('KNG', again, 'the same haul billed again under a new number'),
              ('KNG', rent, 'the monthly warehouse rent, same amount each month')]
    return found


def _brazil(rng, number, goods):
    """The broker, the truck and the terminal, in reais."""
    from business import tariffs
    from business.orders import Shipment
    from simulation import anomalies, customs

    by = issuers.by_code
    ship = Shipment(identifier='B/L MRK26050401', factory_code=goods.issuer_code,
                    carrier_code='MRK', mode='ocean',
                    departed_on=DAY - timedelta(days=38), arrived_on=DAY,
                    origin='Ningbo', destination='Santos', container='40GP',
                    weight_kg=FCL_CARGO[1], volume_m3=FCL_CARGO[0])
    freight_usd = [charges.fcl_invoice(by('MRK'), DAY, 'Ningbo', *FCL_CARGO)]
    ncm = next(iter(customs.goods_by_ncm([goods])))

    def slip(code, published):
        if code != ncm:
            return published
        return anomalies.wrong_duty_rate(rng, code, None, published)

    wrong = customs.statement(rng, ship, [goods], freight_usd, DAY, FX,
                              number(by('SCA'), DAY), duty_rate=slip)
    wrong.anomaly = 'duty_rate_wrong'
    base = tariffs.rate_on(ncm, DAY)
    cut = tariffs.Rate(ncm, base.ii - Decimal('0.02'), base.ipi, base.cofins,
                       DAY - timedelta(days=20), 'simulated Gecex resolution')
    honest = customs.statement(rng, ship, [goods], freight_usd, DAY, FX,
                               number(by('SCA'), DAY), changes=(cut,))
    honest.lookalike_of = 'duty_rate_wrong'

    fee_over = customs.broker_invoice(rng, ship, DAY, number(by('SCA'), DAY))
    fee_over.lines[0].unit_price = anomalies.broker_fee_over(
        rng, fee_over.lines[0].unit_price)
    fee_over.anomaly = 'broker_fee_over'
    amended = customs.broker_invoice(rng, ship, DAY, number(by('SCA'), DAY))
    amended.lines[0].unit_price = (amended.lines[0].unit_price
                                   * Decimal('1.12')).quantize(Decimal('0.01'))
    amended.lines[0].description += ' (amended)'
    amended.lookalike_of = 'broker_fee_over'

    cargo_brl = goods.grand_total * FX
    box = {'origin': 'Santos', 'destination': 'Louveira', 'container': '40GP',
           'weight_kg': str(FCL_CARGO[1]), 'volume_m3': str(FCL_CARGO[0]),
           'vessel': 'Truck'}
    truck = customs.trucker_invoice(rng, ship, DAY, cargo_brl,
                                    number(by('TLV'), DAY), box)
    cif = (goods.grand_total + freight_usd[0].grand_total) * FX
    return [
        ('SCA', wrong, 'a duty statement with a rate the NCM does not carry'),
        ('SCA', honest, 'a duty statement under a published rate cut'),
        ('SCA', fee_over, 'a broker fee above its contract'),
        ('SCA', amended, 'a broker fee the amended contract allows'),
        ('TLV', truck, 'the truck from Santos to Louveira'),
        ('TVA', charges.storage_invoice(DAY, cif, containers=['40GP'],
                                        number=number(issuers.TERMINAL, DAY)),
         'FCL storage, first week'),
        ('TVA', charges.storage_invoice(DAY, LCL_CARGO[0] * Decimal('9000'),
                                        number=number(issuers.TERMINAL, DAY)),
         'LCL storage, first period'),
    ]


def _newcomers(rng, number):
    """The vendor with no order, and the new supplier with one."""
    from business.invoice import Invoice
    from simulation import newcomers

    stranger = newcomers.unmatched(rng, 0)
    bill = Invoice(number=number(stranger, DAY), issue_date=DAY,
                   due_date=DAY + timedelta(days=30), issuer_code=stranger.code,
                   lines=[_service('Supplier audit services', Decimal('6400.00'))],
                   anomaly='unmatched_vendor')
    supplier, template = newcomers.new_supplier(rng, 0)
    goods = _goods(template, 71, number)
    goods.issuer_code = supplier.code
    goods.number = number(supplier, goods.issue_date)
    goods.lookalike_of = 'unmatched_vendor'
    return [(stranger.code, bill, 'services billed with no order behind them',
             'unmatched'),
            (supplier.code, goods, 'goods from a new supplier with an order',
             'supplier')]


def _shows_the_habit(number):
    """Whether the generator makes this number the way its issuer scans:
    a scan, and askew when the issuer lays pages askew."""
    habit = scan.HABITS[number.split('-')[0]]
    return scan.chosen(number) and (scan.askew(number) or not habit.askew)


def _numbered_to_show_habits(documents):
    """A sender that scans has its numbers start where the generator first
    scans one of them its own way, so the scan is one of the flavours. The
    numbers stay in order with no gap; the generator still decides."""
    for code in scan.HABITS:
        mine = [entry[1] for entry in documents if entry[1].issuer_code == code]
        if not mine:
            continue
        prefix, year, first = mine[0].number.rsplit('-', 2)[0], \
            mine[0].number.split('-')[1], int(mine[0].number[-4:])
        start = first
        while not any(_shows_the_habit(f'{prefix}-{year}-{start + n}')
                      for n in range(len(mine))):
            start += 1
        for n, invoice in enumerate(mine):
            invoice.number = f'{prefix}-{year}-{start + n}'


def senders(base, send=False):
    """Step 2: one mail from each sender, every flavour."""
    from business import profiles
    from simulation.pricing import seeded

    home = home_for(base, 'senders')
    rng = seeded(2026)
    number = _Numbers()
    documents = _factories(rng, number) + _carriers(rng, number)
    hcv = next(doc[1] for doc in documents if doc[0] == 'HCV')
    documents += _brazil(rng, number, hcv) + _newcomers(rng, number)
    _numbered_to_show_habits(documents)

    truth, mails = [], {}
    for entry in documents:
        code, invoice, what = entry[:3]
        newcomer = entry[3] if len(entry) > 3 else ''
        issuer = issuers.by_code(invoice.issuer_code)
        pdf, scanned = render.draw(home, invoice, issuer)
        truth.append(invoice.as_truth() | {
            'mail': code, 'file': pdf.name, 'scan': scanned,
            'askew': scan.askew(invoice.number),
            'first_unit': invoice.lines[0].unit})
        mail = mails.setdefault(code, {'issuer': issuer, 'newcomer': newcomer,
                                       'pdfs': [], 'listed': []})
        mail['pdfs'].append(pdf)
        mail['listed'].append((pdf.name, what))
    (home / 'truth.json').write_text(json.dumps(truth, indent=2),
                                     encoding='utf-8')

    _post(home, [(code, mail['issuer'].name, code.lower(),
                  f'Smoke test 2: {mail["issuer"].name}',
                  profiles.describe(mail['issuer'], mail['listed'],
                                    mail['newcomer']),
                  mail['pdfs'])
                 for code, mail in mails.items()], send)
    return home


# ------------------------------------------------------------ step 3


#: The past shipment the broker forwards: it sailed and landed this year.
SAILED = date(2026, 2, 9)
LANDED = date(2026, 3, 16)
LANDED_FX = Decimal('5.3150')

FORWARD_SUBJECT = 'Fwd: Smoke test 3: the file of one past shipment'


def _dossier(rng, number):
    """The ten documents of one past shipment, oldest first."""
    from business.orders import Shipment
    from simulation import builder, customs

    by = issuers.by_code
    booking = f'B/L MRK{SAILED:%y%m%d}01'
    goods = []
    for position in range(4):
        invoice = builder.goods_invoice(by('NCL'), seed=301 + position)
        invoice.issue_date = SAILED - timedelta(days=4 - position)
        invoice.due_date = invoice.issue_date + timedelta(days=by('NCL').lead_days)
        invoice.number = number(by('NCL'), invoice.issue_date)
        invoice.order_number = f'PO-4{6200 + position}'
        invoice.reference = invoice.order_number
        invoice.shipment_id = booking
        invoice.facts = (('Shipment', booking),)
        goods.append(invoice)

    kg = sum((invoice.total_weight_kg for invoice in goods), Decimal(0))
    m3 = (kg / Decimal('180')).quantize(Decimal('0.1'))
    sea = charges.fcl_invoice(by('MRK'), SAILED, 'Ningbo', m3, kg,
                              number=number(by('MRK'), SAILED))
    boxes = charges.containers_for(m3, kg)
    ship = Shipment(identifier=booking, factory_code='NCL', carrier_code='MRK',
                    mode='ocean', departed_on=SAILED, arrived_on=LANDED,
                    origin='Ningbo', destination='Santos',
                    container=' + '.join(boxes), weight_kg=kg, volume_m3=m3)
    cif = ((sum((g.grand_total for g in goods), Decimal(0)) + sea.grand_total)
           * LANDED_FX)
    box = {'origin': 'Santos', 'destination': 'Louveira',
           'container': ship.container, 'weight_kg': str(kg),
           'volume_m3': str(m3), 'vessel': 'Truck'}
    return [(invoice, 'goods invoice') for invoice in goods] + [
        (sea, 'FCL ocean freight'),
        (charges.local_charges(by('MRK'), LANDED, containers=boxes,
                               number=number(by('MRK'), LANDED),
                               shipment_id=booking), 'local charges in Santos'),
        (customs.statement(rng, ship, goods, [sea], LANDED, LANDED_FX,
                           number(by('SCA'), LANDED)), 'duty statement'),
        (customs.broker_invoice(rng, ship, LANDED, number(by('SCA'), LANDED)),
         'broker fees'),
        (charges.storage_invoice(LANDED, cif, containers=boxes,
                                 number=number(issuers.TERMINAL, LANDED),
                                 shipment_id=booking), 'terminal storage'),
        (customs.trucker_invoice(rng, ship, LANDED, cif,
                                 number(by('TLV'), LANDED), box),
         'truck to Louveira'),
    ]


#: Who can forward a shipment's whole file: the broker holds every
#: document of the shipments it clears.
FORWARDERS = ('SCA',)


def forward(base, sender='SCA', send=False):
    """Step 3: one sender forwards the ten PDFs of one past shipment."""
    from simulation.pricing import seeded

    if sender not in FORWARDERS:
        raise ValueError(f'{sender} holds no whole shipment file; '
                         f'only {", ".join(FORWARDERS)} does')
    home = home_for(base, 'forward')
    documents = _dossier(seeded(3), _Numbers(start=3001))
    truth, pdfs, listed = [], [], []
    for invoice, what in documents:
        pdf, scanned = render.draw(home, invoice)
        truth.append(invoice.as_truth() | {'file': pdf.name, 'scan': scanned,
                                           'askew': scan.askew(invoice.number)})
        pdfs.append(pdf)
        listed.append(f'- {pdf.name}: {what}')
    (home / 'truth.json').write_text(json.dumps(truth, indent=2),
                                     encoding='utf-8')
    forwarder = issuers.by_code(sender)
    body = (f'Forwarding the closed file of {documents[0][0].shipment_id}, '
            f'Ningbo to Louveira, landed {LANDED:%d %B %Y}.\n\n'
            + '\n'.join(listed)
            + '\n\nInvented by the invoice pipeline smoke test. Not real data.\n')
    _post(home, [('forward', forwarder.name, sender.lower(), FORWARD_SUBJECT,
                  body, pdfs)], send)
    return home


# ------------------------------------------------------ steps 4 to 6


#: Which subject each sending step's mail carries.
SUBJECTS = {'freight': 'Smoke test 1', 'senders': 'Smoke test 2',
            'forward': 'Smoke test 3'}

#: What the reader may differ on before a page counts as misread.
CHECKED = ('invoice_number', 'grand_total', 'kind', 'currency')


def gmail(step):
    """The project's Gmail inbox, narrowed to one step's mail."""
    from mail import sources, watcher
    account, password = delivery._account()
    return sources.ImapMailbox(watcher.IMAP_HOST, account, password,
                               subject=SUBJECTS[step])


def read(base, step, mailbox=None):
    """Steps 4 to 6: read one sending step's mail into Invoices/samples/
    <step>/data, and score every PDF against that step's answer key."""
    from reading import intake
    home = _samples(base) / step
    data = home / 'data'
    if data.exists():
        shutil.rmtree(data)
    store = intake.Store(data)
    for message in _newest(mailbox or gmail(step)):
        intake.replay(store, message)
    store.save()
    score = _score(store.invoices, _truth(home))
    (home / 'score.json').write_text(json.dumps(score, indent=2),
                                     encoding='utf-8')
    return score


def _newest(mailbox):
    """One mail per subject, the last to arrive: a step sent twice is read
    once."""
    newest = {}
    for message in mailbox.messages():
        held = newest.get(message.subject)
        if held is None or message.received_at >= held.received_at:
            newest[message.subject] = message
    return sorted(newest.values(), key=lambda message: message.received_at)


def _truth(home):
    return json.loads((home / 'truth.json').read_text(encoding='utf-8'))


def _score(rows, truth):
    """Each PDF of the key against the row the reader filed for it.

    Right: every checked field matches. Flagged: something differs and
    the reader said so. Wrong: something differs in silence, the one
    outcome a smoke test must never show. Missing: no row at all."""
    # A superseded row was still read right or wrong; the revision that
    # replaced it is scored under its own file.
    by_file = {row['source']: row for row in rows}
    score = {'pdfs': len(truth), 'right': 0, 'flagged': [], 'wrong': [],
             'missing': []}
    for entry in truth:
        name = entry.get('file') or f'{entry["number"]}.pdf'
        row = by_file.get(name)
        if row is None:
            score['missing'].append(name)
            continue
        key = {'invoice_number': entry['number'],
               'grand_total': entry['grand_total'],
               'kind': entry['kind'], 'currency': entry['currency']}
        differs = [field for field in CHECKED
                   if not _same(row.get(field, ''), key[field])]
        if not differs:
            score['right'] += 1
        elif row.get('problems'):
            score['flagged'].append({'file': name, 'differs': differs,
                                     'problems': row['problems']})
        else:
            score['wrong'].append({'file': name, 'differs': differs,
                                   'read': {f: str(row.get(f, '')) for f in differs},
                                   'key': {f: key[f] for f in differs}})
    return score


def _same(read_value, key_value):
    try:
        return Decimal(str(read_value)) == Decimal(str(key_value))
    except ArithmeticError:
        return str(read_value) == str(key_value)


# ------------------------------------------------------------ step 7


def cost(base, data=None):
    """Step 7: the forwarded shipment, read back in step 6, becomes the
    landed cost of each part, in Invoices/samples/cost."""
    from costing import landed
    data = Path(data) if data else (_samples(base)
                                    / 'forward' / 'data')
    home = home_for(base, 'cost')
    books = landed.Books(landed._read(data / 'invoices.csv'),
                         landed._read(data / 'invoice_lines.csv'),
                         items=_item_master())
    landed.write(books, home)
    rows = landed.cost(books)
    check = {'parts_total': sum((row['landed_brl'] for row in rows), Decimal(0)),
             'documents_total': _documents_total(books, rows)}
    (home / 'check.json').write_text(json.dumps(check, indent=2, default=str),
                                     encoding='utf-8')
    return check | {'folder': home, 'rows': rows}


def _item_master():
    """The desk's item master: each part's weight, room and NCM."""
    from business import catalogue, tariffs
    return {part.code: {'unit_weight_g': Decimal(str(part.grams)),
                        'unit_m3': part.unit_m3,
                        'ncm': tariffs.ncm_for(part.hs_code)}
            for part in catalogue.CATALOGUE}


def _documents_total(books, rows):
    """What the costed shipments' documents bill, in reais, counted
    straight off the filed rows: dollars at the declaration's rate, the
    reais documents as billed, and the duty lines that are a cost."""
    costed = {row['shipment_id'] for row in rows}
    fx = {row['shipment_id']: row['fx'] for row in rows}
    total = Decimal(0)
    for doc in books.invoices:
        if doc['status'] in ('superseded', 'unreadable') \
                or doc.get('shipment_id') not in costed:
            continue
        if doc['kind'] == 'customs':
            for line in books.lines:
                if line['sha256'] == doc['sha256'] and (
                        line['description'].startswith('II ')
                        or line['description'] in ('AFRMM', 'Taxa Siscomex')):
                    total += Decimal(line['net'])
        elif doc['currency'] == 'USD':
            total += Decimal(doc['grand_total']) * fx[doc['shipment_id']]
        else:
            total += Decimal(doc['grand_total'])
    return total.quantize(Decimal('0.01'))


def _post(home, mails, send):
    """Write each mail into home/outbox and, when asked, send it. A mail
    file is written whole and then renamed, so a reader watching the
    folder never opens half of one."""
    import time
    from email.utils import formatdate
    if send:
        account, recipient = delivery.account_and_recipient()
    else:
        account, recipient = 'local@example.invalid', 'costs@moty.example'
    outbox = home / 'outbox'
    outbox.mkdir(exist_ok=True)
    for position, (stem, name, tag, subject, body, pdfs) in enumerate(mails):
        built = delivery.build_mail(name, tag, account, recipient, subject,
                                    body, pdfs)
        built['Date'] = formatdate(localtime=True)
        partial = outbox / f'{stem}.part'
        partial.write_bytes(built.as_bytes())
        partial.replace(outbox / f'{stem}.eml')
        if send:
            if position:
                time.sleep(1.2)
            delivery.send_mail(built)


def _body(fcl, lcl):
    return (
        'Two freight invoices, Ningbo to Santos.\n\n'
        f'FCL, {fcl.number}: {fcl.shipment["volume_m3"]} m3 and '
        f'{fcl.shipment["weight_kg"]} kg in one {fcl.shipment["container"]}, '
        f'US$ {fcl.grand_total}.\n'
        f'LCL, {lcl.number}: {lcl.shipment["volume_m3"]} m3 and '
        f'{lcl.shipment["weight_kg"]} kg, {lcl.lines[0].quantity} W/M at '
        f'US$ {lcl.lines[0].unit_price}, US$ {lcl.grand_total}.\n\n'
        'Invented by the invoice pipeline smoke test. Not real data.\n'
    )
