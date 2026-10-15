"""How each sender answers Moty's request for every document since
1 January.

Real senders do not agree on anything: one sends ten PDFs a mail, another
one; one groups by month, another by shipment; one answers the same day,
another in two rounds and sends some documents twice. The habits are
fixed per sender, so a run repeats.

No reply holds more than ten PDFs, and none passes Gmail's 25 MB limit
for a message; the sending side checks the size.
"""

from dataclasses import dataclass, field

#: Gmail's limit is 25 MB a message; ten PDFs keep a reply far under it.
MAX_PDFS = 10

REQUEST_SUBJECT = 'Documents issued to Moty since 1 January 2026'

#: When the replies arrive, first to last.
ORDER = ('the same day', 'within a week', 'two rounds')


@dataclass(frozen=True)
class Habit:
    per_mail: int
    grouped_by: str      # date, month, kind or shipment
    replies: str         # one of ORDER
    subject: str


HABITS = {
    'NCL': Habit(10, 'date', 'the same day', f'Re: {REQUEST_SUBJECT}'),
    'SBP': Habit(5, 'month', 'within a week', 'BRIGHTPACK INVOICES {month}'),
    'GZV': Habit(10, 'kind', 'two rounds',
                 'Commercial invoices - Guangzhou Verrelia ({n}/{total})'),
    'HCV': Habit(1, 'date', 'within a week',
                 'Hanil // invoice {number} // due {due}'),
    'BDT': Habit(10, 'month', 'the same day', 'Fwd: invoices {month}'),
    'ARL': Habit(5, 'date', 'two rounds',
                 'Aravalli Labelworks - Invoices, part {n}'),
    'DHI': Habit(10, 'shipment', 'the same day',
                 'DHI statement of invoices {n}'),
    'MRK': Habit(10, 'kind', 'within a week', 'Freight invoices, batch {n}'),
    'CSM': Habit(5, 'date', 'the same day',
                 'COSMO SHIPPING | INVOICES {n}/{total}'),
    'KNG': Habit(10, 'month', 'within a week', 'Rechnungen / Invoices {month}'),
    'TLV': Habit(10, 'month', 'the same day', f'Re: {REQUEST_SUBJECT}'),
    'SCA': Habit(5, 'shipment', 'within a week',
                 'SCA - documentos de importação, lote {n}'),
    'TVA': Habit(10, 'month', 'two rounds', 'Faturas de armazenagem {month}'),
}

#: A vendor that joined during the year answers plainly.
NEWCOMER = Habit(10, 'date', 'within a week', f'Re: {REQUEST_SUBJECT}')

def habit_for(code):
    return HABITS.get(code, NEWCOMER)


@dataclass
class Reply:
    code: str
    subject: str
    when: str
    round: int
    invoices: list = field(default_factory=list)


def _key(invoice, grouped_by):
    if grouped_by == 'month':
        return invoice.issue_date.strftime('%Y-%m')
    if grouped_by == 'kind':
        return invoice.kind
    if grouped_by == 'shipment':
        return invoice.shipment_id or invoice.number
    return ''


def _chunks(invoices, habit):
    """The sender's documents cut into mails: one group at a time, oldest
    first, at most per_mail a mail."""
    ordered = sorted(invoices, key=lambda i: (i.issue_date, i.number))
    groups = {}
    for invoice in ordered:
        groups.setdefault(_key(invoice, habit.grouped_by), []).append(invoice)
    size = min(habit.per_mail, MAX_PDFS)
    for group in groups.values():
        for start in range(0, len(group), size):
            yield group[start:start + size]


def _subject(habit, batch, n, total):
    first = batch[0]
    return habit.subject.format(
        month=first.issue_date.strftime('%B %Y'), n=n, total=total,
        number=first.number, due=first.due_date.isoformat())


def replies_of(code, invoices):
    """One sender's replies, in the order it sends them."""
    habit = habit_for(code)
    batches = list(_chunks(invoices, habit))
    found = [Reply(code, _subject(habit, batch, n, len(batches)),
                   habit.replies, 1, batch)
             for n, batch in enumerate(batches, start=1)]
    if habit.replies == 'two rounds' and invoices:
        last = max(i.issue_date for i in invoices).strftime('%Y-%m')
        again = [i for i in invoices if i.issue_date.strftime('%Y-%m') == last]
        batches = list(_chunks(again, habit))
        start = len(found)
        found += [Reply(code, _subject(habit, batch, start + n,
                                       start + len(batches)),
                        habit.replies, 2, batch)
                  for n, batch in enumerate(batches, start=1)]
    return found


def all_replies(invoices):
    """Every sender's replies: the same-day ones first, then those within
    a week, then the two-round senders, whose second round comes last."""
    by_code = {}
    for invoice in invoices:
        by_code.setdefault(invoice.issuer_code, []).append(invoice)
    found = []
    for code in sorted(by_code):
        found += replies_of(code, by_code[code])
    return sorted(found, key=lambda r: (ORDER.index(r.when), r.round))
