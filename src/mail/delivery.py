"""Posting the invented invoices to a real mailbox.

A folder of mail files proves the code works. A real server proves it works
where the mail actually lives, over the same protocol, with the same delays
and the same refusals.

Each issuer keeps its own name on the envelope. The address underneath is the
one account doing the sending, tagged so every issuer can be told apart. A free
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
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from business.buyer import MOTY

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


def build_mail(name, tag, account, recipient, subject, body, pdfs):
    """One mail carrying several PDFs, under a display name, from the one
    account tagged so a filter can tell it apart."""
    local, domain = account.split('@', 1)
    mail = EmailMessage()
    mail['From'] = formataddr((name, f'{local}+{tag}@{domain}'))
    mail['To'] = recipient
    mail['Subject'] = subject
    mail.set_content(body)
    for pdf in pdfs:
        mail.add_attachment(Path(pdf).read_bytes(), maintype='application',
                            subtype='pdf', filename=Path(pdf).name)
    return mail


def send_mail(mail):
    """Send one built mail from the account in the keychain."""
    account, password = _account()
    with _server(account, password) as server:
        server.send_message(mail)


class Session:
    """One logged-in connection for many mails. Logging in for every mail
    made a backlog of hundreds take most of an hour. A dropped connection
    is opened again and the mail retried once."""

    def __enter__(self):
        self.account, self.password = _account()
        self.server = _server(self.account, self.password)
        return self

    def send(self, mail):
        try:
            self.server.send_message(mail)
        except smtplib.SMTPServerDisconnected:
            self.server = _server(self.account, self.password)
            self.server.send_message(mail)

    def __exit__(self, *_):
        try:
            self.server.quit()
        except smtplib.SMTPException:
            pass


def account_and_recipient():
    """The sending account and where the mail goes."""
    account, _ = _account()
    return account, os.environ.get(SMTP_RECIPIENT) or account


#: Brasilia time. The suppliers write from Asia overnight; the mail is on
#: the server when the department opens it.
BRT = timezone(timedelta(hours=-3))

#: A resent invoice comes back when nobody answered the first one.
RESEND_DAYS = 3


def sent_at(invoice, position, again=False):
    """When a simulated invoice reaches the inbox: on its issue date,
    spread across the working morning, or a few days later when it is a
    resend of a document already sent."""
    day = invoice.issue_date + timedelta(days=RESEND_DAYS if again else 0)
    return datetime(day.year, day.month, day.day, 8, 0, tzinfo=BRT) \
        + timedelta(minutes=(position * 7) % 480)


def sender_for(issuer, account):
    """The envelope: the issuer's name, over the one real address.

    `formataddr` does the quoting. Half these names hold a comma, and a
    comma pasted straight into a From header splits it into two addresses.
    """
    local, domain = account.split('@', 1)
    return formataddr((issuer.name, f'{local}+{tag_for(issuer)}@{domain}'))


def tag_for(issuer):
    """Everything after a plus sign is ignored on delivery, so every issuer lands
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
