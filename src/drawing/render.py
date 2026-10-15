"""Turn one invoice into one .pdf file, the way the issuer sent it.

`draw` is the generator every run uses: it prints the page and then lets
the issuer's scanning habit decide, from the invoice number alone,
whether this one arrives as a scan, how badly, and whether fed in askew.
Nobody picks scans by hand.
"""

from pathlib import Path

from reportlab.pdfgen import canvas

from business import issuers
from drawing import parts
from drawing import styles
from drawing.layouts import layout_for


def draw(folder, invoice, issuer=None, name=None):
    """The PDF as it arrives, and the scanner it went through: '' for a
    printed page, or the scan quality's name."""
    from drawing import scan
    pdf = build_invoice(folder, invoice, issuer, name)
    if not scan.chosen(invoice.number):
        return pdf, ''
    grade = scan.quality(invoice.number)
    scan.scan(pdf, seed=invoice.number, chosen_quality=grade,
              fed_askew=scan.askew(invoice.number))
    return pdf, grade.name


def build_invoice(folder, invoice=None, issuer=None, name=None):
    """Write the invoice into folder and return the path of the .pdf file."""
    if invoice is None:
        from simulation import builder
        issuer = issuer or issuers.FACTORIES[0]
        invoice = builder.invoice_for(issuer, seed=1)
    issuer = issuer or issuers.by_code(invoice.issuer_code)
    layout = layout_for(issuer, invoice.kind)

    pdf_file = Path(folder) / (name or f'{invoice.number}.pdf')
    # Invariant: no timestamp or random id inside, so a resend of the same
    # invoice is the same file, byte for byte.
    sheet = canvas.Canvas(str(pdf_file), pagesize=parts.page_size(layout),
                          invariant=1)
    sheet.setTitle(f'{layout.title} {invoice.number}')
    sheet.setAuthor(issuer.name)

    _, _, top = parts.frame(layout)
    cursor = parts.title_block(sheet, layout, invoice, top)
    cursor = parts.parties_block(sheet, layout, invoice, cursor)

    cursor = styles.TABLES[layout.style](sheet, invoice, layout, cursor)
    cursor = styles.TOTALS[layout.style](sheet, invoice, layout, cursor)
    parts.small_print(sheet, layout, cursor - 6, invoice.pay_to)

    sheet.showPage()
    sheet.save()
    return pdf_file
