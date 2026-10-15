"""Sit on the mailbox and write the two CSV files as invoices arrive.

    python watch.py                 wait for the next invoice, forever
    python watch.py --once          take whatever is already there, then stop
    python watch.py --folder DIR    read a folder of .eml files instead
    python watch.py --metrics PORT  also serve the counts on /metrics

What it files goes into Invoices/live/data/. The smoke tests' mail in the
same mailbox is left to the smoke steps.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from reading import intake                       # noqa: E402
from mail import sources                         # noqa: E402

DATA = Path(__file__).parent / 'Invoices' / 'live' / 'data'


def _value_after(flag):
    if flag not in sys.argv:
        return None
    return sys.argv[sys.argv.index(flag) + 1]


def main():
    store = intake.Store(DATA)
    watch = None
    port = _value_after('--metrics')
    if port:
        from prometheus_client import REGISTRY, start_http_server
        from monitoring import metrics
        start_http_server(int(port))
        watch = metrics.Pipeline(REGISTRY)
        watch.stored.set(len(store.invoices))

    def report(arrival, outcome):
        if watch is not None:
            from monitoring import metrics
            metrics.filed(watch, store, outcome)
        note = f'  {outcome.problems[0]}' if outcome.problems else ''
        print(f'{outcome.status:<11} {outcome.invoice_number or arrival.filename}'
              f'{note}', flush=True)

    folder = _value_after('--folder')
    if folder:
        for message in sources.LocalMailbox(folder).messages():
            for name, outcome in intake.replay(store, message):
                print(f'{outcome.status:<11} {outcome.invoice_number or name}')
        store.save()
    elif '--once' in sys.argv:
        from mail import watcher
        with watcher._connected() as server:
            watcher._drain(server, store, report)
    else:
        from mail import watcher
        print('Waiting. The server will push when an invoice lands.\n')
        watcher.watch(store, on_arrival=report)

    print(f'\n{len(store.invoices)} invoices and {len(store.lines)} lines '
          f'in {store.save()}')


if __name__ == '__main__':
    main()
