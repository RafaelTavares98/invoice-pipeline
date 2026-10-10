"""Posting the invented invoices to a real mailbox.

A folder of mail files proves the code works. A real server proves it works
where the mail actually lives, over the same protocol, with the same delays
and the same refusals.

Each issuer keeps its own name on the envelope. The address underneath is the
one account doing the sending, tagged so the ten can be told apart. A free
account cannot send from a domain it does not own, and pretending otherwise
gets the mail refused at the door.

Nothing here reads a password from a file, an argument or the environment.
The password lives in the operating system's own keychain, which encrypts it
and ties it to the owner's login. An environment variable would sit in plain
text in the registry, in the shell history, and in reach of every program
running as that user.

The program never prints the password and never asks for it. The owner types
it once, into the keychain's own tool:

    python -m keyring set invoice-pipeline <the sending address>
"""

import os
import smtplib
import ssl
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from buyer import MOTY

#: Where the account lives. The submission port, which requires the
#: connection to be encrypted before anything is sent.
SMTP_HOST = os.environ.get('INVOICE_SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('INVOICE_SMTP_PORT', '587'))

#: The sending address. This one is not a secret, so an environment
#: variable is the right home for it.
SMTP_USER = 'INVOICE_SMTP_USER'

#: Where the keychain files the password. The service name is the drawer,
#: the sending address is the label on it.
KEYCHAIN_SERVICE = 'invoice-pipeline'

#: Where the invoices are sent: the mailbox the pipeline then reads.
SMTP_RECIPIENT = 'INVOICE_SMTP_TO'

#: How each issuer writes its subject line. Real suppliers do not agree on
#: this either, and the intake has to cope.
SUBJECTS = {
    'NCL': 'Invoice {number} / {reference}',
    'SBP': 'BRIGHTPACK INVOICE {number}',
    'GZV': 'Commercial Invoice {number} - Guangzhou Verrelia',
    'HCV': 'Hanil // invoice {number} // due {due}',
    'BDT': 'Fwd: invoice {number}',
    'ARL': 'Aravalli Labelworks - Invoice no. {number}',
    'DHI': 'DHI {reference} - freight invoice {number}',
    'MRK': 'Freight invoice {number}',
    'CSM': 'COSMO SHIPPING | INVOICE {number} | {reference}',
    'KNG': 'Rechnung / Invoice {number}',
}


class MissingAccount(RuntimeError):
    """Raised when the sending account was never set in the environment."""


@dataclass(frozen=True)
class Delivery:
    """One invoice, on its way, and who it claims to be from."""

    invoice_number: str
    sender: str
    subject: str


def send_invoices(written, recipient=None, dry_run=False, pause=1.0,
                  on_sent=None):
    """Mail every invoice to a real address.

    `written` is what `run.py` produced: triples of issuer, invoice and the
    path of a PDF that already exists, so nothing is drawn a second time.

    `pause` is seconds between messages. A provider that sees a hundred
    messages in ten seconds treats the account as a nuisance.
    """
    account, password = _account()
    recipient = recipient or os.environ.get(SMTP_RECIPIENT) or account

    messages = [
        (invoice, build_message(issuer, invoice, pdf, account, recipient))
        for issuer, invoice, pdf in written
    ]
    sent = [Delivery(invoice.number, mail['From'], mail['Subject'])
            for invoice, mail in messages]
    if dry_run:
        return sent

    with _server(account, password) as server:
        for position, (invoice, mail) in enumerate(messages, start=1):
            server.send_message(mail)
            if on_sent:
                on_sent(position, len(messages), invoice)
            if pause and position < len(messages):
                time.sleep(pause)
    return sent


def build_message(issuer, invoice, pdf, account, recipient):
    """One mail, with the issuer's name on it and the invoice attached."""
    mail = EmailMessage()
    mail['From'] = sender_for(issuer, account)
    mail['To'] = recipient
    mail['Subject'] = subject_for(issuer, invoice)
    mail.set_content(_body(issuer, invoice))
    mail.add_attachment(
        Path(pdf).read_bytes(),
        maintype='application',
        subtype='pdf',
        filename=Path(pdf).name,
    )
    return mail


def sender_for(issuer, account):
    """The envelope: the issuer's name, over the one real address.

    `formataddr` does the quoting. Half these names hold a comma, and a
    comma pasted straight into a From header splits it into two addresses.
    """
    local, domain = account.split('@', 1)
    return formataddr((issuer.name, f'{local}+{tag_for(issuer)}@{domain}'))


def tag_for(issuer):
    """Everything after a plus sign is ignored on delivery, so all ten land
    in the one account while still being told apart by a filter."""
    return issuer.code.lower()


def subject_for(issuer, invoice):
    template = SUBJECTS.get(issuer.code, 'Invoice {number}')
    return template.format(
        number=invoice.number,
        reference=invoice.reference,
        due=invoice.due_date.isoformat(),
    )


def _body(issuer, invoice):
    return (
        f'Dear {MOTY.name},\n\n'
        f'Please find invoice {invoice.number} attached, '
        f'due {invoice.due_date.isoformat()}, '
        f'for {invoice.currency} {invoice.grand_total}.\n\n'
        f'{issuer.name}\n'
    )


def _account():
    """The sending account, or a message saying how to set it.

    The message says which command to run. It never repeats the address
    back, because an error goes into logs that get pasted into chats.
    """
    account = os.environ.get(SMTP_USER)
    if not account:
        raise MissingAccount(f'Set {SMTP_USER} to the sending address.')
    password = read_password(account)
    if not password:
        raise MissingAccount(
            f'No password in the keychain for that address. Store it with: '
            f'python -m keyring set {KEYCHAIN_SERVICE} <the sending address>. '
            f'Use the app password the provider issues for one program, '
            f'never the password to the account.'
        )
    return account, password


def read_password(account):
    """Take the password out of the keychain.

    The value is returned and never logged, never printed, and never written
    anywhere by this module.
    """
    import keyring

    return keyring.get_password(KEYCHAIN_SERVICE, account)


def _server(account, password):
    """An encrypted, logged-in connection to the mail server."""
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    server.starttls(context=ssl.create_default_context())
    server.login(account, password)
    return server
