# Upwork portfolio item

**Title:** Invoice Pipeline: Mailbox to Costed Rows, 992 of 1,003 Read
Without a Human

**Role:** Data engineer and Python developer

**Skills:** Python, Data Engineering, OCR, PDF, IMAP, Docker,
Prometheus, Grafana

**Media:** `dashboard.png`, `monitoring.png`

**Description:**

An importer's cost department had months of supplier invoices sitting
in a mailbox and nothing filed. This pipeline sits on that mailbox and
turns it into rows.

It e-mails every sender asking for everything issued since January,
waits on the inbox over IMAP IDLE so a document is picked up the moment
it lands, reads each PDF, files it as new, revised or a duplicate, and
costs every part in reais.

What it is up against, and handles:

- **Thirteen issuers, each printing its own way.** The same date arrives
  as `2026-04-11`, `04/11/2026` or `11/04/2026`; amounts as `1,234.56`
  or `1.234,56`
- **Two senders scan.** Cheap black-and-white scans, half of them
  askew, read with OCR
- **Resends, revisions and credit notes**, as in any real inbox
- **It never guesses.** If the lines do not add up to the printed total,
  or a date cannot be read, the row goes to a person with the reason

Measured on the real run of 1,003 documents, January to October:

| Arrives as | Read right | Sent to a person | Wrong and not caught |
|---|---|---|---|
| PDF with text | 900 / 900 | 0 | 0 |
| Scan, good | 82 / 82 | 0 | 0 |
| Scan, poor | 8 / 8 | 0 | 0 |
| Scan, poor and askew | 2 / 13 | 11 | 0 |
| **All** | **992 / 1,003** | **11** | **0** |

Nothing was read wrong and passed off as right. That is the number that
matters: a pipeline that quietly files a wrong figure is worse than one
that asks.

- 635 automated tests, none touching the network
- Six Grafana panels watching the run, one per stage a document travels
- Docker deploy

The costed rows feed a landed cost dashboard and an anomaly model, both
separate projects.
