---
type: Note
title: Project 01, every file in reading order
description: The invoice pipeline read from the README to the last file, in the order the data flows, each folder followed by its tests.
status: stable
---

# Project 01, every file in reading order

Paths are inside `Portfolio/manual/01-invoice-pipeline/`. Tick each one.

## 1. The documents

- [ ] `README.md`
- [ ] `docs/tutorial.md`
- [ ] `docs/reference.md`

## 2. Setup

- [ ] `requirements.txt`
- [ ] `pytest.ini`
- [ ] `.gitignore`
- [ ] `.dockerignore`
- [ ] `Dockerfile`

## 3. business: the world being billed

- [ ] `src/business/buyer.py`
- [ ] `src/business/catalogue.py`
- [ ] `src/business/invoice.py`
- [ ] `src/business/issuers.py`
- [ ] `src/business/lanes.py`
- [ ] `src/business/orders.py`
- [ ] `src/business/tariffs.py`
- [ ] `src/business/profiles.py`
- [ ] `tests/conftest.py`
- [ ] `tests/business/test_buyer.py`
- [ ] `tests/business/test_catalogue.py`
- [ ] `tests/business/test_invoice.py`

## 4. simulation: making the year happen

- [ ] `src/simulation/pricing.py`
- [ ] `src/simulation/fx.py`
- [ ] `src/simulation/builder.py`
- [ ] `src/simulation/freight.py`
- [ ] `src/simulation/customs.py`
- [ ] `src/simulation/defects.py`
- [ ] `src/simulation/anomalies.py`
- [ ] `src/simulation/lookalikes.py`
- [ ] `src/simulation/newcomers.py`
- [ ] `src/simulation/operation.py`
- [ ] `src/simulation/ledger.py`
- [ ] `src/simulation/erp.py`
- [ ] `src/simulation/labels.py`
- [ ] `tests/simulation/test_pricing.py`
- [ ] `tests/simulation/test_builder.py`
- [ ] `tests/simulation/test_freight.py`
- [ ] `tests/simulation/test_freight_charges.py`
- [ ] `tests/simulation/test_customs.py`
- [ ] `tests/simulation/test_anomalies.py`
- [ ] `tests/simulation/test_lookalikes.py`
- [ ] `tests/simulation/test_operation.py`
- [ ] `tests/simulation/test_backlog.py`
- [ ] `tests/simulation/test_ledger.py`
- [ ] `tests/simulation/test_erp.py`

## 5. drawing: the invoice as a PDF

- [ ] `src/drawing/formatting.py`
- [ ] `src/drawing/layouts.py`
- [ ] `src/drawing/parts.py`
- [ ] `src/drawing/styles.py`
- [ ] `src/drawing/render.py`
- [ ] `src/drawing/scan.py`
- [ ] `tests/drawing/test_formatting.py`
- [ ] `tests/drawing/test_render.py`
- [ ] `tests/drawing/test_scan.py`

## 6. mail: sending and receiving

- [ ] `src/mail/request.py`
- [ ] `src/mail/replies.py`
- [ ] `src/mail/delivery.py`
- [ ] `src/mail/sources.py`
- [ ] `src/mail/watcher.py`
- [ ] `tests/mail/test_mail.py`
- [ ] `tests/mail/test_replies.py`
- [ ] `tests/mail/test_arrival.py`

## 7. reading: the PDF back into rows

- [ ] `src/reading/fields.py`
- [ ] `src/reading/ocr.py`
- [ ] `src/reading/intake.py`
- [ ] `tests/reading/test_fields.py`
- [ ] `tests/reading/test_intake.py`
- [ ] `tests/reading/test_seen.py`
- [ ] `tests/reading/test_ocr.py`
- [ ] `tests/reading/test_cost_fields.py`
- [ ] `tests/reading/test_brazil_documents.py`
- [ ] `tests/reading/test_santos_documents.py`

## 8. costing: what each part cost

- [ ] `src/costing/landed.py`
- [ ] `src/costing/kpis.py`
- [ ] `src/costing/truth.py`
- [ ] `tests/costing/test_landed.py`
- [ ] `tests/costing/test_kpis.py`
- [ ] `tests/costing/test_at_volume.py`

## 9. runs: the commands

- [ ] `src/runs/modes.py`
- [ ] `src/runs/smoke.py`
- [ ] `src/runs/backlog.py`
- [ ] `src/runs/report.py`
- [ ] `run.py`
- [ ] `watch.py`
- [ ] `tests/runs/conftest.py`
- [ ] `tests/runs/test_modes.py`
- [ ] `tests/runs/test_smoke_freight.py`
- [ ] `tests/runs/test_smoke_senders.py`
- [ ] `tests/runs/test_smoke_forward.py`
- [ ] `tests/runs/test_smoke_reading.py`
- [ ] `tests/runs/test_backlog_run.py`
- [ ] `tests/runs/test_dataset.py`
- [ ] `tests/runs/test_report.py`

## 10. monitoring: what the dashboard counts

- [ ] `src/monitoring/metrics.py`
- [ ] `monitoring/docker-compose.yml`
- [ ] `monitoring/prometheus.yml`
- [ ] `monitoring/grafana/provisioning/datasources/prometheus.yml`
- [ ] `monitoring/grafana/provisioning/dashboards/pipeline.yml`
- [ ] `monitoring/grafana/dashboards/pipeline.json`
- [ ] `tests/monitoring/conftest.py`
- [ ] `tests/monitoring/test_metrics.py`

## 11. Last

- [ ] `tests/test_doc_links.py`
- [ ] `Invoices/samples/truth.json` and one sample PDF
