"""Honest invoices that look like an error.

Every anomaly in anomalies.py has a twin here: an invoice that looks the
same on the page and is legitimate. What tells them apart is a record the
business keeps: a contract amendment, a goods receipt, the rate card, the
vendor master. A model that reads only the invoice will flag both, and a
payables desk would drown in false alarms.

Each twin is named in `lookalike_of`, so a model is scored on how many of
them it wrongly flags.
"""

import copy
import math
from datetime import timedelta
from decimal import Decimal

#: The chance of each twin, per invoice of the kind it applies to. Twins
#: that are business events of their own, such as a new supplier or a
#: bank change, are scheduled by the operation instead.
RATES = {
    'price_drift': 0.010,        # goods: a price rise under an amendment
    'quantity_over': 0.008,      # goods: an over-delivery accepted at the dock
    'round_total': 0.004,        # goods: a fixed tooling quote, billed alone
    'freight_overbill': 0.07,    # freight: a surcharge the rate card allows
}

#: The honest version of each customs error, per declaration or broker
#: bill. A rate really does change and a contract really is amended; a
#: model that cannot tell those from the errors cries wolf at every
#: import.
CUSTOMS_RATES = {
    'duty_rate_wrong': 0.030,   # a rate published before the declaration
    'broker_fee_over': 0.040,   # a fee the amended contract allows
}

#: How much an amended broker contract raises a fee.
FEE_AMENDMENT = (Decimal('0.05'), Decimal('0.20'))

#: Surcharges a carrier may add because the rate card says so.
ALLOWED_SURCHARGES = (
    {'description': 'Peak season surcharge', 'basis': '4 to 12% of freight'},
    {'description': 'Equipment imbalance surcharge', 'basis': '4 to 12% of freight'},
)

#: A storage bill that repeats on a schedule, always the same amount.
RECURRING = {'issuer': 'KNG',
             'description': 'Bonded warehouse rental, monthly',
             'amount': Decimal('2000.00')}
RECURRING_DAYS = 28

#: Quotes a factory bills on their own, at a fixed round price.
TOOLING = 'Mould tooling, fixed quote'
TOOLING_PRICES = (Decimal('3000.00'), Decimal('5000.00'), Decimal('8000.00'))


def at_customs(rng, invoice, changes=()):
    """Maybe make one line honestly different from the usual.

    A declaration whose NCM had a published rate change carries the new
    rate, and that is not an error. A broker fee rises when the contract
    is amended, and the line says so.
    """
    from simulation import customs

    duties = [line for line in invoice.lines
              if line.description.startswith('II ')]
    changed = {change.ncm for change in changes
               if change.effective_on <= invoice.issue_date}
    eligible = [line for line in duties
                if line.description.split()[-1] in changed]
    if eligible and rng.random() < CUSTOMS_RATES['duty_rate_wrong']:
        invoice.lookalike_of = 'duty_rate_wrong'
        return

    fees = [line for line in invoice.lines
            if line.description in customs.FEES]
    if fees and rng.random() < CUSTOMS_RATES['broker_fee_over']:
        line = rng.choice(fees)
        low, high = FEE_AMENDMENT
        over = Decimal(str(rng.uniform(float(low), float(high))))
        line.unit_price = (line.unit_price * (1 + over)).quantize(
            Decimal('0.01'))
        line.description = f'{line.description} (amended)'
        invoice.lookalike_of = 'broker_fee_over'


def _fixed_fees():
    from business import issuers
    fees = [dict(RECURRING)]
    for factory in issuers.FACTORIES:
        for price in TOOLING_PRICES:
            fees.append({'issuer': factory.code, 'description': TOOLING,
                         'amount': price})
    return fees


#: Every fixed fee on the rate card.
FIXED_FEES = _fixed_fees()


def price_rise(rng, invoice, order):
    """A price raised by an amendment signed before the invoice.

    Returns the amendment, for the contracts table."""
    line = rng.choice([l for l in invoice.lines if l.code])
    raised = line.unit_price * Decimal(f'{rng.uniform(1.04, 1.15):.4f}')
    line.unit_price = raised.quantize(line.unit_price)
    lead = (invoice.issue_date - order.raised_on).days
    effective = invoice.issue_date - timedelta(days=rng.randint(0, max(0, lead)))
    invoice.lookalike_of = 'price_drift'
    return {'order_number': order.number, 'code': line.code,
            'price': line.unit_price, 'effective_on': effective}


def accepted_over_delivery(rng, invoice):
    """The factory shipped more, the dock took it, the invoice bills it.

    Returns the extra quantity by part code, for the goods receipt."""
    line = rng.choice([l for l in invoice.lines if l.code])
    line.quantity = Decimal(math.ceil(float(line.quantity)
                                      * rng.uniform(1.10, 1.30)))
    invoice.lookalike_of = 'quantity_over'
    return {line.code: line.quantity}


def allowed_surcharge(rng, invoice, service):
    main = invoice.lines[0].net
    name = rng.choice(ALLOWED_SURCHARGES)['description']
    invoice.lines.append(service(
        name, Decimal(f'{float(main) * rng.uniform(0.04, 0.12):.2f}')))
    invoice.lookalike_of = 'freight_overbill'


def tooling_quote(rng, invoice, issuer, next_number, service):
    """A fixed quote for a mould, billed on its own: a round total."""
    quote = copy.deepcopy(invoice)
    quote.number = next_number(issuer, invoice.issue_date)
    quote.lines = [service(TOOLING, rng.choice(TOOLING_PRICES))]
    quote.discount = Decimal('0.00')
    quote.lookalike_of = 'round_total'
    quote.anomaly = ''
    return quote


def apply(rng, invoice, order, issuer, next_number, service):
    """Maybe make this invoice a twin. Returns (extra invoices, records),
    where records name what the business wrote down to make it honest."""
    if invoice.kind in ('credit', 'customs') or invoice.anomaly:
        return [], {}
    for name, chance in RATES.items():
        goods = name != 'freight_overbill'
        if goods and (invoice.kind != 'goods' or order is None):
            continue
        if not goods and invoice.kind != 'freight':
            continue
        if rng.random() >= chance:
            continue
        if name == 'price_drift':
            return [], {'amendment': price_rise(rng, invoice, order)}
        if name == 'quantity_over':
            return [], {'received': accepted_over_delivery(rng, invoice)}
        if name == 'round_total':
            return [tooling_quote(rng, invoice, issuer, next_number,
                                  service)], {}
        allowed_surcharge(rng, invoice, service)
        return [], {}
    return [], {}
