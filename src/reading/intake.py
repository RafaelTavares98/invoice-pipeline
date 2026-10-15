"""From a mailbox to two CSV files, once per document and never twice.

What identifies a document is not its number. A supplier that resends the
same invoice sends the same number, and a supplier that corrects one keeps
the number and changes the figures. The thing that is actually unique is
the PDF itself, so the key here is the hash of its bytes.

Three questions decide what happens to an arriving file:

    hash already seen            -> skip, it is a resend
    number seen, hash is new     -> the old row becomes superseded
    neither                      -> a new row

Nothing is ever dropped. A file that cannot be read gets a row saying so,
because a line the pipeline hides is a line nobody learns about.
"""

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from reading import fields, ocr

INVOICES_CSV = 'invoices.csv'
LINES_CSV = 'invoice_lines.csv'
STATE_FILE = 'state.json'

INVOICE_COLUMNS = (
    'invoice_number', 'status', 'revises', 'issuer', 'issue_date', 'due_date',
    'subtotal', 'discount', 'grand_total', 'order_number', 'shipment_id',
    'line_count', 'decimal_mark', 'date_order', 'source', 'sha256',
    'first_seen', 'problems', 'read_by', 'bank_account', 'sender',
    'kind', 'currency', 'origin', 'destination', 'container',
    'gross_weight_kg', 'vessel', 'fx_rate', 'customs_value', 'registered_at',
    'incoterm',
)

LINE_COLUMNS = (
    'invoice_number', 'sha256', 'row', 'description', 'quantity',
    'unit_price', 'net', 'code', 'hs_code', 'weight_kg',
)


@dataclass
class Outcome:
    """What one arriving file did to the store."""
    status: str
    invoice_number: str
    digest: str
    problems: list = field(default_factory=list)


class Store:
    """The two CSV files and the small note of what has been seen."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.invoices = _read_csv(self.folder / INVOICES_CSV)
        self.lines = _read_csv(self.folder / LINES_CSV)
        self.state = _read_json(self.folder / STATE_FILE,
                                {'last_uid': 0, 'seen': []})
        #: The same hashes as a set: a list check walks every entry.
        self.seen = set(self.state['seen'])

    # --------------------------------------------------------- the three

    def take(self, payload, source, received_at, sender='',
             registered_at=None):
        """Put one PDF through the three questions. `sender` is the From
        of the mail it came in, kept because a wrong account is invisible
        without it. `registered_at` is when the row was written; a live
        run passes its own clock, a real one leaves it to the wall clock."""
        registered_at = registered_at or _now()
        digest = hashlib.sha256(payload).hexdigest()
        if digest in self.seen:
            return Outcome('duplicate', self._number_of(digest), digest)

        found, failure, read_by = _read_pdf(payload, source)
        if not failure:
            _not_after_arrival(found, received_at)
        if failure:
            self._remember(digest)
            self._add_row(_unreadable_row(source, digest, received_at, failure)
                          | {'registered_at': registered_at})
            return Outcome('unreadable', '', digest, [failure])

        status = 'new'
        if found.revises and self._has_number(found.revises):
            # The number itself announces the correction: INV-9 -R1.
            self._supersede(found.revises)
            status = 'revised'
        elif found.number and self._has_number(found.number):
            # Same number, new bytes, no announcement. Still a correction.
            self._supersede(found.number)
            status = 'revised'

        self._remember(digest)
        self._add_row(_invoice_row(found, status, digest, received_at,
                                   read_by) | {'sender': sender,
                                               'registered_at': registered_at})
        self._add_lines(found, digest)
        return Outcome(status, found.number, digest, found.problems)

    # ------------------------------------------------------------ saving

    def save(self):
        _write_csv(self.folder / INVOICES_CSV, INVOICE_COLUMNS, self.invoices)
        _write_csv(self.folder / LINES_CSV, LINE_COLUMNS, self.lines)
        _write_json(self.folder / STATE_FILE, self.state)
        return self.folder

    # ---------------------------------------------------------- plumbing

    def _remember(self, digest):
        self.state['seen'].append(digest)
        self.seen.add(digest)

    def _has_number(self, number):
        return any(row['invoice_number'] == number and row['status'] != 'superseded'
                   for row in self.invoices)

    def _supersede(self, number):
        for row in self.invoices:
            if row['invoice_number'] == number:
                row['status'] = 'superseded'

    def _number_of(self, digest):
        for row in self.invoices:
            if row['sha256'] == digest:
                return row['invoice_number']
        return ''

    def _add_row(self, row):
        self.invoices.append(row)

    def _add_lines(self, found, digest):
        for position, line in enumerate(found.lines, start=1):
            self.lines.append({
                'invoice_number': found.number,
                'sha256': digest,
                'row': position,
                'description': line.description,
                'quantity': line.quantity,
                'unit_price': line.unit_price,
                'net': line.net,
                'code': line.code,
                'hs_code': line.hs_code,
                'weight_kg': line.weight_kg if line.weight_kg is not None else '',
            })


# ------------------------------------------------------------ the rows


def _invoice_row(found, status, digest, received_at, read_by='text'):
    return {
        'invoice_number': found.number,
        'status': status,
        'revises': found.revises,
        'issuer': found.issuer,
        'issue_date': found.issue_date or '',
        'due_date': found.due_date or '',
        'subtotal': found.subtotal if found.subtotal is not None else '',
        'discount': found.discount if found.discount is not None else '',
        'grand_total': found.grand_total if found.grand_total is not None else '',
        'order_number': found.order_number,
        'shipment_id': found.shipment_id,
        'line_count': len(found.lines),
        'decimal_mark': found.decimal_mark,
        'date_order': found.date_order,
        'source': found.source,
        'sha256': digest,
        'first_seen': received_at,
        'problems': '; '.join(found.problems),
        'read_by': read_by,
        'bank_account': found.bank_account,
        'kind': found.kind,
        'currency': found.currency,
        'origin': found.origin,
        'destination': found.destination,
        'container': found.container,
        'gross_weight_kg': (found.gross_weight_kg
                            if found.gross_weight_kg is not None else ''),
        'vessel': found.vessel,
        'fx_rate': getattr(found, 'fx_rate', None) or '',
        'customs_value': getattr(found, 'customs_value', None) or '',
        'incoterm': getattr(found, 'incoterm', ''),
    }


def replay(store, message):
    """Take every attachment of one mail from a recorded mailbox.

    A replayed mail arrived at its Date header; it is registered when it
    arrived plus the seconds reading it really took. That is the clock the
    pipeline would have had, watching the mailbox as the mail came in.
    """
    import time
    from datetime import timedelta
    outcomes = []
    for name, payload in message.attachments:
        began = time.perf_counter()
        outcome = store.take(payload, name, message.received_at.isoformat(),
                             message.sender, registered_at='pending')
        spent = timedelta(seconds=round(time.perf_counter() - began, 3))
        stamp = (message.received_at + spent).isoformat(timespec='seconds')
        for row in store.invoices:
            if row.get('registered_at') == 'pending':
                row['registered_at'] = stamp
        outcomes.append((name, outcome))
    return outcomes


def _not_after_arrival(found, received_at):
    """A page cannot be issued after it reached the inbox: OCR read a 6
    as an 8 in the year. The row says so, for a person."""
    from datetime import date
    try:
        arrived = date.fromisoformat(str(received_at)[:10])
    except ValueError:
        return
    if found.issue_date and found.issue_date > arrived:
        found.problems.append(f'issued {found.issue_date}, after it arrived '
                              f'on {arrived}; check by hand')


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _unreadable_row(source, digest, received_at, failure):
    row = {column: '' for column in INVOICE_COLUMNS}
    row.update({'status': 'unreadable', 'source': source, 'sha256': digest,
                'first_seen': received_at, 'problems': failure,
                'line_count': 0})
    return row


def _read_pdf(payload, source):
    import io

    try:
        with pdfplumber.open(io.BytesIO(payload)) as document:
            text = '\n'.join(page.extract_text() or ''
                             for page in document.pages)
    except Exception as failure:
        return None, f'{type(failure).__name__}: {failure}', ''
    read_by = 'text'
    if not text.strip():
        # A scan: a picture with no text layer. OCR stands in for the
        # missing layer; with no OCR on the machine, a person reads it.
        if ocr.tesseract() is None:
            return None, 'no text layer', ''
        found, _ = best_reading(ocr.readings(payload), source)
        if found is None:
            return None, 'no text layer, and OCR found none', ''
        return found, None, 'ocr'
    return fields.read(text, source=source), None, read_by


def _gaps(found):
    """How far a reading is from closing: problems plus missing fields.
    The currency counts: a total in the wrong money is a wrong total."""
    wanted = [found.number, found.grand_total, found.issue_date, found.lines,
              found.currency]
    if found.kind == 'customs':
        # A statement costs the goods at its rate: without it, no closing.
        wanted.append(found.fx_rate)
    return len(found.problems) + sum(1 for value in wanted if not value)


def best_reading(texts, source):
    """The first OCR reading whose sums close and fields are all there.

    When none closes, the reading nearest to closing, flagged for a
    person; a wrong number is never accepted in silence. Returns the
    reading and how many passes it took.
    """
    best, tries = None, 0
    for text in texts:
        tries += 1
        if not text.strip():
            continue
        found = fields.read(text, source=source)
        found.number, note = reconcile_number(found.number, source)
        if note:
            found.problems.append(note)
        if _gaps(found) == 0 or (note and _gaps(found) == 1):
            return found, tries
        if best is None or _gaps(found) < _gaps(best):
            best = found
    if best is not None:
        best.problems.append('no OCR reading closed; check by hand')
    return best, tries


#: An invoice number: issuer code, CN for a credit note, year, count, and
#: -R1 for a revision. OCR may misread a letter of the code, never its
#: shape.
NUMBER_SHAPE = re.compile(r'[A-Z0-9]{3}(?:-CN)?-\d{4}-\d{3,5}(?:-R\d)?(?!\d)')


def reconcile_number(number, source):
    """An OCR'd number one letter away from the attachment's name is a
    slip: OCR swaps look-alikes such as D and O. The name wins, and the
    note says so. Anything further apart is left as read."""
    # Specks of dirt read as dots, dashes and quotes at the edges, and a
    # gap in the print reads as a space inside the number.
    number = re.sub(r'\s+', '', number or '').strip('.-_’\'",;:—–')
    # A label or a speck glued on, "Statementno.SCA-2026-3773" or
    # "SCA-2026-3563Oo": the number is the part shaped like one.
    shaped = NUMBER_SHAPE.search(number)
    if shaped:
        number = shaped.group(0)
    named = Path(source).stem.split('_')[-1]
    if not number or named == number or len(named) != len(number):
        return number, ''
    if sum(a != b for a, b in zip(named, number)) != 1:
        return number, ''
    return named, f'OCR read {number}; the attachment says {named}'


# ----------------------------------------------------------- small files


def _read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def _write_csv(path, columns, rows):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, '') for column in columns})


def _read_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding='utf-8'))


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')
