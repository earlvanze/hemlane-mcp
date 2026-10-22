---
name: har-financials-pages-hemlane-com
description: Review Hemlane financial records and plan bank-backed payment allocations and responsible-party adjustments. Optionally discover contracts through sanitized financial-page HAR metadata.
---

# Hemlane financial reconciliation workflow

Read the [parent skill](../../SKILL.md) and
[reconciliation runbook](../../references/reconciliation-and-messaging.md).

1. Confirm current account/property/record scope and read/write authorization.
   Read fully paginated native requests, payments, recurring terms, scheduled
   instructions and bookkeeping mirrors using the exact Hemlane API host.
2. Establish verified bank receipts, unique IDs, posted dates and period
   allocations. Verify the agreement determining responsible parties; do not
   infer liability from external-payer deposits alone.
3. Use `reconcile_payment_allocations.py` / MCP `plan_payment_reconciliation`
   offline. Supply existing billed amounts separately from cash paid. Balance
   combined deposits, retain signed credits and give each period one treatment.
4. Before an authorized correction, prepare exact before/after records, source
   evidence, digest and durable per-step journal. Preserve unrelated request
   terms and real/failed/pending/scheduled payments. Replace identified manual
   overrides only; the planner does not execute live corrections.
5. Independently read back affected records and authorized mirrors. Distinguish
   charge totals, receipts, scheduled instructions and native remaining balance.
   Stop on uncertain mutations; never replay a batch or evade its journal.

Current authorization persists within its scope. Earlier no-write restrictions
remain until the specific changes are authorized. GraphQL POST queries are reads.
Generic replay does not replace scoped financial preflight and native readback.

When browser capture is required, configure `HEMLANE_CDP_URL` (or legacy
`BRAVE_CDP_URL`) for the existing authenticated bridge and use an existing Hemlane
tab. Keep auth and financial evidence private; do not probe alternate profiles,
launch browsers or navigate unrelated tabs.

Optional discovery: a separately installed HAR corpus service may expose sanitized
`financials-pages-hemlane-com` metadata (source basename
`financials_pages_hemlane.com.har`). Templates are discovery sketches; verify the
selected endpoint host. Analytics/PubNub origins do not verify financial balances.
This workflow bundles no raw captures and does not require external corpus tools.

See the [execution checklist](references/workflow.md).
