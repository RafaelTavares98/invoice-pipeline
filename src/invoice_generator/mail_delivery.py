"""Posting the invented invoices to a real mailbox.

The folder mailbox proves the code works. A real server proves it works
where the client's mail actually lives, over the same protocol, with the
same delays and the same refusals.

Each issuer keeps its own name on the envelope. The address underneath is
the one account doing the sending, tagged so the eight can be told apart.
A free account cannot send from a domain it does not own, and pretending
otherwise gets the mail refused at the door.

Nothing here reads a password from a file, an argument or the
environment. The password lives in the operating system's own keychain,
which encrypts it and ties it to the owner's login. An environment
variable would sit in plain text in the registry, in the shell history,
and in reach of every program running as that user.

The program never prints the password and never asks for it. The owner
types it once, into the keychain's own tool:

    python -m keyring set invoice-pipeline <the sending address>
"""

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import List, Optional

from issuer_layouts import Layout

#: Where the account lives. The submission port, which requires the
#: connection to be encrypted before anything is sent.
SMTP_HOST = os.environ.get("INVOICE_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("INVOICE_SMTP_PORT", "587"))

#: The sending address. This one is not a secret, so an environment
#: variable is the right home for it.
SMTP_USER = "INVOICE_SMTP_USER"

#: Where the keychain files the password. The service name is the drawer,
#: the sending address is the label on it.
KEYCHAIN_SERVICE = "invoice-pipeline"

#: Where the invoices are sent: the mailbox the pipeline then reads.
SMTP_RECIPIENT = "INVOICE_SMTP_TO"

#: A short tag per issuer, added to the sending address. Everything after
#: a plus sign is ignored on delivery, so all eight land in the one
#: account while still being told apart by a filter or a later reader.
TAGS = {
    "A": "germany",
    "B": "usa",
    "C": "freight",
    "D": "hongkong",
    "E": "uk",
    "F": "customs",
    "G": "studio",
    "H": "workshop",
}


class MissingAccount(RuntimeError):
    """Raised when the sending account was never set in the environment."""


@dataclass(frozen=True)
class Delivery:
    """One invoice, on its way, and who it claims to be from."""

    invoice_number: str
    sender: str
    subject: str


def send_invoices(filled, recipient: Optional[str] = None) -> List[Delivery]:
    """Mail every invoice of a filled mailbox to a real address.

    `filled` is what `fill_mailbox` returned, so the PDFs already exist
    and nothing is drawn a second time.
    """
    account, password = _account()
    recipient = recipient or os.environ.get(SMTP_RECIPIENT) or account
    sent = []
    with _server(account, password) as server:
        for number, invoice in sorted(filled.invoices.items()):
            pdf = filled.workspace / f"{number}.pdf"
            message = build_message(invoice, pdf, account, recipient)
            server.send_message(message)
            sent.append(Delivery(number, message["From"], message["Subject"]))
    return sent


def build_message(invoice, pdf: Path, account: str, recipient: str):
    """One mail, with the issuer's name on it and the invoice attached."""
    mail = EmailMessage()
    mail["From"] = sender_for(invoice.seller, account)
    mail["To"] = recipient
    mail["Subject"] = f"Invoice {invoice.number}"
    mail.set_content(
        f"Dear {invoice.buyer},\n\n"
        f"Please find invoice {invoice.number} attached, "
        f"due {invoice.due_date}.\n\n"
        f"{invoice.seller}\n"
    )
    mail.add_attachment(
        pdf.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=pdf.name,
    )
    return mail


def sender_for(seller: str, account: str) -> str:
    """The envelope: the issuer's name, over the one real address."""
    tag = _tag_for(seller)
    name, domain = account.split("@", 1)
    return f"{seller} <{name}+{tag}@{domain}>"


def tag_for_layout(layout: Layout) -> str:
    """The tag this issuer's mail carries, for a filter or a later rule."""
    return TAGS.get(layout.code, layout.code.lower())


def _tag_for(seller: str) -> str:
    """Find the tag by the seller's name, since that is what a page gives."""
    from issuer_layouts import all_layouts

    for code, layout in all_layouts().items():
        if layout.seller == seller:
            return TAGS.get(code, code.lower())
    return "unknown"


def _account():
    """The sending account, or a message saying how to set it.

    The message says which command to run. It never repeats the address
    back, because an error goes into logs that get pasted into chats.
    """
    account = os.environ.get(SMTP_USER)
    if not account:
        raise MissingAccount(
            f"Set {SMTP_USER} to the sending address."
        )
    password = read_password(account)
    if not password:
        raise MissingAccount(
            f"No password in the keychain for that address. Store it "
            f"with: python -m keyring set {KEYCHAIN_SERVICE} "
            f"<the sending address>. Use the app password the provider "
            f"issues for one program, never the password to the account."
        )
    return account, password


def read_password(account: str) -> Optional[str]:
    """Take the password out of the keychain.

    The value is returned and never logged, never printed, and never
    written anywhere by this module.
    """
    import keyring

    return keyring.get_password(KEYCHAIN_SERVICE, account)


def _server(account: str, password: str):
    """An encrypted, logged-in connection to the mail server."""
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    server.starttls(context=ssl.create_default_context())
    server.login(account, password)
    return server
