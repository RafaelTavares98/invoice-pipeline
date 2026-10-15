"""Part 3 of the tutorial: the request, the backlog, the replies.

These tests use a short period and post to a folder; the real run sends
the same mails to Gmail.
"""

import email
import json
from datetime import date

import pytest

from runs import backlog

UNTIL = date(2026, 3, 31)

#: The period is drawn with ARL's and SCA's scans, as the real run is.
pytestmark = pytest.mark.scans


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp('base')
    return base, backlog.build(base, UNTIL)


def test_the_request_goes_to_every_sender(tmp_path):
    outbox = backlog.request(tmp_path)
    mails = [email.message_from_bytes(p.read_bytes())
             for p in outbox.glob('*.eml')]

    assert len(mails) == 13
    assert all(m['Subject'] == 'Documents issued to Moty since 1 January 2026'
               for m in mails)
    assert outbox.parts[-3:] == ('Invoices', 'live', 'outbox')


def test_every_document_is_drawn_into_its_month(built):
    base, run = built
    live = base / 'Invoices' / 'live'
    for invoice in run.invoices:
        assert (live / invoice.issue_date.strftime('%Y-%m')
                / f'{invoice.number}.pdf').exists(), invoice.number


def test_the_answer_key_and_the_records_are_written(built):
    base, _ = built
    live = base / 'Invoices' / 'live'
    assert (live / 'ledger.json').exists()
    assert (live / 'labels.csv').exists()
    assert (live / 'erp' / 'items.csv').exists()


def test_nothing_is_dated_after_the_run_date(built):
    _, run = built
    assert max(i.issue_date for i in run.invoices) <= UNTIL


def test_the_posted_replies_carry_every_document(built):
    base, run = built
    inbox = backlog.post(base, run)
    attached = set()
    for path in inbox.glob('*.eml'):
        mail = email.message_from_bytes(path.read_bytes())
        names = [p.get_filename() for p in mail.walk() if p.get_filename()]
        assert 1 <= len(names) <= 10
        assert path.stat().st_size < 25 * 1024 * 1024
        attached.update(names)
    assert {f'{i.number}.pdf' for i in run.invoices} <= attached


def test_a_stopped_send_resumes_without_sending_twice(built, tmp_path):
    base, run = built
    sent = []
    backlog.send(base, run, deliver=sent.append, limit=5, pause=0)
    backlog.send(base, run, deliver=sent.append, limit=10_000, pause=0)

    subjects = [m['X-Reply-Id'] for m in sent]
    assert len(subjects) == len(set(subjects))
    record = json.loads((base / 'Invoices' / 'live' / 'sent.json')
                        .read_text(encoding='utf-8'))
    assert len(record['sent']) == len(sent)


def test_the_daily_limit_stops_the_send(built):
    base, run = built
    (base / 'Invoices' / 'live' / 'sent.json').unlink(missing_ok=True)
    sent = []
    backlog.send(base, run, deliver=sent.append, limit=3, pause=0)

    assert len(sent) == 3


def test_live_brings_only_what_was_issued_since_the_last_run(built):
    """After the backlog, each new document comes in a mail of its own,
    on the day it is issued; running twice a day sends nothing twice."""
    base, run = built
    sent = []
    first = backlog.daily(base, date(2026, 4, 3), deliver=sent.append, pause=0)
    again = backlog.daily(base, date(2026, 4, 3), deliver=sent.append, pause=0)

    assert first and not again
    assert len(sent) == len(first)
    for invoice in first:
        assert date(2026, 4, 1) <= invoice.issue_date <= date(2026, 4, 3)
    assert all(len([p for p in m.walk() if p.get_filename()]) == 1
               for m in sent)


def test_the_simulated_live_ticks_stay_out_of_the_real_run(tmp_path):
    from runs import modes
    assert modes.folder_for(tmp_path, 'live').parts[-2:] == ('samples', 'live')


def test_the_real_run_is_scored_against_the_ledger(built):
    """Every document of the period, read back from the replies, against
    the answer key: none missing, none wrong in silence."""
    from mail import sources
    from reading import intake
    base, run = built
    inbox = backlog.post(base, run)
    store = intake.Store(backlog.live_folder(base) / 'data')
    for message in sources.LocalMailbox(inbox).messages():
        intake.replay(store, message)
    store.save()

    score = backlog.score(base)

    assert score['pdfs'] == len({i.number for i in run.invoices})
    assert score['missing'] == [] and score['wrong'] == []
    written = backlog.live_folder(base) / 'score.json'
    assert json.loads(written.read_text(encoding='utf-8'))['pdfs'] == score['pdfs']


def test_gmails_daily_limit_stops_the_send_cleanly(built):
    """Gmail refuses with 550 5.4.5 once the account's day is used up. The
    send stops there, keeps what went, and says how many are left."""
    import smtplib
    base, run = built
    (base / 'Invoices' / 'live' / 'sent.json').unlink(missing_ok=True)
    sent = []

    def refusing(mail):
        if len(sent) == 2:
            raise smtplib.SMTPDataError(
                550, b'5.4.5 Daily user sending limit exceeded.')
        sent.append(mail)

    outcome = backlog.send(base, run, deliver=refusing, pause=0)

    assert outcome['sent'] == 2 and outcome['stopped'] == 'daily limit'
    assert outcome['left'] == len(backlog.mails(base, run, 'a@b.c', 'd')) - 2
