"""Seven ways to print the same invoice.

Each issuer keeps its own habits: a closed grid, a tinted band, no rules at
all. A reader that assumes one shape falls over on the next.
"""

from formatting import format_amount
from page_drawing import (ROW_HEIGHT, cells_for, column_edges, frame,
                          header_cells, totals_rows, write_row)


# ------------------------------------------------------------- the tables


def grid_table(sheet, invoice, layout, top):
    """Every cell bordered, the way a customs form is printed."""
    left, right, _ = frame(layout)
    edges = column_edges(layout)
    rows = len(invoice.lines) + 1
    bottom = top - ROW_HEIGHT * rows

    sheet.setLineWidth(0.6)
    for index in range(rows + 1):
        y = top - ROW_HEIGHT * index
        sheet.line(left, y, right, y)
    for edge in edges:
        sheet.line(edge, top, edge, bottom)

    sheet.setFont('Helvetica-Bold', 7.5)
    write_row(sheet, layout, top - 11, header_cells(layout))
    sheet.setFont('Helvetica', 8)
    for position, line in enumerate(invoice.lines, start=1):
        write_row(sheet, layout, top - 11 - ROW_HEIGHT * position,
                  cells_for(line, layout))
    return bottom - 16


def zebra_table(sheet, invoice, layout, top):
    """A filled header band and alternating row tints."""
    left, right, _ = frame(layout)
    sheet.setFillColorRGB(*layout.accent)
    sheet.rect(left, top - ROW_HEIGHT, right - left, ROW_HEIGHT, stroke=0, fill=1)
    sheet.setFillColorRGB(1, 1, 1)
    sheet.setFont('Helvetica-Bold', 7.5)
    write_row(sheet, layout, top - 12, header_cells(layout))

    cursor = top - ROW_HEIGHT
    for position, line in enumerate(invoice.lines):
        if position % 2 == 1:
            sheet.setFillColorRGB(0.95, 0.95, 0.94)
            sheet.rect(left, cursor - ROW_HEIGHT, right - left, ROW_HEIGHT,
                       stroke=0, fill=1)
        sheet.setFillColorRGB(0, 0, 0)
        sheet.setFont('Helvetica', 8)
        write_row(sheet, layout, cursor - 12, cells_for(line, layout))
        cursor -= ROW_HEIGHT
    sheet.setLineWidth(0.6)
    sheet.line(left, cursor, right, cursor)
    return cursor - 14


def banded_table(sheet, invoice, layout, top):
    """A coloured rule under the header, nothing between the rows."""
    left, right, _ = frame(layout)
    sheet.setFont('Helvetica-Bold', 7.5)
    write_row(sheet, layout, top - 10, [n.upper() for n in header_cells(layout)])
    sheet.setLineWidth(1.6)
    sheet.setStrokeColorRGB(*layout.accent)
    sheet.line(left, top - 16, right, top - 16)
    sheet.setStrokeColorRGB(0, 0, 0)

    cursor = top - 16 - ROW_HEIGHT
    sheet.setFont('Helvetica', 8.5)
    for line in invoice.lines:
        write_row(sheet, layout, cursor + 5, cells_for(line, layout))
        cursor -= ROW_HEIGHT
    sheet.setLineWidth(0.5)
    sheet.line(left, cursor + 10, right, cursor + 10)
    return cursor - 4


def minimal_table(sheet, invoice, layout, top):
    """No rules, grey headings, room to breathe."""
    left, right, _ = frame(layout)
    sheet.setFillColorRGB(0.45, 0.45, 0.45)
    sheet.setFont('Helvetica', 7)
    write_row(sheet, layout, top - 10, [n.upper() for n in header_cells(layout)])
    sheet.setFillColorRGB(0, 0, 0)

    cursor = top - 28
    sheet.setFont('Helvetica', 9)
    for line in invoice.lines:
        write_row(sheet, layout, cursor, cells_for(line, layout))
        cursor -= ROW_HEIGHT + 8
    sheet.setLineWidth(0.4)
    sheet.line(right - 230, cursor + 16, right, cursor + 16)
    return cursor + 4


def dashed_table(sheet, invoice, layout, top):
    """Dashes between the rows."""
    left, right, _ = frame(layout)
    sheet.setFont('Helvetica-Bold', 7.5)
    write_row(sheet, layout, top - 10, header_cells(layout))
    sheet.setLineWidth(0.8)
    sheet.line(left, top - 16, right, top - 16)

    cursor = top - 16 - ROW_HEIGHT
    sheet.setLineWidth(0.4)
    sheet.setDash(1, 2)
    sheet.setFont('Helvetica', 8.5)
    for line in invoice.lines:
        write_row(sheet, layout, cursor + 5, cells_for(line, layout))
        sheet.line(left, cursor, right, cursor)
        cursor -= ROW_HEIGHT
    sheet.setDash()
    return cursor - 4


def form_table(sheet, invoice, layout, top):
    """A boxed form, totals printed above the lines."""
    left, right, _ = frame(layout)
    cursor = _totals_boxed(sheet, invoice, layout, top)
    return grid_table(sheet, invoice, layout, cursor - 8)


def ledger_table(sheet, invoice, layout, top):
    """A wide ruled ledger, for the landscape freight pages."""
    left, right, _ = frame(layout)
    sheet.setLineWidth(0.5)
    sheet.line(left, top, right, top)
    sheet.line(left, top - 2, right, top - 2)
    sheet.setFont('Helvetica-Bold', 7.5)
    write_row(sheet, layout, top - 13, header_cells(layout))
    cursor = top - ROW_HEIGHT - 3
    sheet.line(left, cursor, right, cursor)

    sheet.setFont('Helvetica', 8)
    for line in invoice.lines:
        write_row(sheet, layout, cursor - 12, cells_for(line, layout))
        cursor -= ROW_HEIGHT
    sheet.line(left, cursor, right, cursor)
    sheet.line(left, cursor - 2, right, cursor - 2)
    return cursor - 16


TABLES = {
    'grid': grid_table,
    'zebra': zebra_table,
    'banded': banded_table,
    'minimal': minimal_table,
    'dashed': dashed_table,
    'form': form_table,
    'ledger': ledger_table,
}


# ------------------------------------------------------------- the totals


def totals_plain(sheet, invoice, layout, top):
    _, right, _ = frame(layout)
    cursor = top
    for label, value in totals_rows(invoice, layout):
        bold = label.startswith('Total')
        sheet.setFont('Helvetica-Bold' if bold else 'Helvetica', 9.5 if bold else 8.5)
        sheet.drawRightString(right - 95, cursor, f'{label}')
        sheet.drawRightString(right, cursor, value)
        cursor -= 13
    sheet.setLineWidth(0.6)
    sheet.line(right - 170, cursor + 8, right, cursor + 8)
    return cursor - 10


def totals_banded(sheet, invoice, layout, top):
    _, right, _ = frame(layout)
    cursor = top
    for label, value in totals_rows(invoice, layout):
        if label.startswith('Total'):
            sheet.setFillColorRGB(*layout.accent)
            sheet.rect(right - 220, cursor - 6, 220, 19, stroke=0, fill=1)
            sheet.setFillColorRGB(1, 1, 1)
            sheet.setFont('Helvetica-Bold', 10)
        else:
            sheet.setFont('Helvetica', 8.5)
        sheet.drawRightString(right - 95, cursor, label)
        sheet.drawRightString(right - 8 if label.startswith('Total') else right,
                              cursor, value)
        sheet.setFillColorRGB(0, 0, 0)
        cursor -= 16
    return cursor - 8


def totals_already_printed(sheet, invoice, layout, top):
    """The boxed form prints its totals above the lines, so here there is
    nothing left to draw."""
    return top


def _totals_boxed(sheet, invoice, layout, top):
    left, right, _ = frame(layout)
    rows = totals_rows(invoice, layout)
    width = (right - left) / len(rows)
    sheet.setLineWidth(0.6)
    for index, (label, value) in enumerate(rows):
        box_left = left + width * index
        sheet.rect(box_left, top - 20, width, 20)
        sheet.setFont('Helvetica', 7.5)
        sheet.drawString(box_left + 5, top - 13, f'{label}: {value}')
    return top - 22


TOTALS = {
    'grid': totals_plain,
    'zebra': totals_banded,
    'banded': totals_banded,
    'minimal': totals_plain,
    'dashed': totals_plain,
    'form': totals_already_printed,
    'ledger': totals_plain,
}
