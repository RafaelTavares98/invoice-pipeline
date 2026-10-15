"""Turning a scanned page back into text, for the same blind reader.

OCR only replaces the missing text layer. It knows nothing of issuers or
layouts; the field reader works on whatever OCR saw, exactly as it works
on a text PDF.
"""

import io
import shutil
from pathlib import Path

#: Where the Windows installer puts Tesseract when it is not on PATH.
WINDOWS_TESSERACT = Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe')

def tesseract():
    """The Tesseract program, or None when this machine has none."""
    found = shutil.which('tesseract')
    if found:
        return found
    if WINDOWS_TESSERACT.exists():
        return str(WINDOWS_TESSERACT)
    return None


#: The ways a page is read, cheapest and most often right first: the
#: rendering resolution, how the picture is cleaned, and Tesseract's
#: page-segmentation mode.
PASSES = ((300, 'plain', 3), (300, 'smooth', 6), (300, 'plain', 6),
          (400, 'clean', 3), (300, 'binary', 4), (400, 'binary', 6),
          (300, 'plain', 4))


def _cleaned(page, how):
    from PIL import ImageFilter, ImageOps
    if how == 'smooth':
        # A black-and-white scan blown up from 150 dpi has stair-step
        # edges; softened, Tesseract reads its digits far better.
        return page.filter(ImageFilter.GaussianBlur(1.5))
    if how == 'clean':
        return ImageOps.autocontrast(page.filter(ImageFilter.MedianFilter(3)))
    if how == 'binary':
        return ImageOps.autocontrast(page).point(
            lambda value: 255 if value > 160 else 0)
    return page


#: The widest turn looked for, either way, and how finely, in degrees.
SKEW_LIMIT = 16.0
SKEW_STEPS = (1.0, 0.1)


def _row_contrast(ink, angle):
    """How sharply the rows of print stand out once the page is turned
    back by angle: straight rows of text give rows of all ink and rows of
    none, so the sums swing hard; slanted rows smear them flat."""
    import numpy
    from PIL import Image
    turned = ink.rotate(-angle, resample=Image.NEAREST, fillcolor=0)
    return float(numpy.asarray(turned, dtype=numpy.float32).sum(axis=1).var())


def skew_of(page):
    """How many degrees the print stands turned, counterclockwise: the
    turn that, undone, makes its rows of text level. Coarse search across
    the whole range, then fine around the best."""
    from PIL import ImageOps
    small = page.convert('L')
    small = small.resize((600, round(600 * small.height / small.width)))
    ink = ImageOps.invert(small).point(lambda value: 255 if value > 96 else 0)
    best, span = 0.0, SKEW_LIMIT
    for step in SKEW_STEPS:
        angles = [best + step * n
                  for n in range(-int(span / step), int(span / step) + 1)]
        best = max(angles, key=lambda angle: _row_contrast(ink, angle))
        span = step
    return round(best, 1)


def level(page):
    """The page turned back so its rows of text run straight across."""
    angle = skew_of(page)
    if abs(angle) < 0.3:
        return page
    return page.rotate(-angle, expand=True, fillcolor=255)


def _pages(payload, dpi):
    """Every page rendered in grey at dpi, each levelled."""
    import pypdfium2
    document = pypdfium2.PdfDocument(io.BytesIO(payload))
    try:
        pages = [document[n].render(scale=dpi / 72).to_pil().convert('L')
                 for n in range(len(document))]
    finally:
        document.close()
    return [level(page) for page in pages]


def readings(payload):
    """The page read once per pass, lazily: a caller that is satisfied
    with the first reading pays for one pass only."""
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = tesseract()
    rendered = {}
    for dpi, how, psm in PASSES:
        if dpi not in rendered:
            rendered[dpi] = _pages(payload, dpi)
        yield '\n'.join(pytesseract.image_to_string(_cleaned(page, how),
                                                    config=f'--psm {psm}')
                        for page in rendered[dpi])

