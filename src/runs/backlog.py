"""Part 3 of the tutorial: the real run, 1 January to the run date.

    request   one request per sender, into Invoices/live/outbox/
    build     the business from 1 January to the run date, every document
              drawn into Invoices/live/<month>/, with ledger.json,
              labels.csv and erp/
    post      the senders' replies as .eml files, into Invoices/live/inbox/
    send      the same replies to the real mailbox, paced, under Gmail's
              daily limit, resumable through Invoices/live/sent.json

Nothing is dated after the run date.
"""

import json
import time
from datetime import date
from email.utils import formatdate
from pathlib import Path

from business import issuers
from drawing import render
from mail import delivery, replies
from mail.request import request_mail

#: Gmail lets a free account send about 500 mails a day; the run keeps a
#: margin and carries the rest over to the next day.
DAILY_LIMIT = 450

#: A message may not pass 25 MB on Gmail.
MAIL_LIMIT_BYTES = 25 * 1024 * 1024

#: The year the request asks about opens on 1 January.
OPENS = date(2026, 1, 1)


def live_folder(base):
    return Path(base) / 'Invoices' / 'live'


def _addresses(send):
    if send:
        return delivery.account_and_recipient()
    return 'local@example.invalid', 'costs@moty.example'


def request(base, send=False, deliver=None):
    """One request per sender, written into outbox/ and sent if asked."""
    outbox = live_folder(base) / 'outbox'
    outbox.mkdir(parents=True, exist_ok=True)
    account, recipient = _addresses(send)
    for code in replies.HABITS:
        mail = request_mail(issuers.by_code(code), account, recipient)
        (outbox / f'request-{code}.eml').write_bytes(mail.as_bytes())
        if send:
            (deliver or delivery.send_mail)(mail)
    return outbox


def build(base, until=None):
    """The business from 1 January to the run date, every document drawn
    into its month, the answer key and the desk's records beside them."""
    from simulation import erp, labels, ledger
    from simulation.operation import BACKLOG, Operation

    until = until or date.today()
    run = Operation(OPENS, profile=BACKLOG, until=until).run()
    live = live_folder(base)
    live.mkdir(parents=True, exist_ok=True)
    for invoice in run.invoices:
        month = live / invoice.issue_date.strftime('%Y-%m')
        month.mkdir(exist_ok=True)
        render.draw(month, invoice)
    (live / 'ledger.json').write_text(json.dumps(ledger.build(run), indent=2,
                                                 default=str),
                                      encoding='utf-8')
    erp.export(run, live / 'erp')
    labels.write(run, live)
    clock = live / 'clock.json'
    if not clock.exists():
        # The backlog covers the year up to the run date; live carries on
        # from the next day.
        clock.write_text(json.dumps({'through': until.isoformat()}),
                         encoding='utf-8')
    return run


def score(base):
    """What the reader filed from the mailbox, against ledger.json: every
    document once, right, flagged for a person, wrong or missing. Written
    to Invoices/live/score.json."""
    from reading import intake
    from runs import smoke
    live = live_folder(base)
    ledger = json.loads((live / 'ledger.json').read_text(encoding='utf-8'))
    truth = list({entry['number']: entry
                  for entry in ledger['invoices']}.values())
    found = smoke._score(intake.Store(live / 'data').invoices, truth)
    (live / 'score.json').write_text(json.dumps(found, indent=2),
                                     encoding='utf-8')
    return found


def daily(base, today=None, deliver=None, pause=1.5, on_sent=None):
    """The documents issued since the last run, up to today, each in a
    mail of its own, the day it is issued. clock.json remembers the last
    day brought, so a second run on one day sends nothing."""
    from simulation.operation import BACKLOG, Operation

    today = today or date.today()
    live = live_folder(base)
    clock = live / 'clock.json'
    through = date.fromisoformat(
        json.loads(clock.read_text(encoding='utf-8'))['through'])
    if today <= through:
        return []
    run = Operation(OPENS, profile=BACKLOG, until=today).run()
    new = sorted((i for i in run.invoices if through < i.issue_date <= today),
                 key=lambda i: (i.issue_date, i.number))
    account, recipient = _addresses(deliver is None)
    deliver = deliver or delivery.send_mail
    for invoice in new:
        month = live / invoice.issue_date.strftime('%Y-%m')
        month.mkdir(parents=True, exist_ok=True)
        issuer = issuers.by_code(invoice.issuer_code)
        pdf, _ = render.draw(month, invoice, issuer)
        mail = delivery.build_message(issuer, invoice, pdf, account, recipient)
        mail['Date'] = formatdate(localtime=True)
        mail['X-Reply-Id'] = f'live-{invoice.issuer_code}-{invoice.number}'
        deliver(mail)
        if on_sent:
            on_sent(mail)
        if pause:
            time.sleep(pause)
    clock.write_text(json.dumps({'through': today.isoformat()}),
                     encoding='utf-8')
    return new


def _pdf(base, invoice):
    return (live_folder(base) / invoice.issue_date.strftime('%Y-%m')
            / f'{invoice.number}.pdf')


def mails(base, run, account, recipient):
    """Every reply as a mail, in the order the senders send them. Each
    carries an id, so a stopped send knows what already went."""
    found = []
    for position, reply in enumerate(replies.all_replies(run.invoices),
                                     start=1):
        issuer = issuers.by_code(reply.code)
        pdfs = [_pdf(base, invoice) for invoice in reply.invoices]
        mail = delivery.build_mail(issuer.name, reply.code.lower(), account,
                                   recipient, reply.subject,
                                   _body(issuer, reply), pdfs)
        mail['Date'] = formatdate(localtime=True)
        mail['X-Reply-Id'] = f'{position:04d}-{reply.code}-r{reply.round}'
        if len(mail.as_bytes()) > MAIL_LIMIT_BYTES:
            raise ValueError(f'{mail["X-Reply-Id"]} passes 25 MB')
        found.append(mail)
    return found


def _body(issuer, reply):
    listed = '\n'.join(f'- {invoice.number}' for invoice in reply.invoices)
    again = ('\nSome of these were sent before; resent as asked.\n'
             if reply.round == 2 else '')
    return (f'Documents issued to Moty, as requested.\n\n{listed}\n{again}\n'
            f'{issuer.name}\n\n'
            'Invented by the invoice pipeline project. Not real data.\n')


def post(base, run):
    """The replies as .eml files in inbox/, no server."""
    inbox = live_folder(base) / 'inbox'
    inbox.mkdir(parents=True, exist_ok=True)
    for mail in mails(base, run, *_addresses(False)):
        (inbox / f'{mail["X-Reply-Id"]}.eml').write_bytes(mail.as_bytes())
    return inbox


def send(base, run, deliver=None, limit=DAILY_LIMIT, pause=1.5,
         on_sent=None):
    """The replies to the real mailbox, paced. sent.json keeps what went,
    so a run stopped by the daily limit, or by hand, resumes where it
    stopped and never sends one twice."""
    record_file = live_folder(base) / 'sent.json'
    record = (json.loads(record_file.read_text(encoding='utf-8'))
              if record_file.exists() else {'sent': []})
    done = set(record['sent'])
    account, recipient = _addresses(deliver is None)
    waiting = [mail for mail in mails(base, run, account, recipient)
               if mail['X-Reply-Id'] not in done]
    if deliver is not None:
        sent, stopped = _send_each(waiting[:limit], deliver, record,
                                   record_file, pause, on_sent)
    else:
        with delivery.Session() as session:
            sent, stopped = _send_each(waiting[:limit], session.send, record,
                                       record_file, pause, on_sent)
    return {'sent': sent, 'left': len(waiting) - sent, 'stopped': stopped}


#: What Gmail answers once an account has used up its day.
DAILY_LIMIT_REPLY = b'5.4.5'


def _send_each(waiting, deliver, record, record_file, pause, on_sent):
    """Send in order; stop cleanly at Gmail's daily limit, keeping what
    went in sent.json for the next run to carry on from."""
    import smtplib
    sent = 0
    for mail in waiting:
        try:
            deliver(mail)
        except smtplib.SMTPDataError as refused:
            if refused.smtp_code == 550 and DAILY_LIMIT_REPLY in refused.smtp_error:
                return sent, 'daily limit'
            raise
        record['sent'].append(mail['X-Reply-Id'])
        record_file.write_text(json.dumps(record, indent=2), encoding='utf-8')
        sent += 1
        if on_sent:
            on_sent(mail)
        if pause:
            time.sleep(pause)
    return sent, ''
