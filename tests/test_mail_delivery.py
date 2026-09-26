"""Mailing the invoices to a real address.

No test here opens a connection. What is tested is the envelope: that the
issuer's name reaches the recipient, that the address underneath is the
one real account, and that a missing account fails loudly instead of
sending nothing in silence.
"""

from pathlib import Path

import pytest

from invoice_generator.build_invoice import build_invoice, print_one
from invoice_generator import mail_delivery
from invoice_generator.mail_delivery import (
    SMTP_USER, TAGS, MissingAccount, build_message, send_invoices,
    sender_for, tag_for_layout,
)
from issuer_layouts import all_layouts, layout_for

ACCOUNT = "rafael@example.invalid"
ALL_CODES = sorted(all_layouts())


@pytest.fixture
def one_invoice(tmp_path):
    """One invoice of the first layout, already printed."""
    layout = layout_for("A")
    invoice = build_invoice(layout, 0)
    return invoice, print_one(invoice, layout, tmp_path, scan=False)


def test_the_issuers_name_is_what_the_recipient_sees():
    assert sender_for("Nordwind Handel GmbH", ACCOUNT).startswith(
        "Nordwind Handel GmbH <"
    )


def test_the_address_underneath_is_the_one_real_account():
    envelope = sender_for("Nordwind Handel GmbH", ACCOUNT)

    assert "rafael+germany@example.invalid" in envelope


@pytest.mark.parametrize("code", ALL_CODES)
def test_every_issuer_has_its_own_tag(code):
    assert tag_for_layout(layout_for(code)) == TAGS[code]


def test_no_two_issuers_share_a_tag():
    assert len(set(TAGS.values())) == len(TAGS)


def test_a_seller_nobody_listed_is_not_guessed():
    assert "+unknown@" in sender_for("Some Company Nobody Listed", ACCOUNT)


def test_the_invoice_is_attached(one_invoice):
    invoice, pdf = one_invoice

    message = build_message(invoice, pdf, ACCOUNT, "inbox@example.invalid")

    assert [p.get_filename() for p in message.iter_attachments()] == [
        pdf.name
    ]


def test_the_subject_carries_the_invoice_number(one_invoice):
    invoice, pdf = one_invoice

    message = build_message(invoice, pdf, ACCOUNT, "inbox@example.invalid")

    assert invoice.number in message["Subject"]


def test_the_body_names_the_buyer_and_the_due_date(one_invoice):
    invoice, pdf = one_invoice

    message = build_message(invoice, pdf, ACCOUNT, "inbox@example.invalid")
    body = message.get_body(("plain",)).get_content()

    assert invoice.buyer in body
    assert str(invoice.due_date) in body


def test_a_missing_address_stops_the_run(monkeypatch):
    """Sending with no address set says so, rather than sending nothing."""
    monkeypatch.delenv(SMTP_USER, raising=False)

    with pytest.raises(MissingAccount) as refused:
        send_invoices(_nothing_to_send())

    assert SMTP_USER in str(refused.value)


def test_an_empty_keychain_stops_the_run(monkeypatch):
    """A password that was never stored is named, not guessed around."""
    monkeypatch.setenv(SMTP_USER, ACCOUNT)
    monkeypatch.setattr(mail_delivery, "read_password", lambda _: None)

    with pytest.raises(MissingAccount) as refused:
        send_invoices(_nothing_to_send())

    assert "keyring set" in str(refused.value)


def test_the_password_never_comes_from_the_environment(monkeypatch):
    """An environment variable must not be able to stand in for the vault."""
    monkeypatch.setenv(SMTP_USER, ACCOUNT)
    monkeypatch.setenv("INVOICE_SMTP_PASSWORD", "not-the-way-in")
    monkeypatch.setattr(mail_delivery, "read_password", lambda _: None)

    with pytest.raises(MissingAccount):
        send_invoices(_nothing_to_send())


def test_no_address_reaches_the_error_message(monkeypatch):
    """An error is pasted into chats. It repeats nothing private."""
    monkeypatch.setenv(SMTP_USER, ACCOUNT)
    monkeypatch.setattr(mail_delivery, "read_password", lambda _: None)

    with pytest.raises(MissingAccount) as refused:
        send_invoices(_nothing_to_send())

    assert ACCOUNT not in str(refused.value)


def _nothing_to_send():
    """A filled mailbox with no invoices in it."""
    from invoice_generator.build_invoice import FilledMailbox

    return FilledMailbox(workspace=Path("."))
