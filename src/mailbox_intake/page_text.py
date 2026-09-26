"""Getting the words off a page, whichever way they got on it.

A PDF that was typeset carries a text layer and can be read directly. A
PDF that is a photograph of a page carries none, and has to go through a
model that turns pixels into words.

The reader that does that is passed in, never imported here. That keeps
this module testable without installing an OCR engine, and lets the
choice of engine change without touching the pipeline.
"""

from pathlib import Path
from typing import Callable, List, Optional

TEXT_LAYER = "text_layer"
IMAGE_ONLY = "image_only"

#: A page with only a handful of stray characters is a scan with noise,
#: not a document. Below this, treat it as a picture and send it to OCR.
MINIMUM_CHARACTERS = 40

#: Tesseract's default segmentation hunts for columns, and on an invoice
#: it finds them: it returns the whole description column, then the whole
#: number column, so every row is torn from its own amounts. Mode 4 reads
#: the page as one column of text and keeps each row intact.
TESSERACT_CONFIG = "--psm 4"

#: An office scanner runs at 200 to 300 dots per inch. Reading a ruled
#: table of small figures needs more than that.
OCR_RESOLUTION = 400

#: A printed rule is a straight run of ink far longer than any letter. A
#: line of pixels darker than this, for at least this share of the page,
#: is the table's border and not a word.
INK = 160
RULE_SHARE = 0.25

#: A rule is thin. A filled band is not, and wiping one would take the
#: words printed on it with it. At 400 dots per inch even a heavy rule is
#: a few pixels; anything thicker is left alone.
RULE_THICKNESS = 12

#: What is left of a rule after it is erased: a stray upright mark the
#: engine reports as a pipe. It is a fragment of a border, not a word.
RULE_MARKS = "|¦"

#: Where the Windows installer puts the binary. It does not add itself to
#: PATH, so a machine with Tesseract installed still fails without this.
TESSERACT_FALLBACKS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
)


def classify(path: Path) -> str:
    """Say whether the page can be read directly or needs a model."""
    text = read_text_layer(path)
    if text is not None and len(text.strip()) >= MINIMUM_CHARACTERS:
        return TEXT_LAYER
    return IMAGE_ONLY


def read_text_layer(path: Path) -> Optional[str]:
    """Return the typeset text of a PDF, or None when it carries none."""
    import pdfplumber

    with pdfplumber.open(str(path)) as document:
        pages = [page.extract_text() or "" for page in document.pages]
    joined = "\n".join(pages)
    return joined if joined.strip() else None


def read_pages(
    path: Path, ocr_reader: Callable[[Path], str], kind: str = None
) -> List[str]:
    """Return the lines of a PDF, whichever way they have to be read.

    `ocr_reader` turns a page image into text. It is required, because a
    caller that forgot it would silently return nothing for every scan.

    `kind` is what `classify` already said about this file. A caller that
    asked once passes the answer in, because classifying opens and parses
    the whole document, and doing that twice for every page doubles the
    work of a run for nothing.
    """
    if (kind or classify(path)) == TEXT_LAYER:
        text = read_text_layer(path) or ""
    else:
        text = ocr_reader(path)
    return [line.strip() for line in text.splitlines() if line.strip()]


def tesseract_reader(path: Path) -> str:
    """Read a scanned PDF with a local Tesseract install."""
    import pdfplumber
    import pytesseract

    _point_at_tesseract(pytesseract)
    words = []
    with pdfplumber.open(str(path)) as document:
        for page in document.pages:
            image = page.to_image(resolution=OCR_RESOLUTION).original
            words.append(
                pytesseract.image_to_string(
                    _erase_rules(image), config=TESSERACT_CONFIG
                )
            )
    return _drop_rule_marks("\n".join(words))


def _erase_rules(image):
    """Paint out the table's borders before the engine reads the page.

    An engine handed a closed grid reads the borders as characters and
    loses the row behind them. Wiping the straight lines first costs
    nothing and is what a scanning desk does before it files a page.
    """
    import numpy
    from PIL import Image

    grey = numpy.array(image.convert("L"))
    dark = grey < INK
    height, width = dark.shape
    grey[_thin_lines(dark.sum(axis=1) >= width * RULE_SHARE), :] = 255
    grey[:, _thin_lines(dark.sum(axis=0) >= height * RULE_SHARE)] = 255
    return Image.fromarray(grey)


def _thin_lines(candidates):
    """Keep only the runs thin enough to be a rule and not a filled band."""
    import numpy

    kept = numpy.zeros_like(candidates)
    start = None
    for index, is_dark in enumerate(list(candidates) + [False]):
        if is_dark and start is None:
            start = index
        elif not is_dark and start is not None:
            if index - start <= RULE_THICKNESS:
                kept[start:index] = True
            start = None
    return kept


def _drop_rule_marks(text: str) -> str:
    """Remove the stray uprights a wiped border leaves behind."""
    for mark in RULE_MARKS:
        text = text.replace(mark, " ")
    return text


def _point_at_tesseract(pytesseract) -> None:
    """Find the binary when it is installed but not on PATH."""
    import shutil

    if shutil.which("tesseract"):
        return
    for candidate in TESSERACT_FALLBACKS:
        if Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return
