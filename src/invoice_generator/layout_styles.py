"""The eight page designs, one function each.

They differ in shape, not only in wording: where the addresses sit,
whether the table is ruled, boxed or open, where the totals fall, and on
one of them, which way up the page is. A reader that only ever saw one
shape has been tested against nothing.

Every company, address and tax number is invented. The designs copy the
habits of trade documents, never any real company's branding.
"""

from pathlib import Path

from reportlab.pdfgen import canvas

from invoice import Invoice
from invoice_generator.page_drawing import (
    airy_table,
    dashed_table,
    double_ruled_table,
    frame,
    grid_table,
    meta_rows,
    page_size,
    rows_with_rules,
    seller_lines,
    small_print,
    stack,
    totals_boxed_cells,
    totals_in_box,
    totals_plain,
    totals_rows,
    totals_with_band,
    zebra_table,
)
from issuer_layouts import Layout

#: An office scanner runs at 200 to 300 dots per inch.
SCAN_RESOLUTION = 300


def render_pdf(invoice: Invoice, layout: Layout, target: Path) -> Path:
    """Print the invoice the way its issuer would print it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet = canvas.Canvas(str(target), pagesize=page_size(layout))
    RENDERERS[layout.style](sheet, invoice, layout)
    sheet.showPage()
    sheet.save()
    return target


def render_image_pdf(invoice: Invoice, layout: Layout, target: Path) -> Path:
    """Print the same invoice, then photograph it.

    The scan is a picture of the real page, not a second drawing of its
    contents. Anything else would test the reader against a page no
    supplier ever sends.
    """
    import pdfplumber

    typeset = render_pdf(invoice, layout, target.with_suffix(".set.pdf"))
    with pdfplumber.open(str(typeset)) as document:
        page = document.pages[0]
        picture = page.to_image(resolution=SCAN_RESOLUTION).original
        truth_file(target).write_text(
            page.extract_text() or "", encoding="utf-8"
        )
    #: The saved page must declare the resolution it was photographed at.
    #: Declare less and the page comes out physically larger than the
    #: paper, so the reader rasterises a stretched picture and misreads a
    #: nine as a zero.
    picture.convert("RGB").save(
        str(target), "PDF", resolution=float(SCAN_RESOLUTION)
    )
    typeset.unlink()
    return target


def truth_file(pdf: Path) -> Path:
    """Where the words of a scanned page are recorded."""
    return pdf.with_suffix(".truth.txt")


def draw_column(sheet, invoice: Invoice, layout: Layout) -> None:
    """Everything down the left, in one narrow column."""
    left, right, top = frame(layout)
    sheet.setFont("Helvetica-Bold", 13)
    sheet.drawString(left, top, layout.title)

    cursor = top - 26
    cursor = stack(sheet, left, cursor, "From", seller_lines(layout))
    cursor = stack(sheet, left, cursor - 6, "Bill to", [invoice.buyer])
    cursor -= 6
    for label, value in meta_rows(invoice, layout):
        sheet.setFont("Helvetica", 9)
        sheet.drawString(left, cursor, f"{label}: {value}")
        cursor -= 12
    sheet.drawString(left, cursor, f"Currency: {invoice.currency}")

    cursor = rows_with_rules(sheet, invoice, layout, cursor - 24)
    cursor -= 8
    for label, value in totals_rows(invoice, layout):
        sheet.setFont("Helvetica", 9)
        sheet.drawString(left + 24, cursor, f"{label}: {value}")
        cursor -= 13
    small_print(sheet, layout, left, cursor - 10)


def draw_split(sheet, invoice: Invoice, layout: Layout) -> None:
    """Two address columns divided by a rule down the middle."""
    left, right, top = frame(layout)
    middle = (left + right) / 2
    sheet.setFont("Helvetica-Bold", 11)
    sheet.drawString(left, top, layout.title.upper())
    sheet.setFont("Helvetica-Bold", 20)
    sheet.drawRightString(right, top - 3, invoice.number)
    sheet.setLineWidth(1.2)
    sheet.line(left, top - 12, right, top - 12)

    sheet.line(middle, top - 20, middle, top - 96)
    stack(sheet, left, top - 26, "From", seller_lines(layout))
    sheet.setFont("Helvetica", 9)
    sheet.drawString(middle + 14, top - 32, f"Bill to: {invoice.buyer}")
    cursor = top - 50
    for label, value in meta_rows(invoice, layout):
        sheet.setFont("Helvetica", 9)
        sheet.drawString(middle + 14, cursor, f"{label}: {value}")
        cursor -= 12
    sheet.drawString(middle + 14, cursor, f"Currency: {invoice.currency}")

    cursor = double_ruled_table(sheet, invoice, layout, top - 116)
    cursor = totals_with_band(sheet, invoice, layout, cursor - 10)
    small_print(sheet, layout, left, cursor - 8)


def draw_ledger_wide(sheet, invoice: Invoice, layout: Layout) -> None:
    """A wide page, a wide table, and the totals inside it."""
    left, right, top = frame(layout)
    sheet.setFont("Helvetica-Bold", 12)
    sheet.drawString(left, top, layout.seller)
    sheet.setFont("Helvetica", 9)
    sheet.drawString(left, top - 13, ", ".join(layout.seller_address))
    sheet.drawString(left, top - 25, f"{layout.tax_label}: {layout.tax_id}")

    strip = top - 44
    sheet.setLineWidth(0.6)
    sheet.rect(left, strip - 18, right - left, 18)
    cursor = left + 8
    parts = list(meta_rows(invoice, layout))
    parts.append(("Currency", invoice.currency))
    for label, value in parts:
        sheet.setFont("Helvetica", 8)
        sheet.drawString(cursor, strip - 13, f"{label}: {value}")
        cursor += (right - left) / len(parts)

    sheet.setFont("Helvetica", 9)
    sheet.drawString(left, strip - 32, f"Bill to: {invoice.buyer}")
    cursor = grid_table(sheet, invoice, layout, strip - 48, totals=True)
    small_print(sheet, layout, left, cursor - 6)


def draw_form_grid(sheet, invoice: Invoice, layout: Layout) -> None:
    """A dense bordered form, every field in its own cell."""
    left, right, top = frame(layout)
    sheet.setFont("Helvetica-Bold", 11)
    sheet.drawCentredString((left + right) / 2, top, layout.title.upper())

    cells = list(meta_rows(invoice, layout))
    cells.append(("Currency", invoice.currency))
    cells.append(("Bill to", invoice.buyer))
    cursor = top - 18
    width = (right - left) / 2
    sheet.setLineWidth(0.6)
    for index, (label, value) in enumerate(cells):
        column = index % 2
        if column == 0 and index:
            cursor -= 20
        box_left = left + width * column
        sheet.rect(box_left, cursor - 20, width, 20)
        sheet.setFont("Helvetica", 8)
        sheet.drawString(box_left + 5, cursor - 13, f"{label}: {value}")
    cursor -= 22

    sheet.rect(left, cursor - 34, right - left, 34)
    sheet.setFont("Helvetica-Bold", 8)
    sheet.drawString(left + 5, cursor - 11, "Seller")
    sheet.setFont("Helvetica", 8)
    sheet.drawString(left + 5, cursor - 22, layout.seller)
    sheet.drawString(left + 5, cursor - 31, ", ".join(layout.seller_address))

    cursor = totals_boxed_cells(sheet, invoice, layout, cursor - 46)
    cursor = grid_table(sheet, invoice, layout, cursor - 10)
    small_print(sheet, layout, left, cursor - 6)


def draw_banded(sheet, invoice: Invoice, layout: Layout) -> None:
    """A colour band across the head, and tinted rows below."""
    left, right, top = frame(layout)
    width, _ = page_size(layout)
    sheet.setFillColorRGB(*layout.accent)
    sheet.rect(0, top - 22, width, 46, stroke=0, fill=1)
    sheet.setFillColorRGB(1, 1, 1)
    sheet.setFont("Helvetica-Bold", 15)
    sheet.drawString(left, top - 2, layout.seller)
    sheet.drawRightString(right, top - 2, layout.title.upper())
    sheet.setFillColorRGB(0, 0, 0)

    cursor = stack(sheet, left, top - 44, "From", seller_lines(layout)[1:])
    stack(sheet, left, cursor - 6, "Bill to", [invoice.buyer])
    meta = top - 44
    for label, value in meta_rows(invoice, layout):
        sheet.setFont("Helvetica", 9)
        sheet.drawRightString(right - 110, meta, f"{label}:")
        sheet.setFont("Helvetica-Bold", 9)
        sheet.drawRightString(right, meta, value)
        meta -= 13
    sheet.setFont("Helvetica", 9)
    sheet.drawRightString(right - 110, meta, "Currency:")
    sheet.drawRightString(right, meta, invoice.currency)

    cursor = zebra_table(sheet, invoice, layout, min(cursor, meta) - 26)
    cursor = totals_plain(sheet, invoice, layout, cursor - 10)
    small_print(sheet, layout, left, cursor - 6)


def draw_boxed(sheet, invoice: Invoice, layout: Layout) -> None:
    """Two bordered blocks, the way a customs declaration is laid out."""
    left, right, top = frame(layout)
    sheet.setFont("Helvetica-Bold", 13)
    sheet.drawCentredString((left + right) / 2, top, layout.title)

    cursor = top - 24
    half = (right - left) / 2
    sheet.setLineWidth(0.7)
    sheet.rect(left, cursor - 70, half, 70)
    sheet.rect(left + half, cursor - 70, half, 70)
    sheet.setFont("Helvetica-Bold", 8)
    sheet.drawString(left + 6, cursor - 12, "Shipper / exporter")
    sheet.setFont("Helvetica", 8.5)
    inner = cursor - 25
    for line in seller_lines(layout):
        sheet.drawString(left + 6, inner, line)
        inner -= 10
    sheet.drawString(
        left + half + 6, cursor - 40, f"Consignee: {invoice.buyer}"
    )

    cursor -= 80
    for label, value in meta_rows(invoice, layout):
        sheet.setFont("Helvetica", 9)
        sheet.drawString(left, cursor, f"{label}: {value}")
        cursor -= 12
    sheet.drawString(left, cursor, f"Currency: {invoice.currency}")

    cursor = grid_table(sheet, invoice, layout, cursor - 22)
    cursor = totals_plain(sheet, invoice, layout, cursor - 8)
    small_print(sheet, layout, left, cursor - 6)


def draw_minimal(sheet, invoice: Invoice, layout: Layout) -> None:
    """A large title, a hairline, and no table rules at all."""
    left, right, top = frame(layout)
    sheet.setFont("Helvetica-Bold", 30)
    sheet.drawString(left, top - 8, layout.title)
    sheet.setLineWidth(0.5)
    sheet.line(left, top - 22, right, top - 22)

    cursor = stack(sheet, left, top - 42, "From", seller_lines(layout))
    stack(sheet, left, cursor - 6, "Bill to", [invoice.buyer])
    meta = top - 42
    for label, value in meta_rows(invoice, layout):
        sheet.setFont("Helvetica", 9)
        sheet.drawRightString(right, meta, f"{label}: {value}")
        meta -= 12
    sheet.drawRightString(right, meta, f"Currency: {invoice.currency}")

    cursor = airy_table(sheet, invoice, layout, min(cursor, meta) - 34)
    cursor = totals_plain(sheet, invoice, layout, cursor - 4)
    small_print(sheet, layout, left, cursor - 10)


def draw_qty_first(sheet, invoice: Invoice, layout: Layout) -> None:
    """A drawn mark, a dashed ledger, and the balance in a filled box."""
    left, right, top = frame(layout)
    sheet.setFillColorRGB(*layout.accent)
    sheet.circle(left + 11, top - 5, 11, stroke=0, fill=1)
    sheet.setFillColorRGB(0, 0, 0)
    sheet.setFont("Helvetica-Bold", 26)
    sheet.drawRightString(right, top - 12, layout.title.upper())

    cursor = stack(sheet, left, top - 44, "From", seller_lines(layout))
    stack(sheet, left, cursor - 6, "Bill to", [invoice.buyer])
    meta = top - 44
    for label, value in meta_rows(invoice, layout):
        sheet.setFont("Helvetica", 9)
        sheet.drawRightString(right - 110, meta, f"{label}:")
        sheet.setFont("Helvetica-Bold", 9)
        sheet.drawRightString(right, meta, value)
        meta -= 13
    sheet.setFont("Helvetica", 9)
    sheet.drawRightString(right - 110, meta, "Currency:")
    sheet.drawRightString(right, meta, invoice.currency)

    cursor = dashed_table(sheet, invoice, layout, min(cursor, meta) - 28)
    cursor = totals_in_box(sheet, invoice, layout, cursor - 8)
    small_print(sheet, layout, left, cursor - 6)


RENDERERS = {
    "column": draw_column,
    "split": draw_split,
    "ledger_wide": draw_ledger_wide,
    "form_grid": draw_form_grid,
    "banded": draw_banded,
    "boxed": draw_boxed,
    "minimal": draw_minimal,
    "qty_first": draw_qty_first,
}
