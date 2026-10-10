"""Sit on the mailbox and write the two CSV files as invoices arrive.

    python watch.py                 wait for the next invoice, forever
    python watch.py --once          take whatever is already there, then stop
    python watch.py --folder inbox  read a folder of .eml files instead
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

import intake                       # noqa: E402
import mail_sources                 # noqa: E402

DATA = Path(__file__).parent / 'data'


def report(arrival, outcome):
    note = f'  {outcome.problems[0]}' if outcome.problems else ''
    print(f'{outcome.status:<11} {outcome.invoice_number or arrival.filename}'
          f'{note}', flush=True)


def from_folder(store, folder):
    """No server. Every .eml in a folder, which is how the tests run."""
    for message in mail_sources.LocalMailbox(folder).messages():
        for name, payload in message.attachments:
            outcome = store.take(payload, name,
                                 message.received_at.isoformat())
            print(f'{outcome.status:<11} {outcome.invoice_number or name}')
    store.save()


def main():
    flags = set(sys.argv[1:])
    store = intake.Store(DATA)

    if '--folder' in flags or any(a == '--folder' for a in sys.argv):
        where = sys.argv[sys.argv.index('--folder') + 1]
        from_folder(store, Path(where))
    elif '--once' in flags:
        import watcher
        with watcher._connected() as server:
            watcher._drain(server, store, report)
    else:
        import watcher
        print('Waiting. The server will push when an invoice lands.\n')
        watcher.watch(store, on_arrival=report)

    print(f'\n{len(store.invoices)} invoices and {len(store.lines)} lines '
          f'in {store.save()}')


if __name__ == '__main__':
    main()
