"""Waiting for the next invoice instead of asking for it.

IMAP has a command called IDLE. The connection is opened, the folder is
selected, and then the client stops talking. The server pushes a line the
moment a message lands. That is a real trigger, not a clock.

Three things go wrong with it, and all three are handled here:

    Gmail hangs up on an idle connection after about half an hour, so the
    IDLE is renewed every ten minutes before the server loses patience.

    The connection drops. The watcher reconnects, waiting longer each
    time, so a server that is down is not hammered.

    A push can be missed. A full sweep runs every hour regardless, and
    the hash in the store makes a second look harmless.

Nothing here knows how to read a PDF. It hands bytes to `intake.Store`.
"""

import os
import time
from dataclasses import dataclass

from imapclient import IMAPClient

from mail import delivery

IMAP_HOST = os.environ.get('INVOICE_IMAP_HOST', 'imap.gmail.com')
FOLDER = os.environ.get('INVOICE_IMAP_FOLDER', 'INBOX')

#: Renewed before the server's own limit, which Gmail puts near 29 minutes.
IDLE_RENEW_SECONDS = 10 * 60

#: The safety net, in case a push never arrived.
SWEEP_SECONDS = 60 * 60

#: How long to wait after a dropped connection, doubling up to the last.
BACKOFF_SECONDS = (5, 15, 45, 120, 300)

WANTED_SUFFIX = '.pdf'

#: The tutorial's smoke tests share the project's mailbox. Their mail is
#: read by the smoke steps, never filed as the business's.
SMOKE_MARK = 'Smoke test'


def is_business(subject):
    """Whether a mail belongs to the real run, not to a smoke test."""
    return SMOKE_MARK not in (subject or '')


@dataclass
class Arrival:
    uid: int
    subject: str
    sender: str
    filename: str
    payload: bytes
    received_at: str


def watch(store, on_arrival=None, stop_after=None):
    """Sit on the mailbox and feed everything new into the store.

    `stop_after` ends the loop after that many pushes, which is how the
    tests drive it. Left alone, it runs until interrupted.
    """
    pushes = 0
    attempt = 0
    while True:
        try:
            with _connected() as server:
                attempt = 0
                _drain(server, store, on_arrival)
                last_sweep = time.monotonic()
                while True:
                    server.idle()
                    server.idle_check(timeout=IDLE_RENEW_SECONDS)
                    server.idle_done()
                    _drain(server, store, on_arrival)
                    pushes += 1
                    if time.monotonic() - last_sweep > SWEEP_SECONDS:
                        _sweep(server, store, on_arrival)
                        last_sweep = time.monotonic()
                    if stop_after and pushes >= stop_after:
                        return store
        except KeyboardInterrupt:
            return store
        except Exception:
            wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
            attempt += 1
            time.sleep(wait)


def _connected():
    account, password = delivery._account()
    server = IMAPClient(IMAP_HOST, ssl=True)
    server.login(account, password)
    server.select_folder(FOLDER)
    return server


def _drain(server, store, on_arrival):
    """Everything with a higher UID than the last one taken."""
    last = int(store.state.get('last_uid', 0))
    uids = server.search(['UID', f'{last + 1}:*'])
    uids = [uid for uid in uids if uid > last]
    _take(server, store, uids, on_arrival)


def _sweep(server, store, on_arrival):
    """Everything in the folder, in case a push went missing."""
    _take(server, store, server.search(['ALL']), on_arrival)


def _take(server, store, uids, on_arrival):
    if not uids:
        return
    fetched = server.fetch(uids, ['RFC822', 'INTERNALDATE'])
    for uid in sorted(uids):
        held = fetched.get(uid)
        if not held:
            continue
        for arrival in _attachments(uid, held):
            outcome = store.take(arrival.payload, arrival.filename,
                                 arrival.received_at, arrival.sender)
            if on_arrival:
                on_arrival(arrival, outcome)
        store.state['last_uid'] = max(int(store.state.get('last_uid', 0)), uid)
    store.save()


def _attachments(uid, held):
    import email
    import email.policy

    parsed = email.message_from_bytes(held[b'RFC822'],
                                      policy=email.policy.default)
    # The server's arrival time, in this machine's zone with its offset.
    received = held[b'INTERNALDATE'].astimezone().isoformat(timespec='seconds')
    if not is_business(parsed.get('Subject')):
        return
    for part in parsed.walk():
        name = part.get_filename()
        if not name or not name.lower().endswith(WANTED_SUFFIX):
            continue
        yield Arrival(
            uid=uid,
            subject=parsed.get('Subject') or '',
            sender=parsed.get('From') or '',
            filename=name,
            payload=part.get_payload(decode=True),
            received_at=received,
        )
