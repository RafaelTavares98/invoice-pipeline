"""Turn one invoice into one .pdf file."""

from pathlib import Path

from reportlab.pdfgen import canvas

import issuers
import page_drawing
import page_styles
from layouts import layout_for


def build_invoice(folder, invoice=None, issuer=None, name=None):
    """Write the invoice into folder and return the path of the .pdf file."""
    if invoice is None:
        import invoice_builder
        issuer = issuer or issuers.FACTORIES[0]
        invoice = invoice_builder.invoice_for(issuer, seed=1)
    issuer = issuer or issuers.by_code(invoice.issuer_code)
    layout = layout_for(issuer)

    pdf_file = Path(folder) / (name or f'{invoice.number}.pdf')
    sheet = canvas.Canvas(str(pdf_file), pagesize=page_drawing.page_size(layout))
    sheet.setTitle(f'{layout.title} {invoice.number}')
    sheet.setAuthor(issuer.name)

    _, _, top = page_drawing.frame(layout)
    cursor = page_drawing.title_block(sheet, layout, invoice, top)
    cursor = page_drawing.parties_block(sheet, layout, invoice, cursor)

    cursor = page_styles.TABLES[layout.style](sheet, invoice, layout, cursor)
    cursor = page_styles.TOTALS[layout.style](sheet, invoice, layout, cursor)
    page_drawing.small_print(sheet, layout, cursor - 6)

    sheet.showPage()
    sheet.save()
    return pdf_file
