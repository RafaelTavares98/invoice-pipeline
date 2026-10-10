"""Write the invoices, plus the answer key.

    python run.py                one per issuer, into out/
    python run.py 60             sixty invoices, drawn at random
    python run.py --weeks        eight weeks of a real operation
    python run.py --post         write a folder mailbox, no server
    python run.py --send         mail them for real, after a confirmation
    python run.py --weeks --post
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

import invoice_builder          # noqa: E402
import issuers                  # noqa: E402
import ledger                   # noqa: E402
import mail_delivery            # noqa: E402
import mail_sources             # noqa: E402
import render                   # noqa: E402
from operation import Operation  # noqa: E402
from pricing import seeded      # noqa: E402

OUT = Path(__file__).parent / 'out'
INBOX = Path(__file__).parent / 'inbox'

#: The Monday the eight week window opens on.
WINDOW_START = date(2026, 4, 6)


def one_per_issuer(folder):
    written = []
    for position, issuer in enumerate(issuers.ALL_ISSUERS, start=1):
        invoice = invoice_builder.invoice_for(issuer, seed=position * 17)
        path = render.build_invoice(folder, invoice, issuer)
        written.append((issuer, invoice, path))
    return written


def many(folder, count):
    rng = seeded(2026)
    written = []
    for index in range(count):
        issuer = rng.choice(issuers.ALL_ISSUERS)
        invoice = invoice_builder.invoice_for(issuer, seed=rng.randrange(10 ** 9))
        path = render.build_invoice(folder, invoice, issuer)
        written.append((issuer, invoice, path))
    return written


def eight_weeks(folder):
    """Run the operation and draw every invoice it produced."""
    run = Operation(WINDOW_START).run()
    written = []
    for invoice in sorted(run.invoices, key=lambda i: (i.issue_date, i.number)):
        issuer = issuers.by_code(invoice.issuer_code)
        name = f'{invoice.issue_date:%Y-%m-%d}_{invoice.number}.pdf'
        path = render.build_invoice(folder, invoice, issuer, name=name)
        written.append((issuer, invoice, path))

    (folder / 'ledger.json').write_text(
        json.dumps(ledger.build(run), indent=2), encoding='utf-8')
    return run, written


def post_to_folder(written):
    """Put the invoices in a folder mailbox. No server, no account.

    Each message gets its own number, not the invoice's. A resent invoice
    carries the same invoice number as the original, so naming the file
    after it would have the duplicate overwrite what it duplicates, and
    the defect would never reach the reader.
    """
    for position, (issuer, invoice, pdf) in enumerate(written, start=1):
        mail_sources.write_message(
            INBOX,
            f'{position:04d}-{invoice.number}',
            mail_delivery.subject_for(issuer, invoice),
            [(pdf.name, pdf.read_bytes())],
            sender=mail_delivery.sender_for(issuer, 'local@example.invalid'),
        )
    return INBOX


def main():
    flags = {arg for arg in sys.argv[1:] if arg.startswith('--')}
    numbers = [arg for arg in sys.argv[1:] if not arg.startswith('--')]
    count = int(numbers[0]) if numbers else 0

    OUT.mkdir(exist_ok=True)

    if '--weeks' in flags:
        run, written = eight_weeks(OUT)
        _report_weeks(run)
    else:
        written = many(OUT, count) if count else one_per_issuer(OUT)
        truth = [invoice.as_truth() for _, invoice, _ in written]
        (OUT / 'truth.json').write_text(
            json.dumps(truth, indent=2), encoding='utf-8')
        for issuer, invoice, path in written:
            print(f'{issuer.code:4} {issuer.kind:8} {invoice.currency} '
                  f'{invoice.grand_total:>12}  {path.name}')
        print(f'\n{len(written)} invoices and truth.json in {OUT}')

    if '--post' in flags:
        print(f'{len(written)} mail files in {post_to_folder(written)}')

    if '--send' in flags:
        _send(written)


def _report_weeks(run):
    counts = __import__('ledger').counts(run)
    chains = __import__('ledger').chains(run)
    print(f'Window opens {run.start}, eight weeks.\n')
    print(f'{counts["orders"]:>4} purchase orders raised')
    print(f'{counts["shipments"]:>4} shipments left a port')
    print(f'{counts["invoices"]:>4} invoices landed in the window')
    for kind, total in sorted(counts['by_kind'].items()):
        print(f'{total:>8} {kind}')
    print(f'\n{counts["duplicate_numbers"]:>4} duplicate numbers')
    print(f'{counts["revisions"]:>4} revisions')
    print(f'{counts["wrong_order_quoted"]:>4} invoices quoting the wrong order')
    print(f'\n{len(chains):>4} chains with a landed cost')
    print(f'{len([c for c in chains if not c["fully_shipped"]]):>4} '
          f'orders still part shipped')
    print(f'\nledger.json and the PDFs are in {OUT}')


def _send(written):
    """Mail them for real. Asks first, because this leaves the machine."""
    planned = mail_delivery.send_invoices(written, dry_run=True)
    print(f'\nAbout to send {len(planned)} messages:')
    for delivery in planned:
        print(f'  {delivery.sender}  ->  {delivery.subject}')
    if input('\nSend them? type yes: ').strip().lower() != 'yes':
        print('Nothing sent.')
        return
    sent = mail_delivery.send_invoices(written)
    print(f'{len(sent)} sent.')


if __name__ == '__main__':
    main()
