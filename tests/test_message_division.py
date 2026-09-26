"""Which messages this pipeline claims, and which it leaves alone.

The same mailbox feeds two readers. This one takes the mail that carries
an invoice file. The mail that only has words in its body belongs to the
reader that answers in words, and must still be there when it arrives.
"""

from pathlib import Path

import pytest

from mailbox_intake.attachment_store import fetch_new, read_manifest
from mailbox_intake.mail_sources import LocalMailbox, write_message


@pytest.fixture
def inbox(tmp_path):
    """A mailbox holding one invoice and one message with no file."""
    folder = tmp_path / "inbox"
    write_message(
        folder=folder,
        identifier="with-file",
        subject="Invoice A-2026-1000",
        attachments=[("invoice.pdf", b"%PDF-1.4 not a real page")],
    )
    write_message(
        folder=folder,
        identifier="words-only",
        subject="Order confirmation",
        attachments=[],
    )
    return folder, tmp_path / "raw"


def test_the_message_with_a_file_is_taken(inbox):
    folder, store = inbox

    taken = fetch_new(LocalMailbox(folder), store)

    assert [stored.message_id for stored in taken] == ["with-file"]


def test_the_message_with_no_file_is_left_alone(inbox):
    folder, store = inbox

    fetch_new(LocalMailbox(folder), store)

    assert "words-only" not in read_manifest(store)


def test_a_second_run_still_leaves_it_alone(inbox):
    """The other reader must find it however often this one runs."""
    folder, store = inbox

    fetch_new(LocalMailbox(folder), store)
    fetch_new(LocalMailbox(folder), store)

    assert list(read_manifest(store)) == ["with-file"]
