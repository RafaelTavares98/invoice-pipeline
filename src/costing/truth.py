"""What a perfect reader would have filed, straight from the simulation.

Reading five thousand PDFs takes hours. A perfect reader takes seconds:
the same two CSV files, in the same columns, with every field right and
the same filing rules as the real one. A resend is filed once; a
revision supersedes what it revises.

It is used to check the costing at volume and to train a model on clean
history. Scores on real reading always come from the real reader.
"""

from datetime import timedelta

from business import issuers
from mail import delivery


def _number(text):
    return text.replace('.', '').replace(',', '.')


def books(operation):
    """(invoice rows, line rows), as the reader's Store would hold them."""
    rows, lines, seen = [], [], set()
    written = sorted(operation.invoices, key=lambda i: (i.issue_date, i.number))
    for position, invoice in enumerate(written, start=1):
        if invoice.number in seen:
            continue
        seen.add(invoice.number)
        sent = delivery.sent_at(invoice, position)
        status = 'new'
        # Only a number ending -R1 announces a correction, as on the page.
        # A credit note also names the invoice it credits; it replaces
        # nothing.
        if invoice.number.endswith('-R1'):
            for row in rows:
                if row['invoice_number'] == invoice.revises:
                    row['status'] = 'superseded'
                    status = 'revised'
        rows.append(_row(invoice, status, sent))
        lines += _lines(invoice)
    return rows, lines


def _row(invoice, status, sent):
    box = invoice.shipment or {}
    facts = dict(invoice.facts)
    issuer = issuers.by_code(invoice.issuer_code)
    return {
        'invoice_number': invoice.number,
        'status': status,
        'revises': invoice.revises if invoice.number.endswith('-R1') else '',
        'issuer': issuer.name,
        'issue_date': invoice.issue_date.isoformat(),
        'due_date': invoice.due_date.isoformat(),
        'subtotal': str(invoice.subtotal),
        'discount': str(invoice.discount),
        'grand_total': str(invoice.grand_total),
        'order_number': invoice.order_number,
        'shipment_id': invoice.shipment_id,
        'line_count': len(invoice.lines),
        'sha256': invoice.number,
        'first_seen': sent.isoformat(),
        'registered_at': (sent + timedelta(seconds=40)).isoformat(),
        'problems': '',
        'read_by': 'text',
        'bank_account': invoice.pay_to or issuer.bank_line,
        'sender': invoice.sender or issuers.address_for(issuer),
        'kind': invoice.kind,
        'currency': invoice.currency,
        'origin': box.get('origin', ''),
        'destination': box.get('destination', ''),
        'container': box.get('container', ''),
        'gross_weight_kg': box.get('weight_kg', ''),
        'vessel': box.get('vessel', ''),
        'fx_rate': _number(facts['FX rate']) if 'FX rate' in facts else '',
        'customs_value': (_number(facts['Customs value'])
                          if 'Customs value' in facts else ''),
    }


def _lines(invoice):
    return [{
        'invoice_number': invoice.number,
        'sha256': invoice.number,
        'row': position,
        'description': line.description,
        'quantity': str(line.quantity),
        'unit_price': str(line.unit_price),
        'net': str(line.net),
        'code': line.code,
        'hs_code': line.hs_code,
        'weight_kg': str(line.weight_kg) if line.weight_kg else '',
    } for position, line in enumerate(invoice.lines, start=1)]
