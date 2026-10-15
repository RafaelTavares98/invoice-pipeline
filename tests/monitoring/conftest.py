"""The metrics are tested on text PDFs; OCR is tested where it is marked.

Every tick here ran OCR on its scans, which made these tests take 14
minutes. What they check is the counting, so no issuer scans unless a
test is marked `ocr`.
"""

import pytest

from drawing import scan


@pytest.fixture(autouse=True)
def no_scans_unless_marked(request, monkeypatch):
    if request.node.get_closest_marker('ocr') is None:
        monkeypatch.setattr(scan, 'HABITS', {})
