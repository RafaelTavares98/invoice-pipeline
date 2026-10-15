"""Make the invoices, send them, read them, cost them.

The real run, Part 3 of the tutorial, into Invoices/live/:

    python run.py request [--send]          one request per sender
    python run.py backlog [DATE] [--post] [--send] [--metrics]
                                            1 January to DATE (today)
    python run.py score                     the reader against ledger.json
    python run.py live [--send]             what was issued since the last run
    python run.py cost [DATA] [ERP] [OUT]   the cost report

The tutorial's smoke steps, into Invoices/samples/<step>/:

    python run.py smoke freight|senders|forward [SCA] [--send]
    python run.py smoke read-mail|read-senders|read-forward
    python run.py smoke cost
    python run.py smoke                     one invoice end to end, scored

Trials and figures for a model:

    python run.py samples [N]               one per issuer, or N at random
    python run.py batch [N]                 N invoices end to end, scored
    python run.py unit                      the tests, one stage at a time
    python run.py dataset [PROFILE] [SEED ...]
    python run.py readset [PROFILE] [COUNT] [SEED]
    python run.py monitor [SECONDS] [PORT]  simulated live ticks, with metrics
    python run.py readme                    the reference's one-run table
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from business import issuers                # noqa: E402
from drawing import render, scan            # noqa: E402
from runs import modes                      # noqa: E402
from simulation import builder              # noqa: E402
from simulation.pricing import seeded       # noqa: E402

HERE = Path(__file__).parent
SAMPLES = HERE / 'Invoices' / 'samples'
LIVE = HERE / 'Invoices' / 'live'

#: The test folders, one per stage, in the order data flows.
STAGES = ('business', 'simulation', 'drawing', 'mail', 'reading', 'costing',
          'runs', 'monitoring')

#: The issuers with one sample each: the foreign ones and the broker.
SAMPLED = issuers.ALL_ISSUERS + (issuers.BROKER,)


def _confirmed(question):
    """Anything that leaves the machine is asked about first."""
    return input(f'{question} type yes: ').strip().lower() == 'yes'


# ------------------------------------------------------------- samples


def _shows_the_habit(invoice):
    """Whether the generator made this one the way its issuer scans: a
    scan, and askew when the issuer lays pages askew."""
    habit = scan.HABITS[invoice.number.split('-')[0]]
    return scan.chosen(invoice.number) and (
        scan.askew(invoice.number) or not habit.askew)


def sample_for(folder, issuer, seed):
    """One invoice from the generator. The sample of an issuer that scans
    shows its habit: the seed moves on until the generator itself makes
    one the way that issuer scans."""
    invoice = builder.invoice_for(issuer, seed=seed)
    while issuer.code in scan.HABITS and not _shows_the_habit(invoice):
        seed += 1
        invoice = builder.invoice_for(issuer, seed=seed)
    path, _ = render.draw(folder, invoice, issuer)
    return issuer, invoice, path


def one_per_issuer(folder):
    return [sample_for(folder, issuer, seed=position * 17)
            for position, issuer in enumerate(SAMPLED, start=1)]


def many(folder, count):
    rng = seeded(2026)
    written = []
    for _ in range(count):
        issuer = rng.choice(issuers.ALL_ISSUERS)
        invoice = builder.invoice_for(issuer, seed=rng.randrange(10 ** 9))
        path, _ = render.draw(folder, invoice, issuer)
        written.append((issuer, invoice, path))
    return written


def _samples(numbers):
    SAMPLES.mkdir(parents=True, exist_ok=True)
    written = many(SAMPLES, numbers[0]) if numbers else one_per_issuer(SAMPLES)
    truth = [invoice.as_truth() | {
        'scan': (scan.quality(invoice.number).name
                 if scan.chosen(invoice.number) else ''),
        'askew': scan.askew(invoice.number)} for _, invoice, _ in written]
    (SAMPLES / 'truth.json').write_text(json.dumps(truth, indent=2),
                                        encoding='utf-8')
    for issuer, invoice, path in written:
        print(f'{issuer.code:4} {issuer.kind:8} {invoice.currency} '
              f'{invoice.grand_total:>12}  {path.name}')
    print(f'\n{len(written)} invoices and truth.json in {SAMPLES}')


# ------------------------------------------------------------ the real run


def _request(flags):
    from runs import backlog
    send = '--send' in flags
    if send and not _confirmed('Send one request per sender to the real '
                               'mailbox?'):
        return print('Nothing sent.')
    outbox = backlog.request(HERE, send=send)
    print(f'13 requests in {outbox}; {"sent" if send else "not sent"}')


def _backlog(words, flags):
    """The business from 1 January to the run date, drawn, then posted to a
    folder or sent to the real mailbox."""
    from runs import backlog
    until = date.fromisoformat(words[1]) if len(words) > 1 else date.today()
    run = backlog.build(HERE, until)
    print(f'{len(run.invoices)} documents from {backlog.OPENS} to {until} in '
          f'{backlog.live_folder(HERE)}', flush=True)
    if '--post' in flags:
        print(f'replies in {backlog.post(HERE, run)}')
    if '--send' not in flags:
        return
    planned = len(backlog.mails(HERE, run, 'x@example.invalid', 'y'))
    if not _confirmed(f'Send {planned} replies to the real mailbox, at most '
                      f'{backlog.DAILY_LIMIT} today?'):
        return print('Nothing sent.')
    on_sent = _sender_metrics() if '--metrics' in flags else None
    outcome = backlog.send(HERE, run, on_sent=on_sent)
    print(f'{outcome["sent"]} replies sent, {outcome["left"]} left; sent.json '
          f'in {backlog.live_folder(HERE)}')
    if outcome['stopped'] == 'daily limit' or outcome['left']:
        print('Gmail\'s daily sending limit is reached. Run the same command '
              'tomorrow: it carries on from the first reply not yet sent.')


def _sender_metrics():
    """Count each reply sent on port 9110; 9108 is the watcher's, 9109
    project 02's."""
    from prometheus_client import REGISTRY, start_http_server
    from monitoring import metrics
    start_http_server(9110)
    watch = metrics.Pipeline(REGISTRY)
    return lambda mail: metrics.mailed(watch, mail)


def _score():
    from runs import backlog
    found = backlog.score(HERE)
    print(f'score: {found["right"]} of {found["pdfs"]} documents read right; '
          f'flagged for a person {len(found["flagged"])}; wrong '
          f'{len(found["wrong"])}; missing {len(found["missing"])}')
    for case in found['wrong']:
        print(f'  wrong: {case}')
    for name in found['missing'][:20]:
        print(f'  missing: {name}')


def _live(flags):
    """The documents issued since the last run, up to today, one mail
    each; posted to a folder unless --send."""
    from runs import backlog
    send = '--send' in flags
    if send and not _confirmed('Send today\'s documents to the real mailbox?'):
        return print('Nothing sent.')
    posted = []
    new = backlog.daily(HERE, deliver=None if send else posted.append,
                        pause=1.5 if send else 0)
    if posted:
        inbox = backlog.live_folder(HERE) / 'inbox'
        inbox.mkdir(parents=True, exist_ok=True)
        for mail in posted:
            (inbox / f'{mail["X-Reply-Id"]}.eml').write_bytes(mail.as_bytes())
    print(f'{len(new)} documents issued since the last run, '
          f'{"sent" if send else "posted"}, one mail each')


def _cost(words):
    from costing import landed
    data = Path(words[1]) if len(words) > 1 else LIVE / 'data'
    erp_folder = Path(words[2]) if len(words) > 2 else LIVE / 'erp'
    target = Path(words[3]) if len(words) > 3 else LIVE / 'cost'
    written = landed.write(landed.load(data, erp_folder), target)
    print('cost report:', ', '.join(p.name for p in written),
          'and kpis.json in', target)


# ------------------------------------------------------- the smoke steps


def _smoke(words, flags):
    from runs import smoke
    step = words[1] if len(words) > 1 else ''
    send = '--send' in flags
    if step in ('freight', 'senders', 'forward'):
        if send and not _confirmed(f'Send smoke step "{step}" to the real '
                                   'mailbox?'):
            return print('Nothing sent.')
        if step == 'forward':
            home = smoke.forward(HERE, sender=words[2] if len(words) > 2
                                 else 'SCA', send=send)
        else:
            home = getattr(smoke, step)(HERE, send=send)
        mails = len(list((home / 'outbox').glob('*.eml')))
        return print(f'smoke {step}: {mails} mail(s) in {home}; '
                     f'{"sent" if send else "not sent"}')
    if step in ('read-mail', 'read-senders', 'read-forward'):
        source = {'read-mail': 'freight', 'read-senders': 'senders',
                  'read-forward': 'forward'}[step]
        score = smoke.read(HERE, source)
        print(f'smoke {step}: {score["right"]} of {score["pdfs"]} PDFs read '
              f'right; flagged for a person {len(score["flagged"])}; wrong '
              f'{len(score["wrong"])}; missing {len(score["missing"])}')
        for case in score['flagged'] + score['wrong']:
            print(f'  {case["file"]}: {case}')
        for name in score['missing']:
            print(f'  missing: {name}')
        return
    if step == 'cost':
        costed = smoke.cost(HERE)
        return print(f'smoke cost: {len(costed["rows"])} cost lines in '
                     f'{costed["folder"]}; parts add to '
                     f'{costed["parts_total"]:.2f}, documents bill '
                     f'{costed["documents_total"]:.2f}')
    _scored('smoke', modes.smoke(HERE))


def _scored(mode, score):
    print(f'{mode}: {score.correct} of {score.total} read correctly; '
          f'scans {score.scanned_correct} of {score.scanned_total}; '
          f'in {modes.folder_for(HERE, mode)}')


# ------------------------------------------------- trials and figures


def _unit():
    """Each stage's tests on their own, temporary files under
    Invoices/samples/unit."""
    import subprocess
    home = modes.folder_for(HERE, 'unit')
    home.mkdir(parents=True, exist_ok=True)
    for stage in STAGES:
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q', f'tests/{stage}',
             f'--basetemp={home / stage}'],
            cwd=HERE, capture_output=True, text=True)
        last = (result.stdout.strip().splitlines() or ['no output'])[-1]
        print(f'{stage:<11} {last}')


def _dataset(words):
    profile = words[1] if len(words) > 1 else 'year'
    for seed in [int(word) for word in words[2:]] or [2026]:
        print(f'dataset in {modes.dataset(HERE, profile, seed)}')


def _readset(words):
    """The same run, drawn and read back, so the figures carry the
    reader's mistakes. Give it a count unless you mean to wait hours."""
    profile = words[1] if len(words) > 1 else 'busy'
    limit = int(words[2]) if len(words) > 2 else 400
    seed = int(words[3]) if len(words) > 3 else 2026
    print(f'read dataset in {modes.read_dataset(HERE, profile, seed, limit=limit)}')


def _monitor(numbers):
    """The simulated live ticks, forever, with the metrics on /metrics:
    the dashboard's demonstration, run by the compose file."""
    import time
    from prometheus_client import REGISTRY, start_http_server
    from monitoring import metrics
    seconds = numbers[0] if numbers else 15
    port = numbers[1] if len(numbers) > 1 else 9108
    start_http_server(port)
    watch = metrics.Pipeline(REGISTRY)
    print(f'metrics on http://localhost:{port}/metrics, a tick every '
          f'{seconds} s', flush=True)
    while True:
        day = modes.live_day(HERE)
        released = metrics.tick(HERE, watch)
        print(f'{day}  {len(released):>3} invoices', flush=True)
        time.sleep(seconds)


def _readme():
    from runs import report
    report.write_into(HERE / 'docs' / 'reference.md')
    print('Reference one-run table rewritten from the run.')


def main():
    flags = {arg for arg in sys.argv[1:] if arg.startswith('--')}
    words = [arg for arg in sys.argv[1:] if not arg.startswith('--')]
    mode = words[0] if words else 'samples'
    numbers = [int(word) for word in words[1:] if word.isdigit()]
    commands = {
        'request': lambda: _request(flags),
        'backlog': lambda: _backlog(words, flags),
        'score': _score,
        'live': lambda: _live(flags),
        'cost': lambda: _cost(words),
        'smoke': lambda: _smoke(words, flags),
        'samples': lambda: _samples(numbers),
        'batch': lambda: _scored('batch', modes.batch(HERE, *numbers[:1])),
        'unit': _unit,
        'dataset': lambda: _dataset(words),
        'readset': lambda: _readset(words),
        'monitor': lambda: _monitor(numbers),
        'readme': _readme,
    }
    if mode not in commands:
        sys.exit(__doc__)
    commands[mode]()


if __name__ == '__main__':
    main()
