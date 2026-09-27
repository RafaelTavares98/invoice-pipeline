# Invoice mailbox to CSV

Invoices arrive in eight different shapes. This turns them into one clean
table, and says which rows it could not trust.

Nothing is thrown away. A line that fails a check still reaches the table,
flagged, because a line the software hides is a line nobody checks.

## What it does

```
mailbox -> attachments -> is there a text layer? -> extract -> validate -> CSV
                                     |
                                     no -> OCR -> extract -> validate -> CSV
```

1. Reads a mailbox and takes out every PDF attachment, exactly once.
2. Decides whether each page was typeset or photographed.
3. Sends the photographs through OCR, the rest straight to the reader.
4. Reads the invoice using the layout record of the issuer that sent it.
5. Applies seven checks.
6. Writes two files: every billed line, and every check that failed.

## Try it without an account

```bash
pip install -r requirements.txt
python run.py demo
```

That invents sixteen invoices across eight layouts, mails them to a folder,
and reads them back into `demo/out/`. Every third one is printed as a
picture of a page, with no text layer, so the OCR branch runs too.

## Read a real mailbox

```bash
python run.py read --inbox mail --store raw --out out
```

Or over IMAP, which asks for the password rather than reading it anywhere:

```bash
python run.py read --imap-host imap.example.com \
    --imap-user you@example.com --store raw --out out
```

## The eight layouts

They exist to break a naive parser, and every name in them is invented. The
records live in `src/issuer_layouts.json`, so a ninth issuer is an entry in
a file, not new code.

| Layout | Shape it copies | What makes it hard |
| --- | --- | --- |
| A | European VAT | Comma as the cents mark, day before month, one narrow column |
| B | US commercial | MM/DD/YYYY, a rule down the middle of the page |
| C | Freight | Landscape, seven columns, totals inside the table |
| D | Asian export | Two currencies, and the totals above the lines |
| E | Retail | A coloured band, tinted rows, bank details |
| F | Customs | Two bordered address boxes and a closed grid |
| G | Studio | No rules at all, grey small-caps headings |
| H | Workshop | Quantity printed before the description, total in a box |

`03/04/2026` is April on one of these and March on another. That is why the
reader asks the record instead of guessing.

## The seven checks

1. The line totals add up to the subtotal.
2. Subtotal plus tax equals the grand total.
3. Quantity times unit price equals the line total.
4. The due date does not fall before the issue date.
5. The invoice number has not arrived before.
6. Every required field is present.
7. The currency is a code the pipeline knows.

Money is compared to the cent. A one-cent gap is a supplier's rounding,
not a mistake worth reporting.

## Two output files

`invoice_lines.csv` is one row per billed line, with the header repeated on
each. `flags` names every check that failed, and `confidence` says how much
the reader vouches for the row. A scanned page is trusted less than a
typeset one.

`findings.csv` is one row per failed check: the rule, the message, the line.

## How well the OCR reads

Measured, not estimated. The generator records the words it drew beside
every scanned page, so the engine's answer is checked against the source.

One demo run, sixteen invoices across the eight layouts:

| | |
| --- | --- |
| Read from a text layer | 11 |
| Read by the engine | 5 |
| Unreadable | 0 |
| Flagged by a rule | 0 |

Every scanned field came back equal to the source, down to the cent.

Three things had to be fixed first, each a fault in how the page was
printed or handed over, not in the engine:

- **A eleven pixel bitmap font.** `4.00` was read as `400`, and four of
  six lines were lost. The arithmetic rule caught it, which is the whole
  argument for flagging rather than trusting.
- **The scan declared the wrong resolution.** Photographed at 300 dots
  per inch, saved claiming 150, so `98,67` became `08,67`.
- **Table borders read as characters.** On the closed grids, every row
  came back as punctuation. A straight run of ink across a quarter of the
  page, no thicker than a rule, is now wiped before reading.

## Requirements

Python 3.10 or newer, and the packages in `requirements.txt`.

OCR needs the Tesseract binary, a separate install. Everything else runs
without it. The reader is passed into the pipeline rather than imported by
it, so swapping the engine touches one line.

## Tests

```bash
python -m pytest
```

102 tests, including a full run from a filled mailbox to both CSV files.
Ten drive the real OCR engine and skip themselves where none is installed.

Every expected value comes from the generator, which knows what it wrote,
so no number is typed in by hand and none goes stale when a layout changes.

## Layout of the code

```
run.py                  the command line
src/
  invoice.py            what an invoice is
  amounts_and_dates.py  reading a printed number and a printed date
  issuer_layouts.json   the eight issuers, as data
  issuer_layouts.py     reading that file
  validation_rules.py   the seven checks
  run_pipeline.py       the order the steps run in
  invoice_generator/     invents invoices, draws them, posts them
  mailbox_intake/        mail in, attachments out, words off the page
  csv_output/            the two files
tests/
```

## Decisions worth knowing

**Money is `Decimal`.** Binary rounding invents a mismatch nobody made.

**`validate` refuses to run without the invoice numbers already seen.**
There is no default, so a caller that forgets it fails loudly instead of
quietly skipping the duplicate check.

**The layout record drives the reader.** Which column holds the
description, what the page calls its total, which mark means cents: all of
it is read from the record, never assumed.

**The table does not need its header row.** The header is the smallest
type on the page and the first thing an engine loses.

**The manifest is keyed on the mail message id.** That makes a run safe to
interrupt.

**A field the page does not give is left empty.** Nothing is invented, and
one unreadable page never ends the batch.
