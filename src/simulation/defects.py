"""The things suppliers get wrong, on purpose.

A corpus of clean invoices teaches a reader nothing. What breaks a naive
pipeline is the duplicate, the revision that keeps the old number, the
credit note with a negative total, and the purchase order quoted wrong.

Every defect here is one a freight desk sees in a normal month.
"""

import copy
from datetime import timedelta
from decimal import Decimal

DUPLICATE_CHANCE = 0.06
REVISION_CHANCE = 0.05
CREDIT_CHANCE = 0.04
WRONG_ORDER_CHANCE = 0.07


def after(rng, invoice, issuer, next_number):
    """Whatever else this invoice drags along behind it."""
    extras = []
    if invoice.kind == 'credit':
        return extras

    if rng.random() < DUPLICATE_CHANCE:
        extras.append(_duplicate(rng, invoice))
    # An invoice that was billed again under a new number must not then
    # be revised: the duplicate would repeat a total the original no
    # longer carries, and it would be a duplicate of nothing.
    if not getattr(invoice, 'billed_again', False) \
            and rng.random() < REVISION_CHANCE:
        extras.append(_revision(rng, invoice))
    if invoice.kind == 'goods' and rng.random() < CREDIT_CHANCE:
        extras.append(_credit_note(rng, invoice, issuer, next_number))
    return extras


def quoted_order(rng, order_number, orders):
    """The purchase order as the supplier typed it, which is not always
    the one it should be."""
    if rng.random() < WRONG_ORDER_CHANCE and len(orders) > 1:
        other = rng.choice(orders).number
        if other != order_number:
            return other
    return order_number


def _duplicate(rng, invoice):
    """The same document, sent again because nobody replied.

    Nothing about the page changes, not even the date it bears. Only the
    delivery is later. That is what makes it a duplicate rather than a
    revision: the bytes are identical, so the hash catches it and no
    second row is written.
    """
    return copy.deepcopy(invoice)


def _revision(rng, invoice):
    """A corrected invoice. The supplier keeps the number and adds a
    suffix, so two documents claim the same identity."""
    copied = copy.deepcopy(invoice)
    copied.number = f'{invoice.number}-R1'
    copied.revises = invoice.number
    copied.issue_date = invoice.issue_date + timedelta(days=rng.randint(3, 12))
    if copied.lines:
        line = rng.choice(copied.lines)
        line.quantity = Decimal(
            max(1, int(float(line.quantity) * rng.uniform(0.6, 0.95))))
    return copied


def _credit_note(rng, invoice, issuer, next_number):
    """Money back for a batch that failed inspection."""
    day = invoice.issue_date + timedelta(days=rng.randint(10, 35))
    faulty = rng.choice([line for line in invoice.lines if line.code]
                        or invoice.lines)
    share = Decimal(max(1, int(float(faulty.quantity) * rng.uniform(0.02, 0.12))))

    credited = copy.deepcopy(faulty)
    credited.quantity = -share
    credited.description = f'Credit, rejected batch: {faulty.description}'
    credited.weight_kg = Decimal('0.00')

    note = copy.deepcopy(invoice)
    note.number = next_number(issuer, day).replace('-', '-CN-', 1)
    note.issue_date = day
    note.due_date = day
    note.kind = 'credit'
    note.lines = [credited]
    note.discount = Decimal('0.00')
    note.revises = invoice.number
    return note
