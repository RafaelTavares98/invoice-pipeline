"""Where invoices arrive, and how they come out of the envelope.

Two mailboxes answer the same two questions: which messages are here, and
what was attached to each. One reads a folder of mail files, which is what
the tests use. The other speaks IMAP to a real server.

Both hand back the same Message, so nothing downstream knows or cares which
one it is talking to.
"""

import email
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

MAIL_SUFFIX = '.eml'

#: Only these reach the pipeline. A signature image attached to every mail
#: is not an invoice, and reading it would cost a model call per message.
WANTED_SUFFIXES = ('.pdf',)


@dataclass
class Message:
    """One mail, reduced to what the pipeline needs from it."""

    identifier: str
    subject: str
    sender: str
    received_at: datetime
    attachments: list = field(default_factory=list)


class LocalMailbox:
    """A folder of mail files, used by the tests and for a dry run."""

    def __init__(self, folder):
        self.folder = Path(folder)

    def messages(self, prefix=''):
        """Every mail in the folder, oldest name first; only those whose
        name starts with prefix, when one is given."""
        if not self.folder.exists():
            return
        for path in sorted(self.folder.glob(f'{prefix}*{MAIL_SUFFIX}')):
            yield _read_message(path.read_bytes(), path.stem)


class ImapMailbox:
    """A real mailbox on a real server."""

    def __init__(self, host, user, password, folder='INBOX', subject=''):
        self.host = host
        self.user = user
        self.password = password
        self.folder = folder
        #: Only mail whose subject holds this text, when one is given.
        self.subject = subject

    def messages(self):
        """Every mail in the chosen folder, or every one with the subject."""
        import imaplib

        server = imaplib.IMAP4_SSL(self.host)
        try:
            server.login(self.user, self.password)
            server.select(self.folder, readonly=True)
            if self.subject:
                _, found = server.search(None, 'SUBJECT', f'"{self.subject}"')
            else:
                _, found = server.search(None, 'ALL')
            for number in found[0].split():
                _, data = server.fetch(number, '(RFC822)')
                yield _read_message(data[0][1], number.decode())
        finally:
            server.logout()


def write_message(folder, identifier, subject, attachments, sender='',
                  sent_at=None):
    """Put a mail with attachments into a folder mailbox. `sent_at`
    becomes its Date header, which is when it is taken to have arrived."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    mail = EmailMessage()
    mail['Subject'] = subject
    mail['From'] = sender or 'billing@example.invalid'
    mail['To'] = 'costs@moty.example'
    mail['Message-ID'] = f'<{identifier}@example.invalid>'
    if sent_at is not None:
        mail['Date'] = format_datetime(sent_at)
    mail.set_content('Invoice attached.')
    for name, payload in attachments:
        mail.add_attachment(
            payload, maintype='application', subtype='pdf', filename=name
        )
    target = folder / f'{identifier}{MAIL_SUFFIX}'
    target.write_bytes(mail.as_bytes())
    return target


def _read_message(raw, fallback_id):
    """Turn raw mail bytes into a Message."""
    parsed = email.message_from_bytes(raw)
    identifier = (parsed.get('Message-ID') or '').strip('<>')
    return Message(
        identifier=identifier.split('@')[0] or fallback_id,
        subject=parsed.get('Subject') or '',
        sender=parsed.get('From') or '',
        received_at=_arrived(parsed),
        attachments=_wanted_attachments(parsed),
    )


def _arrived(parsed):
    """The mail's own Date header; now, when it has none."""
    stamped = parsed.get('Date')
    if stamped:
        try:
            return parsedate_to_datetime(stamped)
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)


def _wanted_attachments(parsed):
    """Every attached file the pipeline knows how to read."""
    found = []
    for part in parsed.walk():
        name = part.get_filename()
        if not name or not name.lower().endswith(WANTED_SUFFIXES):
            continue
        found.append((name, part.get_payload(decode=True)))
    return found
