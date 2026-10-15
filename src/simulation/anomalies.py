"""Errors a model should learn to catch later.

The defects in defects.py are honest mistakes the reader must survive.
These are different: an invoice that bills more than was agreed, more
than was ordered, twice under two numbers, or a suspiciously round sum.
Each is named on the invoice, and so in the answer key.

The rates follow the sources in docs/reference.md: about 1.5% of
payments are duplicate or erroneous (APQC), and 5 to 10% of freight
invoices carry an error (Tompkins Ventures).
"""

import copy
import math
from datetime import timedelta
from decimal import Decimal

#: The chance of each anomaly, per invoice of the kind it applies to.
RATES = {
    'price_drift': 0.010,        # goods: a unit price above the agreed one
    'quantity_over': 0.008,      # goods: more billed than was shipped
    'round_total': 0.004,        # goods: an adjustment to a round sum
    'near_duplicate': 0.005,     # any: billed again under a new number
    'freight_overbill': 0.07,    # freight: a charge nobody agreed to
    'account_mismatch': 0.002,  # any: an account and a sender not on file
    'split_billing': 0.012,     # goods over the limit: one delivery billed in pieces
}

#: What goes wrong at the customs stage, per declaration or broker bill.
#: Neither can happen anywhere else on the page: only a declaration
#: carries a duty rate, and only the broker bills his own contract.
CUSTOMS_RATES = {
    'duty_rate_wrong': 0.030,   # a duty at a rate the NCM does not carry
    'broker_fee_over': 0.040,   # a service charged above the contract
}

#: Every anomaly. An unmatched vendor is a vendor-master entry, not a
#: dice roll per invoice, so the operation schedules it.
KINDS = tuple(RATES) + ('unmatched_vendor',) + tuple(CUSTOMS_RATES)

#: How far a wrong duty rate sits from the published one. A rate ten
#: times over is a typing slip anybody sees; these are the wrong line of
#: the table, or last year's, and they get paid.
DUTY_SLIP = (Decimal('0.02'), Decimal('0.10'))

#: How far a broker fee goes over its contract. A fee at ten times the
#: card is caught by the first person to look; a third over is not.
FEE_OVER = (Decimal('0.15'), Decimal('0.60'))

#: Above this, an invoice needs a second approver. One delivery billed in
#: pieces under it skips that check by mistake.
APPROVAL_LIMIT = Decimal('25000.00')

#: Vendors entered in the master with no order behind them, per year.
UNMATCHED_PER_YEAR = 2.5

#: How an overbilled freight invoice labels its extra charge.
OVERBILL = 'Additional handling'

_GOODS_ONLY = ('price_drift', 'quantity_over', 'round_total', 'split_billing')

#: What the drift profile multiplies, once the second half begins.
DRIFTING = ('freight_overbill', 'account_mismatch')


def duty_slip(rng):
    """A rate the declaration will be built with, or None.

    The wrong rate has to go in while the statement is drawn: the IPI
    base and the ICMS are both built from the duty, so a rate painted on
    afterwards leaves a page that does not add up, and arithmetic alone
    would catch it. The point is to catch it against the tariff table.
    """
    if rng.random() >= CUSTOMS_RATES['duty_rate_wrong']:
        return None
    spoiled = {}

    def rate_for(ncm, published):
        if not spoiled:
            spoiled[ncm] = wrong_duty_rate(rng, ncm, None, published)
        return spoiled.get(ncm, published)

    return rate_for


def at_customs(rng, invoice):
    """Maybe bill one broker service above its contract.

    The broker's own fees are the one thing on his bill that has a
    contract price, so this is the only line that can go wrong this way.
    """
    from simulation import customs

    fees = [line for line in invoice.lines
            if line.description in customs.FEES]
    if fees and rng.random() < CUSTOMS_RATES['broker_fee_over']:
        line = rng.choice(fees)
        line.unit_price = broker_fee_over(rng, line.unit_price)
        invoice.anomaly = 'broker_fee_over'


def wrong_duty_rate(rng, description, base, published):
    """A duty rate a few points off the one the NCM carries.

    The broker's tariff table was not refreshed, or the clerk read the
    line above. The base and the description are passed so the slip can
    be scaled to the line later; today it only needs the rate.
    """
    low, high = DUTY_SLIP
    away = _cents(Decimal(str(rng.uniform(float(low), float(high)))))
    if published - away < 0 or rng.random() < 0.5:
        return published + away
    return published - away


def broker_fee_over(rng, agreed):
    """A broker service billed above its contract price."""
    low, high = FEE_OVER
    over = Decimal(str(rng.uniform(float(low), float(high))))
    return _cents(agreed * (1 + over))


def _cents(value):
    return Decimal(value).quantize(Decimal('0.01'))


def _price_drift(rng, invoice):
    line = rng.choice([l for l in invoice.lines if l.code] or invoice.lines)
    raised = line.unit_price * Decimal(f'{rng.uniform(1.04, 1.15):.4f}')
    line.unit_price = raised.quantize(line.unit_price)


def _quantity_over(rng, invoice):
    line = rng.choice([l for l in invoice.lines if l.code] or invoice.lines)
    line.quantity = Decimal(math.ceil(float(line.quantity)
                                      * rng.uniform(1.10, 1.30)))


def _round_total(invoice, service):
    total = invoice.grand_total
    gap = _cents(math.ceil(total / 1000) * 1000) - total
    if gap <= 0:
        gap = Decimal('1000.00')
    invoice.lines.append(service('Adjustment, as agreed', gap))


def _freight_overbill(rng, invoice, service):
    main = invoice.lines[0].net
    invoice.lines.append(service(
        f'{OVERBILL}, terminal', _cents(float(main) * rng.uniform(0.04, 0.12))))


def _near_duplicate(rng, invoice, issuer, next_number):
    """The same bill under a new number, a few days later. The bytes
    differ, so the reader's hash cannot see it."""
    twin = copy.deepcopy(invoice)
    twin.issue_date = invoice.issue_date + timedelta(days=rng.randint(1, 4))
    twin.number = next_number(issuer, twin.issue_date)
    twin.anomaly = 'near_duplicate'
    #: The original must stay as it is from here on. A revision would
    #: change the total the duplicate repeats, and leave a duplicate of
    #: nothing.
    invoice.billed_again = True
    return twin


def other_account(rng):
    """An account at a bank the issuer never used."""
    bank = rng.choice(('Wise Europe SA  IBAN BE71 9670 ',
                       'Revolut Bank UAB  IBAN LT60 3250 ',
                       'Metropolitan Commercial  Acct 0'))
    return bank + ' '.join(f'{rng.randint(0, 9999):04d}' for _ in range(3))


def _account_mismatch(rng, invoice, issuer):
    from business import issuers
    invoice.pay_to = other_account(rng)
    invoice.sender = issuers.other_address(issuer)


def _eligible_split(invoice):
    return APPROVAL_LIMIT < invoice.grand_total < 3 * APPROVAL_LIMIT


def _split(rng, invoice, issuer, next_number):
    """Bill one delivery in pieces that each sit under the approval limit.

    The sum is the true amount: nothing is overbilled, but the second
    approval the whole bill needed never happens. Returns the extra
    pieces, or None if the cut came out uneven."""
    pieces = math.ceil(invoice.grand_total / (APPROVAL_LIMIT * Decimal('0.97')))
    copies = [copy.deepcopy(invoice) for _ in range(pieces)]
    for index, line in enumerate(invoice.lines):
        whole = int(line.quantity)
        if not line.code or whole < pieces:
            for number, piece in enumerate(copies):
                if number:
                    piece.lines[index].quantity = Decimal(0)
            continue
        share, rest = divmod(whole, pieces)
        for number, piece in enumerate(copies):
            piece.lines[index].quantity = Decimal(share + (rest if not number else 0))
    for number, piece in enumerate(copies):
        piece.lines = [l for l in piece.lines if l.quantity]
        if number:
            piece.discount = Decimal('0.00')
    if any(not p.lines or p.grand_total <= 0 or p.grand_total >= APPROVAL_LIMIT
           for p in copies):
        return None
    invoice.lines = copies[0].lines
    invoice.anomaly = 'split_billing'
    extras = []
    for piece in copies[1:]:
        piece.issue_date = invoice.issue_date + timedelta(days=rng.randint(0, 4))
        piece.number = next_number(issuer, piece.issue_date)
        piece.anomaly = 'split_billing'
        extras.append(piece)
    return extras


def apply(rng, invoice, issuer, next_number, service, boost=1.0):
    """Maybe give this invoice one anomaly. Returns any extra invoice it
    creates, such as a near duplicate. `boost` multiplies the drifting
    kinds, for the drift scenario."""
    # A declaration and a broker's bill have their own errors, planted
    # at the customs stage. Letting the general ones in as well would
    # put two marks on one page.
    if invoice.kind in ('credit', 'customs', 'broker'):
        return []
    for name, chance in RATES.items():
        if name in _GOODS_ONLY and invoice.kind != 'goods':
            continue
        if name == 'freight_overbill' and invoice.kind != 'freight':
            continue
        if name == 'account_mismatch' and not issuer.bank_line:
            continue
        if name == 'split_billing' and not _eligible_split(invoice):
            continue
        if name in DRIFTING:
            chance *= boost
        if rng.random() >= chance:
            continue
        if name == 'near_duplicate':
            return [_near_duplicate(rng, invoice, issuer, next_number)]
        if name == 'split_billing':
            extras = _split(rng, invoice, issuer, next_number)
            if extras is None:
                continue
            return extras
        invoice.anomaly = name
        if name == 'account_mismatch':
            _account_mismatch(rng, invoice, issuer)
            return []
        if name == 'price_drift':
            _price_drift(rng, invoice)
        elif name == 'quantity_over':
            _quantity_over(rng, invoice)
        elif name == 'round_total':
            _round_total(invoice, service)
        else:
            _freight_overbill(rng, invoice, service)
        return []
    return []
