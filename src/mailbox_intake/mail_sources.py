"""Where invoices arrive, and how they come out of the envelope.

Two mailboxes answer the same two questions: which messages are here, and
what was attached to each. One reads a folder of mail files, which is what
the tests use. The other speaks IMAP to a real server.

Both hand back the same Message, so nothing downstream knows or cares
which one it is talking to.
"""

import email
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Iterator, List, Tuple

MAIL_SUFFIX = ".eml"

#: Only these reach the pipeline. A signature image attached to every mail
#: is not an invoice, and reading it would cost a model call per message.
WANTED_SUFFIXES = (".pdf",)


@dataclass
class Message:
    """One mail, reduced to what the pipeline needs from it."""

    identifier: str
    subject: str
    received_at: datetime
    attachments: List[Tuple[str, bytes]] = field(default_factory=list)


class LocalMailbox:
    """A folder of mail files, used by the tests and for a dry run."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def messages(self) -> Iterator[Message]:
        """Every mail in the folder, oldest name first."""
        if not self.folder.exists():
            return
        for path in sorted(self.folder.glob(f"*{MAIL_SUFFIX}")):
            yield _read_message(path.read_bytes(), path.stem)


class ImapMailbox:
    """A real mailbox on a real server."""

    def __init__(self, host: str, user: str, password: str,
                 folder: str = "INBOX"):
        self.host = host
        self.user = user
        self.password = password
        self.folder = folder

    def messages(self) -> Iterator[Message]:
        """Every mail in the chosen folder."""
        import imaplib

        server = imaplib.IMAP4_SSL(self.host)
        try:
            server.login(self.user, self.password)
            server.select(self.folder)
            _, found = server.search(None, "ALL")
            for number in found[0].split():
                _, data = server.fetch(number, "(RFC822)")
                yield _read_message(data[0][1], number.decode())
        finally:
            server.logout()


def write_message(
    folder: Path, identifier: str, subject: str,
    attachments: List[Tuple[str, bytes]]
) -> Path:
    """Put a mail with attachments into a folder mailbox."""
    folder.mkdir(parents=True, exist_ok=True)
    mail = EmailMessage()
    mail["Subject"] = subject
    mail["From"] = "billing@example.invalid"
    mail["To"] = "accounts@example.invalid"
    mail["Message-ID"] = f"<{identifier}@example.invalid>"
    mail.set_content("Invoice attached.")
    for name, payload in attachments:
        mail.add_attachment(
            payload, maintype="application", subtype="pdf", filename=name
        )
    target = folder / f"{identifier}{MAIL_SUFFIX}"
    target.write_bytes(mail.as_bytes())
    return target


def _read_message(raw: bytes, fallback_id: str) -> Message:
    """Turn raw mail bytes into a Message."""
    parsed = email.message_from_bytes(raw)
    identifier = (parsed.get("Message-ID") or "").strip("<>")
    return Message(
        identifier=identifier.split("@")[0] or fallback_id,
        subject=parsed.get("Subject") or "",
        received_at=datetime.now(timezone.utc),
        attachments=_wanted_attachments(parsed),
    )


def _wanted_attachments(parsed) -> List[Tuple[str, bytes]]:
    """Every attached file the pipeline knows how to read."""
    found = []
    for part in parsed.walk():
        name = part.get_filename()
        if not name or not name.lower().endswith(WANTED_SUFFIXES):
            continue
        found.append((name, part.get_payload(decode=True)))
    return found
