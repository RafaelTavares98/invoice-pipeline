# Explanation

[README](../README.md) · [Tutorial](tutorial.md) · [How-to](how-to.md) ·
[Reference](reference.md) · **Explanation**

Why the project is built this way. Nothing here is needed to run it.

Each section argues one decision. The figures and the names behind it are in
[the reference](reference.md); the way to change it is in
[the how-to guide](how-to.md).

---

## Why generate invoices at all

A reader of invoices can only be judged against known answers. Real invoices
do not come with answers; somebody would have to type them in, and that
person would make mistakes at about the rate the reader does.

Inventing the invoices solves that. The generator knows the total because it
chose the total. The reader has to find it. The gap between the two is the
score, and it is not an opinion.

The cost of this is that the corpus is only as hard as it was made. A reader
that scores well here has proved it can read these ten issuers, not that it
can read anything.

---

## Why the reader is blind

An earlier version of this project shared one file between the two halves: a
layout description that said how each issuer printed its pages. The generator
drew with it, and the reader parsed with it.

That reader did not read invoices. It looked up which issuer had printed the
page, found out from the file that this issuer writes `Invoice no.`, and then
searched for `Invoice no.`. The accuracy it reported was inflated, because
half the answer was in the configuration.

A client does not hand over the layout file their supplier printed with.

So `reading.py` imports nothing from `issuers.py` and nothing from
`layouts.py`. It is given text and has to work out the rest:

| What it needs | How it decides |
|---|---|
| decimal mark | counts how many figures end `,00` against how many end `.00` |
| date order | ISO is unmistakable; otherwise a number above twelve can only be a day |
| issuer | the name printed under FROM, before anybody else's |
| the table | the heading row, found by its column names |

Each of those can be wrong. That is the point.

The two modules that do this are listed under
[reading it back](reference.md#reading-it-back). A test enforces the
isolation; see [tests](reference.md#tests).

---

## Why the table is found by its heading

The first version of the row reader took any line holding two or more
figures. It produced subtotals in the millions.

A page is full of numbers that are not prices:

```
Rodovia Anhanguera, km 94, Galpao 3
Louveira, SP 13290-000
CNPJ: 18.442.907/0001-55
ICBC Guangzhou SWIFT ICBKCNBJGDX Acct 3602 0012 9100
```

The bank account line was the worst. `Acct 3602 0012 9100` read as a line
item worth 9,100.

Two rules fixed it, and both are what a person does without thinking:

1. The table starts at its heading. Find the heading, start there.
2. A table is one unbroken block. When prose resumes, the table is over.

---

## Why the quantity column is counted from the right

A goods table reads: part number, description, HS code, quantity, unit price,
amount. A freight table reads: description, units, weight, volume, rate,
amount.

Counting from the left fails, because the description holds numbers of its
own: a `24/410` neck, a `1.2 cc` pump, a `30 ml` pipette.

Counting a fixed number of places from the right fails too. In the goods
table the quantity is the third figure from the right. In the freight table
it is the fifth, because weight and volume sit in between.

So the heading is parsed once, the distance from quantity to amount is
counted in columns that carry a figure, and each row is read at that
distance. When a row has fewer figures than that, because a surcharge leaves
the weight and volume cells empty, the quantity is whatever the amount
divided by the price must have been.

The columns this produces are in
[`data/invoice_lines.csv`](reference.md#datainvoice_linescsv).

---

## Why the hash is the identity, not the invoice number

Three documents can share a number.

A supplier resends an invoice because nobody replied. Same number, same
figures, same PDF. Paying it twice is a real loss.

A supplier corrects an invoice. Same number, different figures, usually with
`-R1` on the end. Both documents now exist and only one is owed.

The invoice number is therefore not an identity. The bytes of the PDF are.
Three questions settle every arriving file:

```
hash already seen             -> a resend. Skip it.
number seen, hash is new      -> a revision. The old row is superseded.
neither                       -> a new document.
```

A number is still useful for joining, which is why both CSV files carry it.
But the join that is always safe is on the hash.

The four answers this produces are tabulated in
[what each status means](reference.md#what-each-status-means). Seeing it
happen: [step 6 of the tutorial](tutorial.md#step-6-read-the-mailbox-back).

---

## Why nothing is ever dropped

A file that cannot be read gets a row saying `unreadable`, with the reason.

The tempting alternative is to skip it and carry on. The pipeline then reports
a hundred invoices read out of a hundred it chose to mention, and the two it
could not read are gone. A line the pipeline hides is a line nobody learns
about, and the one it hides is the odd one, which is the one worth seeing.

To read the reasons it recorded:
[find out why one invoice was not read](how-to.md#find-out-why-one-invoice-was-not-read).

---

## Why prices are drawn and not fixed

Two invoices for the same part are almost never identical. A quote moves with
the month, the volume, and how badly the supplier wants the order.

A corpus of constant prices lets a reader succeed by memorising, and lets any
analysis downstream find a signal that was never there. Worse, it hides
rounding faults: a bug that drops a decimal looks fine when every number is
the same.

So a price is lognormal around the catalogue figure, shifted by a bias fixed
per supplier and pulled down in steps by order size. Hanil is expensive and
consistent. Aravalli is cheap and erratic. Those are properties of the
supplier, held across every invoice it issues, which is what makes supplier
comparison a real question rather than a lottery.

Freight moves more than goods do, so it is drawn with a wider spread.

The shapes and the figures: [distributions](reference.md#distributions). To
pin a run so it repeats:
[get the same invoices twice](how-to.md#get-the-same-invoices-twice).

---

## Why surcharges have their own bands

The first version drew every surcharge from one band of 55 to 980 dollars.
Freight then came to more than the goods it carried, three times over.

A documentation fee is not the size of inland haulage. Giving each named
charge its own band brought freight to about 13% of goods value, which is
where packaging imports from Asia actually sit.

The lesson is older than this project: a distribution with the right shape and
the wrong scale is still wrong, and it is wrong in a way that looks plausible
on the page.

---

## Why a factory waits before shipping

A container costs the same half full. A factory with one order ready does not
sail; it waits for a second, or for a week, whichever comes first.

Removing that rule would make every shipment carry one order, which is tidy
and false. It would also remove the only interesting problem in the ledger,
which is the next section.

The wait is `WAIT_DAYS` in `operation.py`; the clock it belongs to is under
[making it happen](reference.md#making-it-happen).

---

## Why freight is split between orders

A container carrying two purchase orders produces one freight invoice. The
naive ledger charges the whole invoice to both orders, and the landed cost of
everything is overstated.

So each freight invoice is apportioned across the orders aboard its shipment,
by cargo value. A test asserts that the slices of one invoice never add up to
more than the invoice.

Apportioning by value is a choice, not a law. By weight would be defensible
too, and would charge the glass more and the labels less. By value is what a
cost department usually does, because it is the figure already on the page.

What the split looks like in the answer key:
[a chain](reference.md#a-chain). Reading one as a sentence:
[step 4 of the tutorial](tutorial.md#step-4-run-eight-weeks-instead-of-ten-invoices).

---

## Why defects are injected on purpose

A clean corpus proves only that a reader can read clean documents, which no
inbox contains.

| Defect | What it breaks |
|---|---|
| Duplicate | a pipeline keyed on the invoice number |
| Revision | a pipeline that pays the first document it sees |
| Credit note | an arithmetic that assumes totals are positive |
| Wrong order quoted | a join that trusts the reference printed on the page |
| Partial shipment | an assumption that one order means one invoice |

Each is a thing a freight desk sees in a normal month. The rates are small
enough to be realistic and large enough to appear in eight weeks.

The rates: [defect rates](reference.md#defect-rates). To change them:
[change how often things go wrong](how-to.md#change-how-often-things-go-wrong).

---

## Why the window needs a warm start

A lead time is 35 to 55 days. A crossing is another 30 to 46. An order raised
on the first Monday of an eight week window would arrive long after the window
closed, and the first six weeks would be empty.

So the simulation opens thirteen weeks early, builds a backlog already in
production, runs the whole period, and then keeps only the paperwork dated
inside the window. The orders that produced it still exist in the ledger, with
their earlier dates, because a chain that starts outside the window is still
a chain.

To make the window longer or shorter:
[change how long the window is](how-to.md#change-how-long-the-window-is).

---

## Why IMAP IDLE instead of a timer

A timer that checks every fifteen minutes is simple and wrong in both
directions: it is idle most of the time and late when it matters.

IMAP has a command called IDLE. The client stops talking and the server pushes
a line the moment a message lands. That is a trigger rather than a clock.

Its three weaknesses are handled rather than ignored:

- Gmail hangs up on an idle connection after about half an hour, so the IDLE
  is renewed every ten minutes.
- Connections drop, so the watcher reconnects with a growing wait.
- A push can be missed, so a full sweep runs every hour. The hash makes the
  second look harmless.

The alternative with a genuine push and no long-running process is the Gmail
API with a Cloud Pub/Sub subscription. It needs a cloud project, a topic, and
a public endpoint. For ten invented suppliers that is out of proportion.

To start the watcher:
[watch a real mailbox](how-to.md#watch-a-real-mailbox-and-read-invoices-as-they-arrive).
Without a server at all:
[read invoices without any mail server](how-to.md#read-invoices-without-any-mail-server).

---

## Why the name on the envelope is not the address

Ten suppliers send mail, from one real account.

A free account cannot send from a domain it does not own. Forging the address
gets the message refused at the door, or filed as spam, which teaches nothing
about reading invoices.

So the display name is the issuer and the address is the one real account,
tagged:

```
"Ningbo Caplink Industrial Co., Ltd." <you+ncl@gmail.com>
```

Everything after the plus sign is ignored on delivery, so all ten land in one
inbox and can still be told apart by a filter.

One detail cost an hour. Half these names hold a comma, and a comma pasted
straight into a `From` header splits it into two addresses. The header has to
be built by the mail library, not by string formatting.

---

## Why the password is in the keychain

An environment variable sits in plain text in the registry, in the shell
history, and in reach of every program running as that user. It also leaks
into logs and into any error message that prints the environment.

The operating system keychain encrypts the value and ties it to the login.
The program reads it, never prints it, and never writes it anywhere.

It is set once, by hand, by a tool that is not this program:

```bash
python -m keyring set invoice-pipeline you@example.com
```

The whole recipe:
[send the invoices as real e-mail](how-to.md#send-the-invoices-as-real-e-mail).

---

## What this project is not

It does not pay invoices, file them anywhere, or talk to an accounting
system. It does not decide whether a charge is fair. It does not read a
scanned page, because nothing here produces one.

It makes invoices that look real and reads them back, so that a reader can be
measured against an answer key rather than against an opinion.
