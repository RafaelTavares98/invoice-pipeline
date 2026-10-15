"""Modes are tested on text PDFs; OCR is tested where it is marked.

A live tick or a batch with scans spends most of its time in Tesseract.
What these tests check is the folders, the clock and the mail, not OCR,
so no issuer scans unless a test is marked `ocr` or `scans`.
"""

import pytest

from drawing import scan


@pytest.fixture(autouse=True)
def no_scans_unless_marked(request, monkeypatch):
    if not any(request.node.get_closest_marker(mark)
               for mark in ('ocr', 'scans')):
        monkeypatch.setattr(scan, 'HABITS', {})
