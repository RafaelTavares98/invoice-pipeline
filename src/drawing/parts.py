"""The drawing parts every page design shares.

Geometry, the column grid, the address stacks and the totals. The seven page
designs live next door in `styles.py` and are built out of these.
"""

from reportlab.lib.pagesizes import A4, landscape

from business.buyer import MOTY, SHIP_TO
from drawing.formatting import (format_amount, format_date, format_price,
                        format_quantity)
from drawing.layouts import description_at

MARGIN = 45
TOP_MARGIN = 52
ROW_HEIGHT = 17

NARROW = {'code': 62.0, 'hs_code': 52.0}


def page_size(layout):
    return landscape(A4) if layout.landscape else A4


def frame(layout):
    width, height = page_size(layout)
    return MARGIN, width - MARGIN, height - TOP_MARGIN


def column_edges(layout):
    left, right, _ = frame(layout)
    default = 58.0 if layout.landscape else 64.0
    text_column = description_at(layout)

    widths = []
    for index, (_, held) in enumerate(layout.columns):
        widths.append(None if index == text_column else NARROW.get(held, default))
    spare = (right - left) - sum(w for w in widths if w)
    widths = [spare if w is None else w for w in widths]

    edges = [left]
    for width in widths:
        edges.append(edges[-1] + width)
    return edges


def write_row(sheet, layout, baseline, cells):
    edges = column_edges(layout)
    text_column = description_at(layout)
    for index, text in enumerate(cells):
        held = layout.columns[index][1]
        if index == text_column or held in ('code', 'hs_code'):
            sheet.drawString(edges[index] + 5, baseline, str(text))
        else:
            sheet.drawRightString(edges[index + 1] - 5, baseline, str(text))


def cells_for(line, layout):
    mark = layout.decimal_mark
    return [{
        'code': line.code,
        'description': line.description,
        'hs_code': line.hs_code,
        # A W/M is cubic metres or tonnes, so it keeps its cents.
        'quantity': (format_amount(line.quantity, mark) if line.unit == 'W/M'
                     else format_quantity(line.quantity, mark)),
        # A tax base carries cents; a count of pieces does not.
        'base': format_amount(line.quantity, mark),
        'unit': line.unit,
        'unit_price': format_price(line.unit_price, mark),
        'net': format_amount(line.net, mark),
        # A surcharge has no cargo of its own, so the cell stays empty.
        'weight': format_amount(line.weight_kg, mark) if line.weight_kg else '',
        'volume': format_amount(line.volume_m3, mark) if line.volume_m3 else '',
    }[held] for _, held in layout.columns]


def header_cells(layout):
    return [name.replace('USD', layout.currency) for name, _ in layout.columns]


def issuer_lines(layout):
    issuer = layout.issuer
    return [issuer.name] + list(issuer.address) + [
        f'{issuer.tax_label}: {issuer.tax_id}'
    ]


def buyer_lines():
    return [MOTY.name, f'Attn: {MOTY.department}'] + list(MOTY.address) + [
        f'{MOTY.tax_label}: {MOTY.tax_id}', MOTY.contact,
    ]


def meta_rows(invoice, layout):
    rows = [
        (layout.number_label, invoice.number),
        (layout.issued_label, format_date(invoice.issue_date, layout.date_order)),
        (layout.due_label, format_date(invoice.due_date, layout.date_order)),
        ('Currency', invoice.currency),
    ]
    if invoice.reference:
        rows.append(('Reference', invoice.reference))
    if invoice.incoterm:
        rows.append(('Incoterm', invoice.incoterm))
    rows += list(invoice.facts)
    return rows


def shipment_rows(invoice):
    held = invoice.shipment
    if not held:
        return []
    return [
        ('Origin', held['origin']),
        ('Destination', held['destination']),
        ('Equipment', held['container']),
        ('Vessel / flight', held['vessel']),
        ('Gross weight kg', held['weight_kg']),
        ('Volume m3', held['volume_m3']),
    ]


def totals_rows(invoice, layout):
    mark = layout.decimal_mark
    rows = [('Subtotal', format_amount(invoice.subtotal, mark))]
    if invoice.discount:
        rows.append(('Discount', '-' + format_amount(invoice.discount, mark)))
    rows.append((f'Total {invoice.currency}',
                 format_amount(invoice.grand_total, mark)))
    return rows


def stack(sheet, left, top, heading, body):
    sheet.setFillColorRGB(0.42, 0.42, 0.42)
    sheet.setFont('Helvetica-Bold', 7.5)
    sheet.drawString(left, top, heading.upper())
    sheet.setFillColorRGB(0, 0, 0)
    sheet.setFont('Helvetica', 8.5)
    cursor = top - 12
    for line in body:
        sheet.drawString(left, cursor, str(line))
        cursor -= 10.5
    return cursor


def pairs(sheet, left, top, rows, label_width=78):
    cursor = top
    for label, value in rows:
        sheet.setFillColorRGB(0.42, 0.42, 0.42)
        sheet.setFont('Helvetica', 8)
        sheet.drawString(left, cursor, f'{label}')
        sheet.setFillColorRGB(0, 0, 0)
        sheet.setFont('Helvetica-Bold', 8.5)
        sheet.drawString(left + label_width, cursor, str(value))
        cursor -= 11
    return cursor


def title_block(sheet, layout, invoice, cursor):
    left, right, _ = frame(layout)
    sheet.setFillColorRGB(*layout.accent)
    sheet.setFont('Helvetica-Bold', 19)
    sheet.drawRightString(right, cursor - 4, layout.title.upper())
    sheet.setFillColorRGB(0.42, 0.42, 0.42)
    sheet.setFont('Helvetica', 9)
    sheet.drawRightString(right, cursor - 18,
                          f'{layout.number_label} {invoice.number}')
    sheet.setFillColorRGB(0, 0, 0)

    return stack(sheet, left, cursor, 'From', issuer_lines(layout)) - 10


def parties_block(sheet, layout, invoice, cursor):
    left, right, _ = frame(layout)
    middle = left + (right - left) * 0.34
    far = left + (right - left) * 0.64

    bill = stack(sheet, left, cursor, 'Bill to', buyer_lines())
    ship = stack(sheet, middle, cursor, 'Ship to', SHIP_TO)
    meta = pairs(sheet, far, cursor, meta_rows(invoice, layout))

    bottom = min(bill, ship, meta)
    if invoice.shipment:
        bottom = _shipment_strip(sheet, layout, invoice, bottom - 6)
    return bottom - 10


def _shipment_strip(sheet, layout, invoice, cursor):
    left, right, _ = frame(layout)
    rows = shipment_rows(invoice)
    sheet.setFillColorRGB(0.95, 0.95, 0.94)
    sheet.rect(left, cursor - 26, right - left, 32, stroke=0, fill=1)
    sheet.setFillColorRGB(0, 0, 0)
    step = (right - left) / len(rows)
    for index, (label, value) in enumerate(rows):
        x = left + step * index + 6
        sheet.setFillColorRGB(0.42, 0.42, 0.42)
        sheet.setFont('Helvetica', 7)
        sheet.drawString(x, cursor - 4, label.upper())
        sheet.setFillColorRGB(0, 0, 0)
        sheet.setFont('Helvetica-Bold', 8)
        sheet.drawString(x, cursor - 16, str(value))
    return cursor - 30


CURRENCY_LINES = {'USD': 'All amounts in United States dollars.',
                  'BRL': 'All amounts in Brazilian reais.'}


def small_print(sheet, layout, cursor, pay_to=''):
    """Terms and the account to pay into. An invoice may name another
    account than the issuer's usual one: a change on file, or an error."""
    left, _, _ = frame(layout)
    issuer = layout.issuer
    bank = pay_to or issuer.bank_line
    sheet.setFillColorRGB(0.3, 0.3, 0.3)
    sheet.setFont('Helvetica', 7.5)
    sheet.drawString(left, cursor, issuer.terms)
    cursor -= 10
    if bank:
        sheet.drawString(left, cursor, bank)
        cursor -= 10
    sheet.drawString(left, cursor, CURRENCY_LINES.get(
        layout.currency, f'All amounts in {layout.currency}.'))
    sheet.setFillColorRGB(0, 0, 0)
    return cursor - 10
