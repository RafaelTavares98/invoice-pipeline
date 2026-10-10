# How-to guide

[README](../README.md) · [Tutorial](tutorial.md) · **How-to** ·
[Reference](reference.md) · [Explanation](explanation.md)

Recipes for people who already know what this project is. Each one stands
alone. If you have never run it, start with the [tutorial](tutorial.md).

---

## Send the invoices as real e-mail

You need a mail account you control, and an app password rather than your
own password.

**1. Tell the program which account sends.**

```bash
setx INVOICE_SMTP_USER "you@gmail.com"
setx INVOICE_SMTP_TO   "you@gmail.com"
```

The address is not a secret, so an environment variable is the right home
for it.

**2. Put the password in the keychain, not in a file.**

```bash
python -m keyring set invoice-pipeline you@gmail.com
```

The keychain encrypts the value and ties it to your login. An environment
variable would sit in plain text in the registry and in your shell history.
The full argument is in
[the explanation](explanation.md#why-the-password-is-in-the-keychain).

Use the app password your provider issues for one program. Never the password
to the account itself.

**3. Send.**

```bash
python run.py --weeks --send
```

The program prints every message it is about to send, waits for you to type
`yes`, and then sends one message every 1.2 seconds. A provider that sees a
hundred messages in ten seconds treats the account as a nuisance.

All ten suppliers send from your one address, under their own names. Why that
works: [the name on the envelope is not the address](explanation.md#why-the-name-on-the-envelope-is-not-the-address).
The variables this recipe sets are listed in
[the reference](reference.md#environment).

---

## Watch a real mailbox and read invoices as they arrive

```bash
python watch.py
```

The program opens an IMAP connection, selects the inbox, and then stops
talking. The server pushes a line the moment a message lands.

It renews the connection every ten minutes, because Gmail hangs up on an idle
one after about half an hour. It sweeps the whole folder once an hour in case
a push went missing. Reading the same message twice is harmless: the hash of
the PDF decides what has already been seen.

Stop it with Ctrl+C. Nothing is lost; `data/state.json` remembers where it
got to.

Why a push and not a timer:
[IMAP IDLE instead of a timer](explanation.md#why-imap-idle-instead-of-a-timer).

To take whatever is already in the mailbox and then stop:

```bash
python watch.py --once
```

---

## Read invoices without any mail server

```bash
python run.py --weeks --post
python watch.py --folder inbox
```

The first command writes `.eml` files into `inbox/`. The second reads that
folder exactly as it would read a server. This is how the tests run, and how
to work on a plane.

It is also step 5 and step 6 of [the tutorial](tutorial.md#step-5-post-the-invoices-to-a-folder-mailbox).

---

## Start again from an empty store

```bash
rm -r data out inbox        # Windows: rmdir /s /q data out inbox
```

`data/` holds the two CSV files and the note of what has been seen. Deleting
it makes every invoice look new again.

`samples/` is not one of these. It is committed on purpose; see
[folders written](reference.md#folders-written).

---

## Get the same invoices twice

Every run is driven by one seed.

```python
from operation import Operation
from datetime import date

run = Operation(date(2026, 4, 6), seed=4242).run()
```

The same seed gives the same eight weeks, down to the invoice numbers. Change
the seed and everything changes except the rules.

`run.py --weeks` uses the default seed, so repeated runs are identical. That
is deliberate: the answer key must not move under your feet.

---

## Add an eleventh issuer

Open `src/issuers.py` and add a `Factory` or a `Carrier` to the tuple.

```python
Factory(
    code='XYZ',
    name='Example Components Ltd.',
    address=('1 Example Road', 'Example City 00000', 'Country'),
    country='Country',
    tax_label='Tax no.',
    tax_id='00-0000000',
    terms='FOB Example. Net 30.',
    bank_line='',
    style='zebra',
    date_order='day_first',
    decimal_mark='dot',
    number_prefix='XYZ',
    accent=(0.12, 0.12, 0.12),
    families=('bottle',),
    price_bias=1.0,
    price_spread=0.09,
),
```

Then:

- add the issuer's port to `LOADING_PORT` in `src/invoice_builder.py`
- add a lane for it in `src/lanes.py`
- add a subject line to `SUBJECTS` in `src/mail_delivery.py`

Two tests fail if you forget. `test_render.py` checks that every issuer has a
page style and `test_operation.py` checks that every issuer bills at least
once in eight weeks.

`style` must be one of: `grid`, `zebra`, `banded`, `minimal`, `dashed`,
`form`, `ledger`. What each one looks like:
[page styles](reference.md#page-styles).

`price_bias` and `price_spread` are what make the new supplier expensive or
erratic; see [distributions](reference.md#distributions) and
[why prices are drawn](explanation.md#why-prices-are-drawn-and-not-fixed).

---

## Add a component to the catalogue

Open `src/catalogue.py` and add a `Component`:

```python
Component('PB-500K', 'PET bottle, 500 ml, clear', 'bottle',
          'pcs', 31.0, 0.214, 4000, '3923.30'),
```

The fields are code, description, family, unit, grams each, base price in
dollars, pack size, and HS code.

A factory only sells the families listed on it, so the new component reaches
an invoice only if some factory claims its family.

---

## Change how often things go wrong

Open `src/defects.py`:

```python
DUPLICATE_CHANCE = 0.06
REVISION_CHANCE = 0.05
CREDIT_CHANCE = 0.04
WRONG_ORDER_CHANCE = 0.07
```

Setting all four to zero gives a clean corpus. Useful once, to see the reader
succeed; useless after that.

`test_ledger.py` asserts that the corpus is not clean, so it fails if you zero
them. That is the test doing its job.

The rates as they stand: [defect rates](reference.md#defect-rates). Why they
are there at all:
[defects are injected on purpose](explanation.md#why-defects-are-injected-on-purpose).

---

## Change how long the window is

Open `src/operation.py`:

```python
WEEKS = 8
BACKLOG_WEEKS = 13
```

`BACKLOG_WEEKS` must stay comfortably longer than a lead time plus a crossing,
which is about seventy days. Otherwise the window opens with nothing arriving,
because every order is still being made.

Why there is a backlog at all:
[the window needs a warm start](explanation.md#why-the-window-needs-a-warm-start).

---

## Find out why one invoice was not read

Open `data/invoices.csv` and look at the `problems` column.

| What it says | What happened |
|---|---|
| `no text layer` | the PDF is a scan; there is nothing to extract |
| `no invoice number` | no label matched any of the known spellings |
| `no table rows` | the heading row was never found |
| `lines add to X, page says subtotal Y` | the rows were read but do not reconcile |

A row with `status=unreadable` still exists. Nothing is dropped, because a
line the pipeline hides is a line nobody learns about. The argument:
[nothing is ever dropped](explanation.md#why-nothing-is-ever-dropped).

The other three statuses are explained in
[what each status means](reference.md#what-each-status-means).

---

## Run one part of the test suite

```bash
python -m pytest tests/test_operation.py -q     # the simulation
python -m pytest tests/test_reading.py -q       # the reader
python -m pytest -k "freight" -q                # anything about freight
python -m pytest -x                             # stop at the first failure
```

What each file covers: [tests](reference.md#tests).
