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

NUMBER_LABELS = ('invoice no.', 'invoice #', 'invoice number',
                 'statement no.')
ISSUED_LABELS = ('date of issue', 'invoice date', 'registered', 'date')
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
    'quantity': ('quantity', 'units', 'pieces', 'hours', 'qty', 'base'),
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
    #: The part number and HS code of a goods line, and the weight of a
    #: freight line. Empty when the page has no such column.
    code: str = ''
    hs_code: str = ''
    weight_kg: Decimal = None


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
    bank_account: str = ''
    #: What the document is: goods, freight, customs, broker or credit.
    kind: str = ''
    currency: str = ''
    #: The shipment strip of a freight invoice.
    origin: str = ''
    destination: str = ''
    container: str = ''
    gross_weight_kg: Decimal = None
    vessel: str = ''
    #: The terms of a goods invoice: CIF means the freight is in the price.
    incoterm: str = ''
    #: The rate and the customs value printed on a duty statement.
    fx_rate: Decimal = None
    customs_value: Decimal = None
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
    found.bank_account = _bank_account(rows)
    found.currency = _currency(rows)
    found.incoterm = _labelled(rows, ('incoterm',))
    printed_rate = _labelled(rows, ('fx rate',))
    found.fx_rate = _rate(printed_rate)
    found.customs_value = _amount(_labelled(rows, ('customs value',)),
                                  found.decimal_mark)
    _shipment_strip(rows, found)

    found.lines = _named_taxes(_rows(rows, found.decimal_mark))
    found.kind = _kind(rows, found)
    found.problems = _complain(found)
    if printed_rate and found.fx_rate is None:
        found.problems.append(f'FX rate "{printed_rate}" is not a rate with '
                              f'four decimals; check by hand')
    return found


#: A rate is printed with four decimals, after a comma or a dot.
RATE = re.compile(r'\b(\d{1,3})[.,](\d{4})\b')


def _rate(text):
    """The FX rate as printed, 5,3408 or 5.3408. A figure without its four
    decimals is not taken: read as 3408, it would cost the goods a
    thousandfold."""
    found = RATE.search(text or '')
    return Decimal(f'{found.group(1)}.{found.group(2)}') if found else None


#: The taxes a duty statement charges on each NCM, always in this order.
TAX_ORDER = ('II', 'IPI', 'PIS-Importacao', 'COFINS-Importacao')

NCM_ANYWHERE = re.compile(r'\b(\d{4})[.:](\d{2})[.:](\d{2})\b')


def _tax_named(token):
    """The tax a garbled name stands for, when the letters still say."""
    word = token.upper().translate(str.maketrans('!1L|', 'IIII'))
    if word == 'II':
        return 'II'
    for prefix, name in (('IP', 'IPI'), ('PIS', 'PIS-Importacao'),
                         ('COF', 'COFINS-Importacao')):
        if word.startswith(prefix):
            return name
    return ''


def _named_taxes(lines):
    """Each tax line of a duty statement named cleanly, "II 3923.30.00".
    OCR garbles the names, "ON" or "I!" for II; where the letters no
    longer say, the line's place among its NCM's four lines does."""
    ncm, place = '', -1
    for line in lines:
        code = NCM_ANYWHERE.search(line.description)
        if not code:
            continue
        found = '.'.join(code.groups())
        place = place + 1 if found == ncm else 0
        ncm = found
        name = _tax_named(line.description.split()[0]) or (
            TAX_ORDER[place] if place < len(TAX_ORDER) else '')
        if name:
            line.description = f'{name} {ncm}'
    return lines


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


def _bank_account(rows):
    """The account to pay into: the one row that names an IBAN or an
    account number."""
    for row in rows:
        if re.search(r'\b(IBAN|Acct)\b', row):
            return row.strip()
    return ''


#: The footer every page prints under its totals.
FOOTERS = {'united states dollars': 'USD', 'brazilian reais': 'BRL'}


def _currency(rows):
    """The labelled currency; on a scan that lost the label, the footer,
    then the code printed beside the total."""
    found = re.match(r'[A-Z]{3}\b', _labelled(rows, ('currency',)))
    if found:
        return found.group(0)
    page = '\n'.join(rows).lower()
    for words, code in FOOTERS.items():
        if words in page:
            return code
    found = re.search(r'\btotal\s+(USD|BRL)\b', '\n'.join(rows), re.IGNORECASE)
    return found.group(1).upper() if found else ''


#: The title each kind of document prints, as the page shows it.
TITLES = (('import duty statement', 'customs'), ('service invoice', 'broker'),
          ('freight invoice', 'freight'), ('local charges', 'local'),
          ('storage invoice', 'storage'))


#: Taxes only a duty statement charges. OCR can lose a title, but not
#: every one of these lines with it.
DUTY_LINES = ('pis-importacao', 'cofins-importacao', 'afrmm', 'taxa siscomex')


def _kind(rows, found):
    page = '\n'.join(rows).lower()
    if found.grand_total is not None and found.grand_total < 0:
        return 'credit'
    for title, kind in TITLES:
        if title in page:
            return kind
    if 'statement no' in page or any(tax in page for tax in DUTY_LINES):
        return 'customs'
    return 'goods'


#: The equipment a shipment travels in. It is the one token the strip
#: always carries, so the words either side of it can be told apart.
EQUIPMENT = re.compile(r'^(20GP|40GP|40HC|LOOSE|LCL)$')


def _shipment_strip(rows, found):
    """The strip under the parties: origin, destination, equipment,
    vessel, gross weight and volume, labels on one line and values on the
    next. The port names can hold two words, so the line is split around
    the equipment code rather than by position."""
    for index, row in enumerate(rows[:-1]):
        upper = row.upper()
        if 'ORIGIN' not in upper or 'DESTINATION' not in upper:
            continue
        tokens = rows[index + 1].split()
        at = next((i for i, token in enumerate(tokens)
                   if EQUIPMENT.match(token)), None)
        if at is None or at < 2 or len(tokens) < at + 3:
            return
        found.origin = ' '.join(tokens[:at - 1])
        found.destination = tokens[at - 1]
        # A booking of several boxes prints them joined: 40HC + 20GP.
        end = at + 1
        while end + 1 < len(tokens) and tokens[end] == '+' \
                and EQUIPMENT.match(tokens[end + 1]):
            end += 2
        found.container = ' '.join(tokens[at:end])
        found.vessel = ' '.join(tokens[end:-2])
        try:
            found.gross_weight_kg = Decimal(tokens[-2].replace(',', ''))
        except InvalidOperation:
            found.gross_weight_kg = None
        return


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
        # OCR can garble one heading word, QTY read as "ary"; the table is
        # still found by its description, its amount and one more figure.
        if {'description', 'amount'} <= hit and hit & {'quantity',
                                                       'unit_price'}:
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
    columns = [name for _, name in sorted(_columns(rows[start]))]
    numeric = [name for name in columns if name in NUMERIC_COLUMNS]

    found = []
    for row in rows[start + 1:]:
        row = _with_ii(row)
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
        description = _with_ncm(row, description)
        line = ReadLine(description, quantity, unit_price, net)
        _cost_fields(line, row, description, columns, numeric, decimal_mark)
        found.append(line)
    return found


NCM = re.compile(r'^\d{4}\.\d{2}\.\d{2}$')


#: What OCR makes of the two capital I's of II, the import duty, when an
#: NCM follows: "|| 8424.89.90", "ll 3923.10.90", "IL 7010.90.22".
II_SLIP = re.compile(r'^\s*(?:\|\||ll|IL|Il|lI|1I|I1|11|\|I|I\||l\||\|l)'
                     r'(?=\s+\d{4}[.:]\d{2}[.:]\d{2}\b)')


def _with_ii(row):
    """The row with an OCR slip of II put back. II is the one tax that is
    a cost; lost to a slip, it would vanish from the landed cost."""
    return II_SLIP.sub('II', row)


def _with_ncm(row, description):
    # A tax line names the NCM it is charged on, right after the tax:
    # "II 3923.50.00". It looks like a figure and would be stripped with
    # the base and the amount, but it is part of what the line is.
    tail = MONEY.findall(row[len(description):])
    if tail and NCM.match(tail[0]):
        return f'{description} {tail[0]}'
    return description


PART = re.compile(r'^([A-Z]{2}-[A-Z0-9]{3,5})\b')
HS = re.compile(r'^\d{4}\.\d{2}(?:\.\d{2})?$')


def _cost_fields(line, row, description, columns, numeric, decimal_mark):
    """The part, HS code and weight, read from where the heading puts
    them. The figures after the description are counted from the left: a
    full goods row holds the HS code then the numeric columns; a full
    freight row holds every numeric column. A surcharge row is short, so
    it has no weight, which is right."""
    tail = MONEY.findall(row[len(description):])
    if 'code' in columns:
        part = PART.match(description)
        line.code = part.group(1) if part else ''
    if 'hs_code' in columns and len(tail) == len(numeric) + 1 \
            and HS.match(tail[0]):
        line.hs_code = tail[0]
    if 'weight' in numeric and len(tail) == len(numeric):
        line.weight_kg = _amount(tail[numeric.index('weight')], decimal_mark)


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
    if found.subtotal is not None and found.grand_total is not None:
        expected = found.subtotal - abs(found.discount or Decimal(0))
        if abs(expected - found.grand_total) > Decimal('0.05'):
            problems.append(f'total {found.grand_total} is not the subtotal '
                            f'less the discount, {expected}')
    elif found.grand_total is not None and found.lines:
        # No subtotal read: the lines themselves must make the total.
        counted = sum(line.net for line in found.lines) \
            - abs(found.discount or Decimal(0))
        if abs(counted - found.grand_total) > Decimal('0.05'):
            problems.append(f'lines make {counted}, page says total '
                            f'{found.grand_total}')
    return problems
