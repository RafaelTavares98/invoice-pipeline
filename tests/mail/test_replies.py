"""Each sender answers Moty's request in its own habit.

How many PDFs a mail, how they are grouped, how soon the reply comes and
what the subject says are fixed per sender, so a run repeats. No reply
holds more than ten PDFs.
"""

from collections import defaultdict
from datetime import date

import pytest

from mail import replies
from simulation.operation import BACKLOG, Operation


@pytest.fixture(scope='module')
def run():
    return Operation(date(2026, 1, 1), profile=BACKLOG,
                     until=date(2026, 10, 14)).run()


@pytest.fixture(scope='module')
def answered(run):
    return replies.all_replies(run.invoices)


def test_every_sender_in_the_reference_has_a_habit():
    assert set(replies.HABITS) == {'NCL', 'SBP', 'GZV', 'HCV', 'BDT', 'ARL',
                                   'DHI', 'MRK', 'CSM', 'KNG', 'TLV', 'SCA',
                                   'TVA'}


def test_no_reply_holds_more_than_ten_pdfs(answered):
    for reply in answered:
        assert 1 <= len(reply.invoices) <= replies.MAX_PDFS


def test_a_reply_never_holds_more_than_its_senders_habit(answered):
    for reply in answered:
        assert len(reply.invoices) <= replies.habit_for(reply.code).per_mail


def test_every_document_is_sent_at_least_once(run, answered):
    sent = {id(i) for reply in answered for i in reply.invoices}
    assert all(id(i) in sent for i in run.invoices)


def test_a_monthly_sender_keeps_one_month_a_mail(answered):
    for reply in answered:
        if replies.habit_for(reply.code).grouped_by == 'month':
            assert len({i.issue_date.strftime('%Y-%m')
                        for i in reply.invoices}) == 1


def test_a_shipment_sender_keeps_one_shipment_a_mail(answered):
    for reply in answered:
        if replies.habit_for(reply.code).grouped_by == 'shipment':
            assert len({i.shipment_id for i in reply.invoices}) == 1


def test_a_kind_sender_keeps_one_kind_a_mail(answered):
    for reply in answered:
        if replies.habit_for(reply.code).grouped_by == 'kind':
            assert len({i.kind for i in reply.invoices}) == 1


def test_hcv_sends_one_invoice_a_mail_under_its_own_subject(answered):
    for reply in answered:
        if reply.code == 'HCV':
            invoice, = reply.invoices
            assert reply.subject == (f'Hanil // invoice {invoice.number} '
                                     f'// due {invoice.due_date.isoformat()}')


def test_a_two_round_sender_sends_some_documents_again(answered):
    by_round = defaultdict(set)
    for reply in answered:
        if replies.habit_for(reply.code).replies == 'two rounds':
            by_round[reply.round].update(i.number for i in reply.invoices)
    assert by_round[2]
    assert by_round[2] <= by_round[1]


def test_the_same_day_replies_come_first(answered):
    ranks = [replies.ORDER.index(reply.when) for reply in answered]
    assert ranks == sorted(ranks)


def test_the_replies_repeat(run):
    first = [(r.code, r.subject) for r in replies.all_replies(run.invoices)]
    second = [(r.code, r.subject) for r in replies.all_replies(run.invoices)]
    assert first == second


def test_the_watcher_leaves_the_smoke_test_mail_alone():
    """The project's one mailbox also holds the tutorial's smoke tests.
    The real run files the business's mail only."""
    from mail import watcher
    assert not watcher.is_business('Smoke test 2: Aravalli Labelworks Pvt. Ltd.')
    assert not watcher.is_business('Fwd: Smoke test 3: the file of one past shipment')
    assert watcher.is_business('BRIGHTPACK INVOICES March 2026')
    assert watcher.is_business('Re: Documents issued to Moty since 1 January 2026')
