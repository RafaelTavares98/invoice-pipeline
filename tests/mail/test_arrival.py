"""When a mail arrived, and when its invoice was registered.

"Analysed the day it arrived" is a target, so both times are kept: the
arrival from the mail's own Date header, the registration from the clock
of whatever wrote the row.
"""

from datetime import datetime, timedelta, timezone

from business import issuers
from drawing import render
from mail import sources
from reading import intake
from simulation import builder

BRT = timezone(timedelta(hours=-3))
SENT = datetime(2026, 4, 7, 9, 30, tzinfo=BRT)


def _pdf(tmp_path):
    issuer = issuers.by_code('NCL')
    invoice = builder.invoice_for(issuer, seed=5)
    return render.build_invoice(tmp_path, invoice, issuer, name='a.pdf')


def test_a_mail_keeps_the_time_it_was_sent(tmp_path):
    pdf = _pdf(tmp_path)
    sources.write_message(tmp_path / 'inbox', 'm1', 'Invoice',
                          [(pdf.name, pdf.read_bytes())], sent_at=SENT)

    message = next(sources.LocalMailbox(tmp_path / 'inbox').messages())

    assert message.received_at == SENT


def test_a_mail_without_a_date_arrives_now(tmp_path):
    pdf = _pdf(tmp_path)
    sources.write_message(tmp_path / 'inbox', 'm1', 'Invoice',
                          [(pdf.name, pdf.read_bytes())])

    message = next(sources.LocalMailbox(tmp_path / 'inbox').messages())

    assert abs(message.received_at - datetime.now(timezone.utc)) < timedelta(minutes=1)


def test_the_registration_time_is_stored(tmp_path):
    store = intake.Store(tmp_path / 'data')
    store.take(_pdf(tmp_path).read_bytes(), 'a.pdf', SENT.isoformat(),
               registered_at='2026-04-07T09:31:05-03:00')

    assert store.invoices[0]['registered_at'] == '2026-04-07T09:31:05-03:00'
    assert store.invoices[0]['first_seen'] == SENT.isoformat()


def test_without_a_clock_the_wall_clock_registers_it(tmp_path):
    store = intake.Store(tmp_path / 'data')
    store.take(_pdf(tmp_path).read_bytes(), 'a.pdf', SENT.isoformat())

    written = datetime.fromisoformat(store.invoices[0]['registered_at'])
    assert abs(written - datetime.now(timezone.utc)) < timedelta(minutes=1)


def test_a_simulated_invoice_arrives_on_its_issue_date_in_brasilia():
    from mail import delivery
    invoice = builder.invoice_for(issuers.by_code('NCL'), seed=5)

    sent = delivery.sent_at(invoice, 1)

    assert sent.date() == invoice.issue_date
    assert sent.utcoffset() == timedelta(hours=-3)


def test_a_resend_arrives_days_later():
    from mail import delivery
    invoice = builder.invoice_for(issuers.by_code('NCL'), seed=5)

    assert (delivery.sent_at(invoice, 1, again=True).date()
            - invoice.issue_date).days == delivery.RESEND_DAYS


def test_a_replayed_mail_is_registered_after_it_arrived(tmp_path):
    pdf = _pdf(tmp_path)
    sources.write_message(tmp_path / 'inbox', 'm1', 'Invoice',
                          [(pdf.name, pdf.read_bytes())], sent_at=SENT)
    store = intake.Store(tmp_path / 'data')

    intake.replay(store, next(sources.LocalMailbox(tmp_path / 'inbox').messages()))

    registered = datetime.fromisoformat(store.invoices[0]['registered_at'])
    assert SENT <= registered < SENT + timedelta(minutes=1)
