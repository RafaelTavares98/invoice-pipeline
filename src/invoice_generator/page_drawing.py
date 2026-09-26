"""The drawing parts every layout shares.

Page geometry, the column grid, and the blocks that appear on more than
one issuer's page: an address stack, a totals box, the small print. The
eight page designs live next door in `layout_styles.py` and are built out
of these.
"""

from decimal import Decimal
from typing import List

from reportlab.lib.pagesizes import A4, landscape

from amounts_and_dates import format_amount, format_date
from invoice import Invoice, InvoiceLine
from issuer_layouts import Layout, description_at

MARGIN = 45
TOP_MARGIN = 55
ROW_HEIGHT = 18


def page_size(layout: Layout):
    """How big the page is, and which way up."""
    return landscape(A4) if layout.landscape else A4


def frame(layout: Layout):
    """The left edge, the right edge and the first baseline."""
    width, height = page_size(layout)
    return MARGIN, width - MARGIN, height - TOP_MARGIN


def column_edges(layout: Layout):
    """Where the vertical rules of the table fall.

    The description column takes whatever width the numeric ones leave,
    wherever in the row it happens to sit.
    """
    left, right, _ = frame(layout)
    narrow = 62.0
    wide = (right - left) - narrow * (len(layout.columns) - 1)
    widths = [
        wide if index == description_at(layout) else narrow
        for index in range(len(layout.columns))
    ]
    edges = [left]
    for width in widths:
        edges.append(edges[-1] + width)
    return edges


def write_row(sheet, layout: Layout, baseline: float, cells) -> None:
    """Put one row of cells across the table."""
    edges = column_edges(layout)
    text_column = description_at(layout)
    for index, text in enumerate(cells):
        if index == text_column:
            sheet.drawString(edges[index] + 6, baseline, str(text))
        else:
            sheet.drawRightString(edges[index + 1] - 6, baseline, str(text))


def cells_for(line: InvoiceLine, layout: Layout):
    """One billed item, as the cells of its row, in this issuer's order."""
    mark = layout.decimal_mark
    values = {
        "description": line.description,
        "quantity": format_amount(line.quantity, mark),
        "unit_price": format_amount(line.unit_price, mark),
        "tax_rate": format_amount(line.tax_rate * 100, mark),
        "line_total": format_amount(line.line_total, mark),
        "weight": format_amount(line.quantity * Decimal("2.4"), mark),
        "volume": format_amount(line.quantity * Decimal("0.06"), mark),
    }
    return [values[held] for _, held in layout.columns]


def header_cells(layout: Layout) -> List[str]:
    """The printed names of the columns."""
    return [name for name, _ in layout.columns]


def seller_lines(layout: Layout) -> List[str]:
    """The seller's name, address and tax number, as printed."""
    return [layout.seller] + list(layout.seller_address) + [
        f"{layout.tax_label}: {layout.tax_id}"
    ]


def meta_rows(invoice: Invoice, layout: Layout):
    """The invoice's own number and dates."""
    rows = [
        (layout.number_label, invoice.number),
        (layout.issued_label,
         format_date(invoice.issue_date, layout.date_order)),
        (layout.due_label,
         format_date(invoice.due_date, layout.date_order)),
    ]
    if layout.second_currency:
        rows.append((
            "Settlement",
            f"{layout.second_currency} at {invoice.exchange_rate}",
        ))
    return rows


def totals_rows(invoice: Invoice, layout: Layout):
    """The three totals, printed the way this issuer prints them."""
    mark = layout.decimal_mark
    return [
        ("Subtotal", format_amount(invoice.subtotal, mark)),
        ("Tax", format_amount(invoice.tax_total, mark)),
        ("Total", format_amount(invoice.grand_total, mark)),
    ]


def stack(sheet, left: float, top: float, heading: str, body) -> float:
    """A small heading with lines under it."""
    sheet.setFont("Helvetica-Bold", 8.5)
    sheet.drawString(left, top, heading)
    sheet.setFont("Helvetica", 9)
    cursor = top - 12
    for line in body:
        sheet.drawString(left, cursor, line)
        cursor -= 11
    return cursor


def small_print(sheet, layout: Layout, left: float, top: float) -> None:
    """Terms, bank details and a closing line, where a layout has them."""
    cursor = top
    sheet.setFont("Helvetica", 8)
    sheet.drawString(left, cursor, layout.terms)
    if layout.bank_line:
        cursor -= 11
        sheet.drawString(left, cursor, layout.bank_line)
    if layout.note:
        width, _ = page_size(layout)
        sheet.setFont("Helvetica-Bold", 9)
        sheet.drawCentredString(width / 2, cursor - 24, layout.note)


# --------------------------------------------------------- the tables


def rows_with_rules(sheet, invoice, layout, top):
    """Horizontal rules only, no verticals."""
    left, right, _ = frame(layout)
    sheet.setFont("Helvetica-Bold", 8.5)
    write_row(sheet, layout, top - 11, header_cells(layout))
    sheet.setLineWidth(0.5)
    cursor = top - ROW_HEIGHT
    sheet.line(left, cursor, right, cursor)
    sheet.setFont("Helvetica", 8.5)
    for line in invoice.lines:
        write_row(sheet, layout, cursor - 11, cells_for(line, layout))
        cursor -= ROW_HEIGHT
        sheet.line(left, cursor, right, cursor)
    return cursor


def double_ruled_table(sheet, invoice, layout, top):
    """A double rule above the header and below the last row."""
    left, right, _ = frame(layout)
    sheet.setLineWidth(0.5)
    sheet.line(left, top, right, top)
    sheet.line(left, top - 2, right, top - 2)
    sheet.setFont("Helvetica-Bold", 8.5)
    write_row(sheet, layout, top - 14, header_cells(layout))
    cursor = top - ROW_HEIGHT - 4
    sheet.line(left, cursor, right, cursor)
    sheet.setFont("Helvetica", 8.5)
    for line in invoice.lines:
        write_row(sheet, layout, cursor - 12, cells_for(line, layout))
        cursor -= ROW_HEIGHT
    sheet.line(left, cursor, right, cursor)
    sheet.line(left, cursor - 2, right, cursor - 2)
    return cursor - 2


def grid_table(sheet, invoice, layout, top, totals=False):
    """A closed grid, every cell bordered."""
    left, right, _ = frame(layout)
    edges = column_edges(layout)
    count = len(invoice.lines) + (2 if totals else 1)
    bottom = top - ROW_HEIGHT * count
    sheet.setLineWidth(0.6)
    for index in range(count + 1):
        line_y = top - ROW_HEIGHT * index
        sheet.line(left, line_y, right, line_y)
    for edge in edges:
        sheet.line(edge, top, edge, bottom)
    sheet.setFont("Helvetica-Bold", 8)
    write_row(sheet, layout, top - 12, header_cells(layout))
    sheet.setFont("Helvetica", 8)
    for position, line in enumerate(invoice.lines, start=1):
        write_row(
            sheet, layout, top - 12 - ROW_HEIGHT * position,
            cells_for(line, layout),
        )
    if totals:
        totals_inside(sheet, invoice, layout, bottom + ROW_HEIGHT)
    return bottom - 22


def zebra_table(sheet, invoice, layout, top):
    """A filled header band and alternating row tints."""
    left, right, _ = frame(layout)
    sheet.setFillColorRGB(*layout.accent)
    sheet.rect(left, top - ROW_HEIGHT, right - left, ROW_HEIGHT,
               stroke=0, fill=1)
    sheet.setFillColorRGB(1, 1, 1)
    sheet.setFont("Helvetica-Bold", 8.5)
    write_row(sheet, layout, top - 12, header_cells(layout))

    cursor = top - ROW_HEIGHT
    for position, line in enumerate(invoice.lines):
        if position % 2 == 1:
            sheet.setFillColorRGB(0.95, 0.95, 0.94)
            sheet.rect(left, cursor - ROW_HEIGHT, right - left,
                       ROW_HEIGHT, stroke=0, fill=1)
        sheet.setFillColorRGB(0, 0, 0)
        sheet.setFont("Helvetica", 8.5)
        write_row(sheet, layout, cursor - 12, cells_for(line, layout))
        cursor -= ROW_HEIGHT
    sheet.setLineWidth(0.6)
    sheet.line(left, cursor, right, cursor)
    return cursor


def airy_table(sheet, invoice, layout, top):
    """No rules, small grey headings, and room between the rows."""
    left, right, _ = frame(layout)
    sheet.setFillColorRGB(0.45, 0.45, 0.45)
    sheet.setFont("Helvetica", 7.5)
    write_row(sheet, layout, top - 10, [
        name.upper() for name in header_cells(layout)
    ])
    sheet.setFillColorRGB(0, 0, 0)
    cursor = top - 30
    for line in invoice.lines:
        sheet.setFont("Helvetica", 9)
        write_row(sheet, layout, cursor, cells_for(line, layout))
        cursor -= ROW_HEIGHT + 10
    sheet.setLineWidth(0.4)
    sheet.line(right - 210, cursor + 16, right, cursor + 16)
    return cursor


def dashed_table(sheet, invoice, layout, top):
    """A heavy rule under the header, dashes between the rows."""
    left, right, _ = frame(layout)
    sheet.setFont("Helvetica-Bold", 8.5)
    write_row(sheet, layout, top - 10, [
        name.upper() for name in header_cells(layout)
    ])
    sheet.setLineWidth(1.4)
    sheet.setStrokeColorRGB(*layout.accent)
    sheet.line(left, top - 17, right, top - 17)
    sheet.setStrokeColorRGB(0, 0, 0)

    cursor = top - 17 - ROW_HEIGHT
    sheet.setLineWidth(0.4)
    sheet.setDash(1, 2)
    for line in invoice.lines:
        sheet.setFont("Helvetica", 8.5)
        write_row(sheet, layout, cursor + 5, cells_for(line, layout))
        sheet.line(left, cursor, right, cursor)
        cursor -= ROW_HEIGHT
    sheet.setDash()
    return cursor


# --------------------------------------------------------- the totals


def totals_plain(sheet, invoice, layout, top):
    """Three right aligned rows and a rule."""
    _, right, _ = frame(layout)
    cursor = top
    for label, value in totals_rows(invoice, layout):
        bold = label == "Total"
        sheet.setFont("Helvetica-Bold" if bold else "Helvetica", 9.5)
        sheet.drawRightString(right - 90, cursor, f"{label}:")
        sheet.drawRightString(right, cursor, value)
        cursor -= 14
    sheet.setLineWidth(0.6)
    sheet.line(right - 150, cursor + 8, right, cursor + 8)
    return cursor - 10


def totals_with_band(sheet, invoice, layout, top):
    """The last row sits on a grey band."""
    _, right, _ = frame(layout)
    cursor = top
    for label, value in totals_rows(invoice, layout):
        if label == "Total":
            sheet.setFillColorRGB(0.9, 0.9, 0.89)
            sheet.rect(right - 210, cursor - 5, 210, 17, stroke=0, fill=1)
            sheet.setFillColorRGB(0, 0, 0)
            sheet.setFont("Helvetica-Bold", 10)
        else:
            sheet.setFont("Helvetica", 9.5)
        sheet.drawRightString(right - 90, cursor, f"{label}:")
        sheet.drawRightString(right, cursor, value)
        cursor -= 16
    return cursor - 8


def totals_in_box(sheet, invoice, layout, top):
    """The amount owed in a filled box, the way a garage prints it."""
    _, right, _ = frame(layout)
    mark = layout.decimal_mark
    cursor = top
    for label, value in (
        ("Subtotal", format_amount(invoice.subtotal, mark)),
        ("Tax", format_amount(invoice.tax_total, mark)),
    ):
        sheet.setFont("Helvetica", 9)
        sheet.drawRightString(right - 90, cursor, f"{label}:")
        sheet.drawRightString(right, cursor, value)
        cursor -= 14
    sheet.setFillColorRGB(*layout.accent)
    sheet.rect(right - 200, cursor - 16, 200, 22, stroke=0, fill=1)
    sheet.setFillColorRGB(1, 1, 1)
    sheet.setFont("Helvetica-Bold", 10)
    sheet.drawString(right - 192, cursor - 8, "Balance due")
    sheet.drawRightString(
        right - 8, cursor - 8, format_amount(invoice.grand_total, mark)
    )
    sheet.setFillColorRGB(0, 0, 0)
    return cursor - 34


def totals_boxed_cells(sheet, invoice, layout, top):
    """Totals in their own bordered cells, above the table."""
    left, right, _ = frame(layout)
    rows = totals_rows(invoice, layout)
    width = (right - left) / len(rows)
    sheet.setLineWidth(0.6)
    for index, (label, value) in enumerate(rows):
        box_left = left + width * index
        sheet.rect(box_left, top - 20, width, 20)
        sheet.setFont("Helvetica", 8)
        sheet.drawString(box_left + 5, top - 13, f"{label}: {value}")
    return top - 22


def totals_inside(sheet, invoice, layout, baseline):
    """A closing row of the table itself, on the wide page."""
    left, _, _ = frame(layout)
    mark = layout.decimal_mark
    sheet.setFont("Helvetica-Bold", 8)
    sheet.drawString(
        left + 6, baseline - 12,
        "Subtotal: {}   Tax: {}   Total: {}".format(
            format_amount(invoice.subtotal, mark),
            format_amount(invoice.tax_total, mark),
            format_amount(invoice.grand_total, mark),
        ),
    )
