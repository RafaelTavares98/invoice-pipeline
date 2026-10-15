"""Moty's one request to each sender: every document since 1 January.

The real run starts here. Moty writes once to every sender that bills
it, and each one answers in its own habit (`replies.py`).
"""

from email.message import EmailMessage
from email.utils import formataddr, formatdate

from business.buyer import MOTY
from mail.replies import REQUEST_SUBJECT


def body(issuer):
    return (f'Dear {issuer.name},\n\n'
            'Please send every invoice and credit note you issued to Moty '
            'since 1 January 2026, as PDF.\n\n'
            f'{MOTY.department}\n{MOTY.name}\n\n'
            'Invented by the invoice pipeline project. Not real data.\n')


def request_mail(issuer, account, recipient):
    """The request to one sender. Every mail goes to the project's one
    mailbox; the sender it is meant for is named in the body and in a
    header, the way a filter would see it."""
    local, domain = account.split('@', 1)
    mail = EmailMessage()
    mail['From'] = formataddr((MOTY.name, f'{local}+moty@{domain}'))
    mail['To'] = recipient
    mail['Subject'] = REQUEST_SUBJECT
    mail['Date'] = formatdate(localtime=True)
    mail['X-Request-For'] = issuer.code
    mail.set_content(body(issuer))
    return mail
