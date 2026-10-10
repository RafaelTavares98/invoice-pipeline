# Reference

[README](../README.md) · [Tutorial](tutorial.md) · [How-to](how-to.md) ·
**Reference** · [Explanation](explanation.md)

Technical description of the machinery. Look things up here; do not read it
straight through.

Each section says what a thing is. When you want to know why it is that way,
the link at the end of the section goes to [the explanation](explanation.md).

---

## Commands

### `run.py`

Makes invoices and writes the answer key.

| Invocation | What it does |
|---|---|
| `python run.py` | one invoice per issuer, into `out/`, plus `truth.json` |
| `python run.py 60` | sixty invoices, issuers drawn at random |
| `python run.py --weeks` | eight weeks of the operation, plus `ledger.json` |
| `python run.py --post` | also writes `.eml` files into `inbox/` |
| `python run.py --send` | also mails them, after printing them and asking |
| `python run.py --weeks --post` | flags combine |

### `watch.py`

Reads a mailbox into the two CSV files.

| Invocation | What it does |
|---|---|
| `python watch.py` | opens IMAP IDLE and waits for the server to push |
| `python watch.py --once` | takes what is already in the mailbox, then stops |
| `python watch.py --folder inbox` | reads a folder of `.eml` files, no server |

Each of these is walked through, one step at a time, in
[the tutorial](tutorial.md).

---

## Environment

| Variable | Default | Used by |
|---|---|---|
| `INVOICE_SMTP_USER` | none, required to send | `mail_delivery.py` |
| `INVOICE_SMTP_TO` | the sending address | `mail_delivery.py` |
| `INVOICE_SMTP_HOST` | `smtp.gmail.com` | `mail_delivery.py` |
| `INVOICE_SMTP_PORT` | `587` | `mail_delivery.py` |
| `INVOICE_IMAP_HOST` | `imap.gmail.com` | `watcher.py` |
| `INVOICE_IMAP_FOLDER` | `INBOX` | `watcher.py` |

The password is never an environment variable. It lives in the operating
system keychain, under the service name `invoice-pipeline`, labelled with the
sending address.

Why: [the password is in the keychain](explanation.md#why-the-password-is-in-the-keychain).
How: [send the invoices as real e-mail](how-to.md#send-the-invoices-as-real-e-mail).

---

## Folders written

| Folder | Holds |
|---|---|
| `out/` | the PDFs, plus `truth.json` or `ledger.json` |
| `inbox/` | `.eml` files, when `--post` is used |
| `data/` | `invoices.csv`, `invoice_lines.csv`, `state.json` |

`samples/` is not written by a run. It is ten invoices committed on purpose,
one per issuer, with their answers in `samples/truth.json`.

`out/` holds fewer PDFs than the run reports invoices. A resend bears the same
date and the same number, so it writes the same filename with the same bytes.
`inbox/` holds one message per invoice, resends included, because the point of
a resend is that it arrives twice.

---

## `data/invoices.csv`

One row per document taken from the mailbox.

| Column | Meaning |
|---|---|
| `invoice_number` | as printed on the page; empty if none was found |
| `status` | `new`, `revised`, `superseded` or `unreadable` |
| `revises` | the number this one corrects, taken from its own `-R1` suffix |
| `issuer` | the name printed under FROM |
| `issue_date` | ISO, whatever order the page used |
| `due_date` | ISO |
| `subtotal` | before any discount |
| `discount` | empty when the page shows none |
| `grand_total` | what is owed; negative on a credit note |
| `order_number` | the `PO-xxxxx` found anywhere on the page |
| `shipment_id` | the `B/L ...` or `AWB ...` found anywhere on the page |
| `line_count` | rows read out of the table |
| `decimal_mark` | `dot` or `comma`, as worked out from the page |
| `date_order` | `iso`, `day_first` or `month_first`, as worked out |
| `source` | the attachment filename |
| `sha256` | hash of the PDF bytes; the real identity of the document |
| `first_seen` | when the message arrived at the server |
| `problems` | semicolon separated; empty when nothing was wrong |

### What each status means

| Status | Cause | Should it be paid |
|---|---|---|
| `new` | a document never seen before | yes |
| `revised` | it corrects an invoice already on file | yes |
| `superseded` | an earlier row that a revision replaced | **no** |
| `unreadable` | the PDF could not be read | needs a human |

A resend gets no row at all. The hash of its bytes is already known, so it is
counted once and skipped. `watch.py` prints `duplicate` when that happens, but
nothing is written.

A revision is recognised two ways: by its number ending `-R1`, and by the same
number arriving with different bytes. Either way the earlier row becomes
`superseded`.

Why: [the hash is the identity, not the invoice number](explanation.md#why-the-hash-is-the-identity-not-the-invoice-number),
and [nothing is ever dropped](explanation.md#why-nothing-is-ever-dropped).
How: [find out why one invoice was not read](how-to.md#find-out-why-one-invoice-was-not-read).

---

## `data/invoice_lines.csv`

One row per line item.

| Column | Meaning |
|---|---|
| `invoice_number` | joins to `invoices.csv` |
| `sha256` | joins to the exact document, even when numbers repeat |
| `row` | position in the table, from 1 |
| `description` | the words of the row, figures removed |
| `quantity` | read from the column the heading pointed at |
| `unit_price` | second figure from the right |
| `net` | last figure on the row |

Join on `sha256`, not on `invoice_number`. A revision shares its number with
the document it replaces.

Why: [the quantity column is counted from the right](explanation.md#why-the-quantity-column-is-counted-from-the-right).

---

## `out/ledger.json`

The answer key for a `--weeks` run.

| Key | Holds |
|---|---|
| `window` | the start date and the number of weeks |
| `orders` | every purchase order, with its lines and agreed prices |
| `shipments` | every shipment, with route, mode, dates and what it covered |
| `invoices` | the truth of every invoice written |
| `chains` | order joined to goods, shipment, freight and landed cost |
| `counts` | totals, including how many defects were injected |

### A chain

```json
{
  "order_number": "PO-41011",
  "factory": "HCV",
  "raised_on": "2026-02-02",
  "ordered_value": "4245.00",
  "goods_invoices": ["HCV-2026-3107"],
  "shipments": ["B/L MRK7000106"],
  "freight_invoices": ["MRK-2026-3108", "KNG-2026-3209"],
  "freight_share": {"MRK-2026-3108": "1512.40", "KNG-2026-3209": "988.02"},
  "credit_notes": [],
  "goods_total": "1996.59",
  "freight_total": "2500.42",
  "credit_total": "0.00",
  "landed_cost": "4497.01",
  "fully_shipped": true
}
```

`freight_share` exists because a container carries more than one order. Each
freight invoice is split between the orders aboard it, by cargo value.
`freight_total` is the sum of this order's slices, not of the whole invoices.

Why: [freight is split between orders](explanation.md#why-freight-is-split-between-orders),
and [a factory waits before shipping](explanation.md#why-a-factory-waits-before-shipping).

---

## Modules

### The business

| Module | Responsibility |
|---|---|
| `buyer.py` | Moty: name, department, address, tax number, delivery dock |
| `issuers.py` | the ten issuers, with their habits and price bias |
| `catalogue.py` | sixteen components: weight, base price, pack size, HS code |
| `lanes.py` | each factory's port, the carriers that serve it, transit days |
| `orders.py` | `PurchaseOrder`, `Shipment`, `Dispatch`, `OrderLine` |
| `invoice.py` | `Invoice` and `Line`, and the arithmetic over them |

### Making it happen

| Module | Responsibility |
|---|---|
| `operation.py` | the eight week clock; the only module that knows the order of events |
| `pricing.py` | the distributions, and the surcharge bands |
| `defects.py` | duplicates, revisions, credit notes, wrong order references |
| `invoice_builder.py` | one invoice outside the simulation, for `run.py` without `--weeks` |
| `ledger.py` | the answer key, including the freight apportionment |

### Drawing the page

| Module | Responsibility |
|---|---|
| `render.py` | `build_invoice(folder, invoice, issuer) -> Path` |
| `layouts.py` | which columns and labels each issuer's page uses |
| `page_drawing.py` | geometry, the column grid, address blocks, totals rows |
| `page_styles.py` | the seven table designs and the three totals designs |
| `formatting.py` | `format_amount`, `format_price`, `format_quantity`, `format_date` |

### The mailbox

| Module | Responsibility |
|---|---|
| `mail_delivery.py` | SMTP, the keychain, the envelope, the subject lines |
| `mail_sources.py` | `LocalMailbox` and `ImapMailbox`, both yielding `Message` |
| `watcher.py` | IMAP IDLE, renewal, reconnection, the hourly sweep |

### Reading it back

| Module | Responsibility |
|---|---|
| `reading.py` | text to `ReadInvoice`, with no knowledge of the issuers |
| `intake.py` | the three questions, and the two CSV files |

The folder tree these sit in is drawn in [the README](../README.md). Why
`reading.py` is kept ignorant: [the reader is blind](explanation.md#why-the-reader-is-blind).

---

## Page styles

| Style | Table | Totals |
|---|---|---|
| `grid` | every cell bordered | three right aligned rows |
| `zebra` | filled header, alternating tints | last row on a coloured band |
| `banded` | coloured rule under the header | last row on a coloured band |
| `minimal` | no rules, grey headings | three right aligned rows |
| `dashed` | dashes between the rows | three right aligned rows |
| `form` | closed grid, totals printed above | already printed |
| `ledger` | double ruled, landscape | three right aligned rows |

One invoice of each style sits in [the samples folder](../samples/README.md).
To give a new issuer one: [add an eleventh issuer](how-to.md#add-an-eleventh-issuer).

---

## Distributions

| Quantity | Shape | Set in |
|---|---|---|
| Unit price | lognormal around the catalogue price | `pricing.unit_price` |
| Supplier bias | fixed per issuer, 0.83 to 1.21 | `issuers.py` |
| Spread | fixed per issuer, 0.06 to 0.19 | `issuers.py` |
| Volume discount | four steps, 1.00 down to 0.86 | `pricing._volume_discount` |
| Order size | 2 to 60 packs, weighted to the middle | `pricing.order_quantity` |
| Freight rate | lognormal around a base per mode | `pricing.freight_rate` |
| Surcharge | a band per named charge | `pricing.SURCHARGE_BANDS` |
| Lead time slip | 0, 3, 7 or 14 days | `operation._lead` |
| Transit | per lane, 30 to 46 days by sea | `lanes.LANES` |

A unit price keeps three or four decimals when it is under a dollar. Rounding
a cap to two places would throw away the difference between 0.0615 and
0.0628, which is the whole point of having a distribution.

Why: [prices are drawn and not fixed](explanation.md#why-prices-are-drawn-and-not-fixed),
and [surcharges have their own bands](explanation.md#why-surcharges-have-their-own-bands).
How: [get the same invoices twice](how-to.md#get-the-same-invoices-twice).

---

## Defect rates

| Defect | Rate | Where |
|---|---|---|
| Resend | 6% | `defects.DUPLICATE_CHANCE` |
| Revision | 5% | `defects.REVISION_CHANCE` |
| Credit note | 4% | `defects.CREDIT_CHANCE` |
| Wrong order quoted | 7% | `defects.WRONG_ORDER_CHANCE` |
| Partial shipment | 15% | `operation.PARTIAL_CHANCE` |
| Demurrage | 18% | `operation.DEMURRAGE_CHANCE` |

Why: [defects are injected on purpose](explanation.md#why-defects-are-injected-on-purpose).
How: [change how often things go wrong](how-to.md#change-how-often-things-go-wrong).

---

## Tests

| File | Covers |
|---|---|
| `test_formatting.py` | how numbers and dates are written |
| `test_invoice.py` | the arithmetic and the answer key |
| `test_pricing.py` | the distributions behave as claimed |
| `test_invoice_builder.py` | one-off invoices stay sane and stay different |
| `test_operation.py` | the eight weeks behave like a business |
| `test_ledger.py` | the chains add up and nothing is billed twice |
| `test_render.py` | every issuer's page carries what it must |
| `test_mail.py` | the envelope, the subject, the attachment, the folder mailbox |
| `test_reading.py` | the reader, on plain text, and that it stays blind |
| `test_intake.py` | the three questions, and that nothing is ever dropped |

253 tests. `python -m pytest` runs them in about six seconds.

To run part of it: [run one part of the test suite](how-to.md#run-one-part-of-the-test-suite).
