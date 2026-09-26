# Invoice mailbox to CSV

Invoices arrive in your inbox in eight different shapes. This turns them
into one clean table, and tells you which rows it could not trust.

Nothing is thrown away. A line that fails a check still reaches the table,
flagged, because a line the software hides is a line nobody checks.

## What it does

```
mailbox -> attachments -> is there a text layer? -> extract -> validate -> CSV
                                     |
                                     no -> OCR -> extract -> validate -> CSV
```

1. Reads a mailbox and takes out every PDF attachment.
2. Records what it has taken, so a second run downloads nothing twice.
3. Decides whether each page was typeset or is a photograph of a page.
4. Sends the photographs through OCR, and the rest straight to the reader.
5. Reads the invoice using the layout record of the issuer that sent it.
6. Applies seven checks.
7. Writes two files: every billed line, and every check that failed.

## Try it without an account

```bash
pip install -r requirements.txt
python run.py demo
```

That invents sixteen invoices across eight layouts, mails them to a
folder, and reads them back. Every third one is printed as a picture of a
page, with no text layer, so the OCR branch runs too.

Output:

```
demo/out/invoice_lines.csv
demo/out/findings.csv
```

## Read a real mailbox

```bash
python run.py read --inbox mail --store raw --out out
```

Or over IMAP, which asks for the password rather than reading it from a
file or an argument:

```bash
python run.py read --imap-host imap.example.com \
    --imap-user you@example.com --store raw --out out
```

## The eight layouts

They exist to break a naive parser. Every company, address and tax number
in them is invented. The records live in `src/issuer_layouts.json`, so a
ninth issuer is a new entry in a file, not new code.

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

The same six digits, `03/04/2026`, are the third of April on one of these
and the fourth of March on another. That is why the reader asks the layout
record instead of guessing.

## The seven checks

1. The line totals add up to the subtotal.
2. Subtotal plus tax equals the grand total.
3. Quantity times unit price equals the line total.
4. The due date does not fall before the issue date.
5. The invoice number has not arrived before.
6. Every required field is present.
7. The currency is a code the pipeline knows.

Money is compared to the cent. Suppliers round their own way, and a
one-cent gap is their rounding, not a mistake worth reporting.

## Two output files

`invoice_lines.csv` is one row per billed line, with the invoice header
repeated on each. The `flags` column names every check that failed for
that row, and `confidence` says how much the reader vouches for it. A page
read by a model is trusted less than one read from a text layer.

`findings.csv` is one row per failed check, with the rule, the message and
the line it came from.

## How well the OCR reads

Measured, not estimated. The generator records the words it drew beside
every scanned page, so the engine's answer is compared against the source
rather than against a number typed by hand.

One demo run, sixteen invoices across the eight layouts:

| | |
| --- | --- |
| Read from a text layer | 11 |
| Read by the engine | 5 |
| Unreadable | 0 |
| Flagged by a rule | 0 |

Every field of the scanned pages came back equal to the source, down to
the cent, on all eight layouts.

Three things had to be fixed before that was true, and each was a fault in
how the page was printed or handed over, not in the engine:

- **The page was drawn in an eleven pixel bitmap font.** The engine read a
  quantity of `4.00` as `400` and lost four of six lines. The arithmetic
  rule caught it, which is the whole argument for flagging rather than
  trusting.
- **The scan declared the wrong resolution.** A page photographed at 300
  dots per inch was saved claiming 150, so it came out twice the size of
  the paper and the engine read a stretched picture. `98,67` became
  `08,67`.
- **The engine read table borders as characters.** On the three layouts
  with a closed grid, every row came back as punctuation. The borders are
  now wiped before the page is read: a straight run of ink across a
  quarter of the page, no thicker than a rule, is a border and not a word.
  A thicker band is left alone, because words are printed on those.

## Requirements

Python 3.10 or newer, and the packages in `requirements.txt`.

OCR needs the Tesseract binary on the machine, which is a separate
install. Everything else runs without it. The OCR reader is passed into
the pipeline rather than imported by it, so swapping the engine touches
one line and the test suite runs on a machine with no engine at all.

## Tests

```bash
python -m pytest
```

102 tests. The suite includes a full run from a filled mailbox to both CSV
files, and ten tests that drive the real OCR engine.

Those ten skip themselves on a machine with no engine installed, so the
other ninety-two still run anywhere.

Every expected value comes from the generator, which knows what it wrote,
so no number is typed into a test by hand and none can go stale when a
layout changes.

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
  invoice_generator/
    build_invoice.py    invents invoices and posts them
    page_drawing.py     the parts every layout is drawn from
    layout_styles.py    the eight ways of putting those parts together
  mailbox_intake/
    mail_sources.py     a folder of mail, or a real IMAP server
    attachment_store.py taking attachments out, exactly once
    page_text.py        getting the words off a page, typeset or scanned
    field_extraction.py turning those words back into an invoice
  csv_output/
    table_writer.py     the two files
tests/
```

## Decisions worth knowing

**Money is `Decimal`.** A cent lost to binary rounding is a cent the
validator would later report as a mismatch that was never there.

**`validate` refuses to run without the list of invoice numbers already
seen.** There is no default, so a caller that forgets it fails loudly
instead of quietly skipping the duplicate check.

**The layout record drives the reader.** Which column holds the
description, what the page calls its total, which mark means cents: all of
it is read from the record. A reader that assumes an order reads one
issuer and fails on the next.

**The table does not need its header row.** The header is the smallest
type on the page and the first thing an engine loses. It narrows the
search when it survives; the rows are found without it.

**The manifest is keyed on the mail message id.** That is what makes a run
safe to interrupt.

**A field the page does not give is left empty and reported.** Nothing is
invented to fill a gap.

**One unreadable page does not end the batch.** The other invoices in the
mailbox are still owed to whoever is waiting for them.
