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
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

import reading

INVOICES_CSV = 'invoices.csv'
LINES_CSV = 'invoice_lines.csv'
STATE_FILE = 'state.json'

INVOICE_COLUMNS = (
    'invoice_number', 'status', 'revises', 'issuer', 'issue_date', 'due_date',
    'subtotal', 'discount', 'grand_total', 'order_number', 'shipment_id',
    'line_count', 'decimal_mark', 'date_order', 'source', 'sha256',
    'first_seen', 'problems',
)

LINE_COLUMNS = (
    'invoice_number', 'sha256', 'row', 'description', 'quantity',
    'unit_price', 'net',
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

    # --------------------------------------------------------- the three

    def take(self, payload, source, received_at):
        """Put one PDF through the three questions."""
        digest = hashlib.sha256(payload).hexdigest()
        if digest in self.state['seen']:
            return Outcome('duplicate', self._number_of(digest), digest)

        found, failure = _read_pdf(payload, source)
        if failure:
            self._remember(digest)
            self._add_row(_unreadable_row(source, digest, received_at, failure))
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
        self._add_row(_invoice_row(found, status, digest, received_at))
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
            })


# ------------------------------------------------------------ the rows


def _invoice_row(found, status, digest, received_at):
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
    }


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
        return None, f'{type(failure).__name__}: {failure}'
    if not text.strip():
        return None, 'no text layer'
    return reading.read(text, source=source), None


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
