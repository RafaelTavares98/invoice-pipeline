"""Getting the words off a page, and not doing it twice.

Classifying a page opens and parses the whole document. A caller that has
already done it says so, and this proves the second pass is skipped.
"""

from pathlib import Path

import pytest

from invoice_generator.build_invoice import build_invoice, print_one
from issuer_layouts import layout_for
from mailbox_intake import page_text
from mailbox_intake.page_text import (
    IMAGE_ONLY, TEXT_LAYER, classify, read_pages,
)


@pytest.fixture
def typeset(tmp_path):
    """One printed page that carries its text."""
    layout = layout_for("A")
    return print_one(build_invoice(layout, 0), layout, tmp_path, scan=False)


def refuse_to_ocr(path):
    raise AssertionError("a typeset page must not reach the engine")


def test_a_told_kind_is_not_worked_out_again(typeset, monkeypatch):
    def complain(path):
        raise AssertionError("classify was called a second time")

    monkeypatch.setattr(page_text, "classify", complain)

    assert read_pages(typeset, refuse_to_ocr, kind=TEXT_LAYER)


def test_a_kind_nobody_gave_is_worked_out(typeset):
    assert read_pages(typeset, refuse_to_ocr)


def test_a_page_told_to_be_a_scan_goes_to_the_engine(typeset):
    """The caller's word is taken, so a wrong answer is the caller's."""
    lines = read_pages(typeset, lambda path: "read by the engine",
                       kind=IMAGE_ONLY)

    assert lines == ["read by the engine"]


def test_a_typeset_page_is_recognised(typeset):
    assert classify(typeset) == TEXT_LAYER
