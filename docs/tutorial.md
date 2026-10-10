# Tutorial: your first invoice, end to end

[README](../README.md) · **Tutorial** · [How-to](how-to.md) ·
[Reference](reference.md) · [Explanation](explanation.md)

By the end of this lesson you will have made an invoice, posted it to a
folder that stands in for a mailbox, read it back, and seen your own answer
compared with the correct one.

No mail server is involved. Nothing leaves your machine.

Allow fifteen minutes.

## Before you start

You need Python 3.10 or newer. Check it:

```bash
python --version
```

Move into the project and install what it needs:

```bash
cd Portfolio/manual/01-invoice-pipeline
pip install -r requirements.txt
```

Three libraries arrive: `reportlab` draws the PDFs, `pypdf` and `pdfplumber`
read them back, and `pytest` runs the tests.

## Step 1: prove the project works

```bash
python -m pytest
```

You should see `253 passed`. If anything fails, stop here; the rest of the
lesson assumes a healthy project.

What the ten test files cover: [tests](reference.md#tests).

## Step 2: make one invoice

```bash
python run.py
```

The program writes one invoice from each of the ten issuers and prints a line
for each:

```
NCL  factory  USD     31218.00  NCL-2026-7579.pdf
SBP  factory  USD     22191.38  SBP-2026-1978.pdf
...
MRK  carrier  USD      6119.18  MRK-2026-1496.pdf
```

Look in the `out/` folder. Open two of the PDFs side by side, one from a
factory and one from a carrier. Notice that they share no layout: different
columns, different page orientation, different way of writing the date.

That difference is the point of the whole project. The seven designs are
named in [page styles](reference.md#page-styles), and the same ten PDFs are
committed in [the samples folder](../samples/README.md) if you would rather
not run anything.

## Step 3: look at the answer key

Open `out/truth.json`. Find the entry whose `number` matches one of the PDFs
you just opened:

```json
{
  "number": "NCL-2026-7579",
  "kind": "goods",
  "issuer": "NCL",
  "issue_date": "2026-09-30",
  "grand_total": "31218.00",
  "line_count": 3
}
```

Check the figure against the paper. They agree, because the same program
wrote both. Later, a different program will have to work the figure out from
the paper alone. Why that separation matters:
[the reader is blind](explanation.md#why-the-reader-is-blind).

## Step 4: run eight weeks instead of ten invoices

```bash
python run.py --weeks
```

This is the interesting mode. Instead of ten invoices drawn from nowhere, it
runs a business for eight weeks and lets the paperwork happen:

```
  79 purchase orders raised
  44 shipments left a port
 102 invoices landed in the window
```

Open `out/ledger.json` and find the `chains` section. One chain looks like
this:

```json
{
  "order_number": "PO-41011",
  "factory": "HCV",
  "goods_invoices": ["HCV-2026-3107"],
  "shipments": ["B/L MRK7000106"],
  "freight_invoices": ["MRK-2026-3108", "KNG-2026-3209"],
  "landed_cost": "8601.06"
}
```

Read it as a sentence. Moty ordered something from Hanil. Hanil invoiced it.
Marsk carried it by sea and invoiced that. Keuhne & Nager trucked it from the
port and invoiced that too. Landing those goods in Louveira cost 8601.06.

That sentence is the question the cost department is actually asked.

Every key in a chain is listed in [a chain](reference.md#a-chain). Why the
freight is a slice and not the whole invoice:
[freight is split between orders](explanation.md#why-freight-is-split-between-orders).

## Step 5: post the invoices to a folder mailbox

```bash
python run.py --weeks --post
```

Now look in `inbox/`. Every invoice has become an `.eml` file: a real mail
message, with a real subject line and the PDF attached.

Open one in a text editor. The subject is not the same for every supplier:

```
Subject: Invoice NCL-2026-3140 / PO-41021
Subject: COSMO SHIPPING | INVOICE CSM-2026-3285 | B/L CSM7000282
Subject: Rechnung / Invoice KNG-2026-3265
```

Two of them give away the purchase order or the bill of lading in the subject.
Eight do not. A reader cannot rely on the subject line.

The address every one of them came from is not the name on it; see
[the name on the envelope](explanation.md#why-the-name-on-the-envelope-is-not-the-address).

## Step 6: read the mailbox back

```bash
python watch.py --folder inbox
```

The program opens every message, pulls out the PDF, reads the text, and
writes two files into `data/`:

```
new         NCL-2026-3140
new         MRK-2026-3141
duplicate   NCL-2026-3140
revised     CSM-2026-3238
...
```

Three words appear in that output and each means something:

- `new` is a document never seen before.
- `duplicate` is the same PDF arriving twice. It is counted once.
- `revised` means an invoice number came back with different figures. The
  earlier row is marked `superseded` and must not be paid.

All four statuses: [what each status means](reference.md#what-each-status-means).
Why the bytes decide and not the number:
[the hash is the identity](explanation.md#why-the-hash-is-the-identity-not-the-invoice-number).

## Step 7: look at what it found

Open `data/invoices.csv`. One row per document:

```
invoice_number,status,issuer,issue_date,grand_total,order_number,...
NCL-2026-3140,new,"Ningbo Caplink Industrial Co., Ltd.",2026-04-11,40640.00,PO-41021,...
```

Open `data/invoice_lines.csv`. One row per line item:

```
invoice_number,row,description,quantity,unit_price,net
NCL-2026-3140,1,"Lotion pump, 24/410, 1.2 cc, silver collar",100000,0.212,21200.00
```

Nothing in `reading.py` was told that Ningbo Caplink exists, or that it writes
dates as `2026-04-11`. It worked both out from the page.

Every column of both files:
[`data/invoices.csv`](reference.md#datainvoicescsv) and
[`data/invoice_lines.csv`](reference.md#datainvoice_linescsv).

## Step 8: score yourself

Compare what the reader found with what the generator knows:

```bash
python -c "
import csv, json
from decimal import Decimal
rows = list(csv.DictReader(open('data/invoices.csv', encoding='utf-8')))
truth = {}
for t in json.load(open('out/ledger.json', encoding='utf-8'))['invoices']:
    truth.setdefault(t['number'], []).append(t)
hit = sum(1 for r in rows
          if r['grand_total'] in [t['grand_total'] for t in truth.get(r['invoice_number'], [])])
print(f'{hit} of {len(rows)} totals correct')
"
```

You should see every total matching.

## What you have learned

- The generator and the reader are separate programs, and the reader is blind
  to the generator.
- An invoice is the consequence of an order and a shipment, not an isolated
  document.
- The same PDF arriving twice is a duplicate; the same number with new figures
  is a revision. They are not the same problem.
- The answer key is what makes the score honest.

## Where to go next

- [How-to guide](how-to.md) for sending real mail and changing the simulation.
  Start with [send the invoices as real e-mail](how-to.md#send-the-invoices-as-real-e-mail).
- [Explanation](explanation.md) for why it is built this way. Start with
  [why the reader is blind](explanation.md#why-the-reader-is-blind).
- [Reference](reference.md) when you need a command, a column or a module.
- [README](../README.md) for the diagrams and the whole picture.
