"""Some invoices arrive as scans: a picture of paper, no text inside.

Scanning is a habit of the issuer, not luck. Two print, sign and scan:

- ARL, the cheap label printer in India, scans most of its invoices on
  an old machine: black and white, low resolution, and often laid on
  the glass askew: still portrait, standing 75 to 90 degrees from the
  horizontal, so up to 15 degrees off upright;
- SCA, the broker in Santos, scans a signed copy now and then, on a good
  office scanner, straight.

Everyone else sends the PDF its system printed. Which invoice is scanned
is decided by its number, so a resend of a scan is the same scan. Every
scan is tilted, speckled and saved back as a PDF that holds only the
picture: nothing on it can be selected or copied.
"""

import hashlib
import io
import random
from pathlib import Path

import pypdfium2
from PIL import Image, ImageFilter

#: Stamped into every scan, so the same invoice gives the same bytes.
SCAN_DATE = 'D:20260101000000'

class Quality:
    """How one kind of scanner leaves a page."""

    def __init__(self, name, dpi, speckle, blur, jpeg, black_and_white):
        self.name = name
        self.dpi = dpi
        #: One speck for every this many pixels; smaller is dirtier.
        self.speckle = speckle
        self.blur = blur
        self.jpeg = jpeg
        self.black_and_white = black_and_white


QUALITIES = {
    'good': Quality('good', dpi=200, speckle=900, blur=0.4, jpeg=75,
                    black_and_white=False),
    # Low enough that OCR can mix up digits such as 8 and 6, still
    # readable by a person.
    'poor': Quality('poor', dpi=150, speckle=500, blur=0.0, jpeg=None,
                    black_and_white=True),
}


class Habit:
    """How one issuer scans: how often, how badly, how often askew."""

    def __init__(self, share, quality, askew):
        self.share = share
        self.quality = quality
        self.askew = askew


HABITS = {
    'ARL': Habit(share=0.6, quality='poor', askew=0.5),
    'SCA': Habit(share=0.3, quality='good', askew=0.0),
}


def _fraction(number, salt):
    digest = hashlib.sha256(f'{salt}:{number}'.encode('utf-8')).digest()
    return int.from_bytes(digest[:4], 'big') / 2 ** 32


def _habit(number):
    return HABITS.get(str(number).split('-')[0])


def chosen(number):
    """Whether this invoice number arrives as a scan. Never changes."""
    habit = _habit(number)
    return habit is not None and _fraction(number, 'scan') < habit.share


def quality(number):
    """Which scanner this invoice went through. Never changes."""
    habit = _habit(number)
    return QUALITIES[habit.quality if habit else 'good']


#: How far an askew page is turned off upright, in degrees: it stands 75
#: to 90 degrees from the horizontal.
ASKEW_DEGREES = (0.0, 15.0)


def askew(number):
    """Whether the page was fed into the scanner askew."""
    habit = _habit(number)
    return habit is not None and _fraction(number, 'askew') < habit.askew


def askew_degrees(seed):
    """How far the page turned off upright, up to 15 degrees, either way."""
    rng = random.Random(f'askew:{seed}')
    return rng.choice((-1, 1)) * rng.uniform(*ASKEW_DEGREES)


def render_page(pdf_path, dpi=200):
    """The first page of the PDF as a greyscale picture."""
    document = pypdfium2.PdfDocument(str(pdf_path))
    try:
        image = document[0].render(scale=dpi / 72).to_pil()
    finally:
        document.close()
    return image.convert('L')


def tilt_degrees(seed):
    rng = random.Random(seed)
    return rng.choice((-1, 1)) * rng.uniform(0.3, 1.4)


def degrade(page, seed, quality=QUALITIES['good']):
    """Tilt, speckle and soften a page the way this scanner does."""
    rng = random.Random(seed)
    page = page.rotate(tilt_degrees(seed), resample=Image.BICUBIC,
                       expand=True, fillcolor=255)
    pixels = page.load()
    width, height = page.size
    for _ in range(width * height // quality.speckle):
        x, y = rng.randrange(width), rng.randrange(height)
        pixels[x, y] = rng.choice((0, 60, 200))
    if quality.blur:
        page = page.filter(ImageFilter.GaussianBlur(radius=quality.blur))
    if quality.black_and_white:
        # A high cut keeps thin grey strokes black, as cheap scanners do.
        page = page.point(lambda value: 255 if value > 190 else 0, mode='1')
    return page


def _trimmed(page, pad=20):
    """The clean page cut down to its printed part, plus a little white."""
    from PIL import ImageOps
    printed = ImageOps.invert(page).getbbox()
    if not printed:
        return page
    return page.crop((max(printed[0] - pad, 0), max(printed[1] - pad, 0),
                      min(printed[2] + pad, page.width),
                      min(printed[3] + pad, page.height)))


#: An A4 sheet in inches, portrait, and the white border a scanner leaves
#: around its reading area, as a share of each side.
A4_INCHES = (8.27, 11.69)
READING_MARGIN = 0.04


def a4_sheet(dpi):
    """The pixel size of a portrait A4 sheet at dpi."""
    return round(A4_INCHES[0] * dpi), round(A4_INCHES[1] * dpi)


def _laid_askew(page, seed, sheet):
    """The page turned on the glass, scanned onto a portrait A4 sheet:
    turned, shrunk only as much as it must to sit wholly inside the
    reading area, centred on white. Nothing printed falls off the edge."""
    white = 1 if page.mode == '1' else 255
    turned = page.rotate(askew_degrees(seed), expand=True, fillcolor=white)
    width, height = sheet
    room_w = width * (1 - 2 * READING_MARGIN)
    room_h = height * (1 - 2 * READING_MARGIN)
    fit = min(1.0, room_w / turned.width, room_h / turned.height)
    turned = turned.resize((int(turned.width * fit), int(turned.height * fit)))
    glass = Image.new(page.mode, (width, height), white)
    glass.paste(turned, ((width - turned.width) // 2,
                         (height - turned.height) // 2))
    return glass


def scan(pdf_path, seed, chosen_quality=None, fed_askew=False):
    """Replace the PDF with a scan of itself. Returns the same path."""
    pdf_path = Path(pdf_path)
    grade = chosen_quality or quality(str(seed))
    page = render_page(pdf_path, dpi=grade.dpi)
    sheet = a4_sheet(grade.dpi)
    if fed_askew:
        # Trimmed before the dirt, or every speck would count as print.
        page = _trimmed(page)
    page = degrade(page, seed, grade)
    if fed_askew:
        page = _laid_askew(page, seed, sheet)
    if grade.jpeg:
        squeezed = io.BytesIO()
        page.save(squeezed, format='JPEG', quality=grade.jpeg)
        squeezed.seek(0)
        page = Image.open(squeezed)
    # A fixed date: the same invoice must give the same bytes, or a resend
    # of a scan would look like a new document.
    page.save(pdf_path, format='PDF', resolution=float(grade.dpi),
              creationDate=SCAN_DATE, modDate=SCAN_DATE)
    return pdf_path
