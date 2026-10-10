# Samples

[README](../README.md) · [Tutorial](../docs/tutorial.md) ·
[How-to](../docs/how-to.md) · [Reference](../docs/reference.md) ·
[Explanation](../docs/explanation.md)

Ten invoices, one from each issuer, so that the pages can be looked at
without installing anything. `truth.json` beside them says what each one
really holds.

They are the output of:

```bash
python run.py
```

That command is seeded, so running it again writes these same ten files into
`out/`. They are not the eight week corpus; `python run.py --weeks` makes
that, and it is not committed because it rebuilds in seconds.

| File | Issuer | Page style |
|---|---|---|
| `NCL-2026-7579.pdf` | Ningbo Caplink Industrial | closed grid |
| `SBP-2026-1978.pdf` | Shantou Brightpack | tinted band |
| `GZV-2026-5910.pdf` | Guangzhou Verrelia Glassworks | boxed form, totals on top |
| `HCV-2026-8220.pdf` | Hanil Cosmetic Vessels | no rules at all |
| `BDT-2026-8413.pdf` | Binh Duong Tubeworks | dashed rows |
| `ARL-2026-4637.pdf` | Aravalli Labelworks | coloured rule |
| `DHI-2026-5192.pdf` | DHI Global Forwarding | wide ledger, air |
| `MRK-2026-1496.pdf` | Marsk Line Agencies | wide ledger, ocean |
| `CSM-2026-5070.pdf` | COSMO Shipping Lines | closed grid |
| `KNG-2026-8602.pdf` | Keuhne & Nager Logistics | coloured rule |

Three of them write a date the others would read backwards, and two write
`1.234,56` where the rest write `1,234.56`. That is the point of keeping one
of each.

The designs are described in
[page styles](../docs/reference.md#page-styles). What the reader has to work
out from these pages alone:
[why the reader is blind](../docs/explanation.md#why-the-reader-is-blind).
