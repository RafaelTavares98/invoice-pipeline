"""Reading an invoice off the page it was printed on.

This module is told nothing about who issued the document. It is given a
PDF and has to work out, from the text alone, which labels the issuer used,
which way round the dates are, and which mark is the decimal point.

That is the honest version of the job. A client does not hand over the
layout file their supplier printed with.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

MONEY = re.compile(r'-?\d[\d.,]*')
ISO_DATE = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')
SLASH_DATE = re.compile(r'\b(\d{2})/(\d{2})/(\d{4})\b')

NUMBER_LABELS = ('invoice no.', 'invoice #', 'invoice number')
ISSUED_LABELS = ('date of issue', 'invoice date', 'date')
DUE_LABELS = ('payment due', 'due date', 'due')
TOTAL_LABELS = ('total usd', 'balance due', 'amount due', 'total')
SUBTOTAL_LABELS = ('subtotal',)
DISCOUNT_LABELS = ('discount',)

#: A line of the table ends in an amount, and the amount before it is the
#: unit price. Anything shorter than this is prose, not a row.
MIN_ROW_AMOUNTS = 2

#: What a column heading can be called. The table is found by its heading
#: row, the way a person finds it, and never by guessing which lines
#: happen to hold numbers. An address holds numbers too.
HEADING_WORDS = {
    'code': ('part no.', 'item no.', 'code'),
    'description': ('description of goods', 'charge description',
                    'goods description', 'description'),
    'hs_code': ('hs code', 'tariff'),
    'quantity': ('quantity', 'units', 'pieces', 'hours', 'qty'),
    'weight': ('weight kg', 'weight'),
    'volume': ('volume m3', 'volume', 'cbm'),
    'unit_price': ('unit price', 'unit value', 'rate', 'price'),
    'amount': ('amount usd', 'net amount', 'total value', 'amount',
               'charge'),
}

#: The columns that carry a figure. Only these are counted when working
#: out how far the quantity sits from the right hand edge.
NUMERIC_COLUMNS = ('quantity', 'weight', 'volume', 'unit_price', 'amount')


@dataclass
class ReadLine:
    description: str
    quantity: Decimal
    unit_price: Decimal
    net: Decimal


@dataclass
class ReadInvoice:
    source: str
    number: str = ''
    issue_date: object = None
    due_date: object = None
    issuer: str = ''
    subtotal: Decimal = None
    discount: Decimal = None
    grand_total: Decimal = None
    order_number: str = ''
    shipment_id: str = ''
    revises: str = ''
    decimal_mark: str = 'dot'
    date_order: str = 'iso'
    lines: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    @property
    def is_credit(self):
        return self.grand_total is not None and self.grand_total < 0


def read(text, source=''):
    """One invoice, read off the text of its page."""
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    found = ReadInvoice(source=source)

    found.decimal_mark = guess_decimal_mark(rows)
    found.date_order = guess_date_order(rows)
    found.issuer = guess_issuer(rows)

    found.number = _labelled(rows, NUMBER_LABELS) or _number_from_text(rows)
    found.issue_date = _date(_labelled(rows, ISSUED_LABELS), found.date_order)
    found.due_date = _date(_labelled(rows, DUE_LABELS), found.date_order)

    found.subtotal = _amount(_labelled(rows, SUBTOTAL_LABELS), found.decimal_mark)
    found.discount = _amount(_labelled(rows, DISCOUNT_LABELS), found.decimal_mark)
    found.grand_total = _amount(_labelled(rows, TOTAL_LABELS), found.decimal_mark)

    found.order_number = _match(rows, r'\bPO-\d{4,6}\b')
    found.shipment_id = (_match(rows, r'\bB/L\s*[A-Z]{3}\d{6,8}\b')
                         or _match(rows, r'\bAWB\s*\d{3}-\d{8}\b'))
    found.revises = _revises(found.number)

    found.lines = _rows(rows, found.decimal_mark)
    found.problems = _complain(found)
    return found


# ------------------------------------------------------- what the page is


def guess_decimal_mark(rows):
    """A thousands separator sits three digits from the end. A decimal
    mark sits two. Count which character does which."""
    dot = comma = 0
    for row in rows:
        for token in MONEY.findall(row):
            if re.search(r',\d{2}$', token):
                comma += 1
            elif re.search(r'\.\d{2}$', token):
                dot += 1
    return 'comma' if comma > dot else 'dot'


def guess_date_order(rows):
    """Which way round a slashed date is written.

    ISO is unmistakable. Otherwise look at every date on the page, not
    just the first: a number above twelve can only be a day, and one such
    date settles the order for the whole page.

    When every date is ambiguous, `05/12/2026` could be either, and the
    page itself cannot say. The payment terms then decide, because a due
    date comes after an issue date.
    """
    page = '\n'.join(rows)
    if ISO_DATE.search(page):
        return 'iso'

    found = SLASH_DATE.findall(page)
    for first, second, _ in found:
        if int(first) > 12:
            return 'day_first'
        if int(second) > 12:
            return 'month_first'
    return _order_from_the_terms(found)


def _order_from_the_terms(found):
    """Every date was ambiguous. Pick the order that puts them in sequence.

    An invoice is issued before it falls due. Reading the page both ways,
    only one reading keeps that true.
    """
    if len(found) < 2:
        return 'day_first'

    first, second = found[0], found[1]
    as_day = (_safe(first, 'day_first'), _safe(second, 'day_first'))
    as_month = (_safe(first, 'month_first'), _safe(second, 'month_first'))

    day_works = all(as_day) and as_day[0] < as_day[1]
    month_works = all(as_month) and as_month[0] < as_month[1]

    if month_works and not day_works:
        return 'month_first'
    return 'day_first'


def _safe(parts, date_order):
    first, second, year = (int(part) for part in parts)
    day, month = ((second, first) if date_order == 'month_first'
                  else (first, second))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def guess_issuer(rows):
    """The issuer prints its own name under FROM, before anybody else's."""
    for index, row in enumerate(rows):
        if row.strip().upper().startswith('FROM'):
            tail = row.strip()[4:].strip()
            if tail:
                return tail
            if index + 1 < len(rows):
                return rows[index + 1].strip()
    return rows[0].strip() if rows else ''


# ----------------------------------------------------------- the pieces


def _labelled(rows, labels):
    """The text printed after a label, on its line or the next one."""
    for label in labels:
        for index, row in enumerate(rows):
            lowered = row.lower()
            at = lowered.find(label)
            if at < 0:
                continue
            tail = row[at + len(label):].strip(' :\t')
            if tail:
                return tail
            if index + 1 < len(rows):
                return rows[index + 1].strip()
    return ''


def _match(rows, pattern):
    found = re.search(pattern, '\n'.join(rows))
    return found.group(0).strip() if found else ''


def _number_from_text(rows):
    return _match(rows, r'\b[A-Z]{3}-\d{4}-\d{3,5}(?:-R\d)?\b')


def _revises(number):
    """A number ending `-R1` is a correction of the number without it.

    Suppliers announce a revision in the number itself. Missing that
    leaves two live documents claiming the same money.
    """
    found = re.match(r'^(.*)-R\d+$', number or '')
    return found.group(1) if found else ''


def _amount(text, decimal_mark):
    if not text:
        return None
    token = MONEY.search(text)
    if not token:
        return None
    raw = token.group(0)
    raw = (raw.replace('.', '').replace(',', '.') if decimal_mark == 'comma'
           else raw.replace(',', ''))
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _date(text, date_order):
    if not text:
        return None
    iso = ISO_DATE.search(text)
    if iso:
        return date(*(int(part) for part in iso.groups()))
    slashed = SLASH_DATE.search(text)
    if not slashed:
        return None
    first, second, year = (int(part) for part in slashed.groups())
    day, month = ((second, first) if date_order == 'month_first'
                  else (first, second))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_heading(rows):
    """Which line is the table's heading, and how its columns are ordered.

    Returns the index of that line and how far the quantity column sits
    from the right hand edge, counted in columns.
    """
    for index, row in enumerate(rows):
        hit = {name for _, name in _columns(row)}
        if {'description', 'amount', 'quantity'} <= hit:
            return index, _quantity_offset(row)
    return None, None


def _quantity_offset(heading):
    """How many figures stand between the quantity and the right edge.

    A goods table reads part, description, HS code, qty, price, amount:
    two figures after the quantity. A freight table puts weight and
    volume in between, so there are four. Counting only three columns,
    rather than every column that carries a figure, reads the volume as
    the quantity.
    """
    ordered = [name for _, name in sorted(_columns(heading))
               if name in NUMERIC_COLUMNS]
    if 'quantity' not in ordered or 'amount' not in ordered:
        return None
    return ordered.index('amount') - ordered.index('quantity')


def _columns(heading):
    """Where each known column heading sits on the line."""
    lowered = heading.lower()
    taken = []
    places = []
    for name, words in HEADING_WORDS.items():
        for word in words:
            at = lowered.find(word)
            if at < 0 or any(at < end and at + len(word) > begin
                             for begin, end in taken):
                continue
            taken.append((at, at + len(word)))
            places.append((at, name))
            break
    return places


def _rows(rows, decimal_mark):
    """Every line of the table, taken from under its heading.

    The table starts at the heading and ends at the first totals label,
    or at the first line that is plainly not a row. A table is one
    unbroken block, so once prose resumes the table is over. Without that
    rule a bank account number further down the page reads as a price.
    """
    start, offset = find_heading(rows)
    if start is None:
        return []

    found = []
    for row in rows[start + 1:]:
        lowered = row.lower()
        if any(lowered.startswith(label) for label in
               TOTAL_LABELS + SUBTOTAL_LABELS + DISCOUNT_LABELS):
            break
        amounts = [_amount(token, decimal_mark) for token in MONEY.findall(row)]
        amounts = [value for value in amounts if value is not None]
        if len(amounts) < MIN_ROW_AMOUNTS:
            if found:
                break
            continue

        net, unit_price = amounts[-1], amounts[-2]
        quantity = _quantity(amounts, offset, net, unit_price)
        description = _description(row)
        if not description:
            continue
        found.append(ReadLine(description, quantity, unit_price, net))
    return found


def _quantity(amounts, offset, net, unit_price):
    """Read the quantity where the heading says it is.

    A surcharge row leaves the weight and volume cells empty, so the
    count runs short. Then the quantity is whatever the amount divided by
    the price must have been.
    """
    if offset is not None and len(amounts) > offset:
        return amounts[-(offset + 1)]
    if unit_price:
        return Decimal(f'{net / unit_price:.2f}').normalize()
    return Decimal(1)


def _description(row):
    """The words of the row, with the figures taken out.

    Only the trailing figures go. A description that holds a number of
    its own, like a 24/410 neck or a 30 ml pipette, keeps it.
    """
    text = re.sub(r'(\s+-?\d[\d.,]*)+\s*$', '', row).strip(' .,|')
    return text or MONEY.sub('', row).strip(' .,|')


def _complain(found):
    """Say what is missing. A field the page did not give is left empty
    and reported, never invented."""
    problems = []
    if not found.number:
        problems.append('no invoice number')
    if found.issue_date is None:
        problems.append('no issue date')
    if found.grand_total is None:
        problems.append('no total')
    if not found.lines:
        problems.append('no table rows')
    if found.subtotal is not None and found.lines:
        counted = sum(line.net for line in found.lines)
        if abs(counted - found.subtotal) > Decimal('0.05'):
            problems.append(
                f'lines add to {counted}, page says subtotal {found.subtotal}')
    return problems
