"""The department's operational targets, from what the reader filed.

- invoices analysed the day they arrive, in Brasilia time;
- our errors: what the reader could not read or close, so a person must;
- the share of a month's landed cost known before the month is closed.

Client errors, the supplier's and the carrier's, come from the anomaly
model in project 02, never from here.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

BRT = timezone(timedelta(hours=-3))
CLOSE_BUSINESS_DAY = 6
ONE = Decimal('0.1')


def close_day(year, month):
    """The 6th business day of the month after; holidays are left out."""
    day = date(year + month // 12, month % 12 + 1, 1)
    counted = 0
    while True:
        if day.weekday() < 5:
            counted += 1
            if counted == CLOSE_BUSINESS_DAY:
                return day
        day += timedelta(days=1)


def _local(text):
    return datetime.fromisoformat(text).astimezone(BRT)


def _percent(part, whole):
    if not whole:
        return None
    return (Decimal(part * 100) / Decimal(whole)).quantize(ONE)


def analysed_same_day(rows):
    """The share registered on the Brasilia day it arrived."""
    timed = [r for r in rows if r.get('first_seen') and r.get('registered_at')]
    same = sum(_local(r['registered_at']).date() == _local(r['first_seen']).date()
               for r in timed)
    return _percent(same, len(timed))


def exceptions(rows):
    """Every filed row a person must look at, and whose error it is."""
    found = []
    for r in rows:
        if r['status'] == 'unreadable':
            found.append({'invoice_number': r['invoice_number'],
                          'origin': 'ours', 'reason': 'unreadable'})
        elif r.get('problems'):
            found.append({'invoice_number': r['invoice_number'],
                          'origin': 'ours', 'reason': r['problems']})
    return found


def our_error_rate(rows):
    return _percent(len(exceptions(rows)), len(rows))


def known_before_close(cost, groups, year, month):
    """The share of the month's landed cost whose every document was
    registered by the month's close. `groups` is each shipment's filed
    documents, as the cost report tied them. The month is the goods'."""
    close = close_day(year, month)
    last_in, month_of = {}, {}
    for shipment, docs in groups.items():
        registered = [_local(d['registered_at']).date() for d in docs
                      if d.get('registered_at')]
        if registered:
            last_in[shipment] = max(registered)
        issued = sorted(d['issue_date'] for d in docs
                        if d.get('kind') == 'goods' and d.get('issue_date'))
        if issued:
            first = date.fromisoformat(issued[0])
            month_of[shipment] = (first.year, first.month)
    whole = known = Decimal(0)
    for line in cost:
        shipment = line['shipment_id']
        if month_of.get(shipment) != (year, month):
            continue
        whole += line['landed_brl']
        if shipment in last_in and last_in[shipment] <= close:
            known += line['landed_brl']
    return _percent(known, whole) if whole else None
