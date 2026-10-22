---
name: hemlane
description: Operate Hemlane through native GraphQL and existing browser sessions. Use for payment allocation and reconciliation, financial requests, scoped messages, referrals, maintenance, and HAR contract discovery.
---

# Hemlane

Use maintained scripts for repeatable native Hemlane operations. Confirm the
current account and target records. Operator authorization determines allowed
writes and audiences; a digest records an exact plan, not permission.

## Reconciliation and communication

Read [reconciliation-and-messaging.md](references/reconciliation-and-messaging.md)
for verified receipt allocation, responsible-party adjustments, historical manual
payment corrections, balance interpretation, messages and ledger attachments.

- `scripts/reconcile_payment_allocations.py` / MCP `plan_payment_reconciliation`
  produce offline plans for periodic charges split between external payers and a
  responsible party. Verify the agreement establishing responsibility; no customer,
  organization, property, period or assistance program is assumed.
- Deposits have unique IDs and balanced allocations. Existing billed amounts are
  separate from cash paid; adjustments must not duplicate existing arrears.
- Each period is adjusted historically, corrected on its regular request, or
  excluded. Credits remain signed; bookkeeping mirrors are separate records.
- Report charges, receipts, scheduled instructions and native remaining balance
  separately. Updating an instance does not change a recurring template.

## Mutation and delivery controls

Tenant replies and comment/referral wrappers default to preview. Apply requires
`--apply --confirm-digest <exact-preview-digest> --journal <new-private-file>` and
runtime credentials. Preview neither loads credentials nor sends a request.

`send_hemlane_tenant_reply.py` additionally requires tenant-group ID, expected user
ID and property ID. It checks native scope, complete pagination and duplicate text
before submission, then verifies message ID, author, body and visibility. Recover
uncertain outcomes with the original journal and `--verify-only` / MCP
`verify_tenant_reply`; recovery never sends. Attachments need independent content
verification. Other audiences require their own verified native contract.

Generic replay and legacy wrappers report `submitted_readback_required` after a
successful mutation. Independently verify native records before claiming completion.
Never automatically retry mutations or evade unresolved journals with new filenames.
These controls are not server-side idempotency across concurrent callers.

## Transport and credentials

Business GraphQL uses exactly `https://api.hemlane.com/graphql` (optional trailing
slash). POST queries are reads. Captured analytics/PubNub origins are not business
API hosts. Maintained transport refuses redirects and withholds raw error bodies.
Keep tokens, headers, threads and ledger evidence private.

For capture, configure `HEMLANE_CDP_URL` for the deployment's existing authenticated
CDP bridge; legacy `BRAVE_CDP_URL` is accepted. There is no implicit host/profile
fallback. Do not launch another browser, probe alternate ports or navigate unrelated
tabs. Capture requires an existing Hemlane UI tab and a new private `--out-file`;
existing files/symlinks are refused and stdout contains metadata only. Remove runtime
credentials after use.

## MCP deployment and caller policy

Run `mcp/server.py` over stdio using the deployment's Python interpreter and absolute
checkout path. Install `mcp` and `websocket-client` for MCP/capture runtime. The
standalone planner/replay use the standard library. Maintained private-file
safeguards target POSIX systems and Python 3.10+.

The trusted host must set `HEMLANE_CALLER_ID` and comma-separated
`HEMLANE_ALLOWED_CALLER_SHA256`. Identity comes from the host, never tool arguments
or message text. Apply and credential capture fail closed without a matching hash;
preview and non-capture reads remain available. Use separate trusted stdio processes
for different caller identities. Standalone CLI access relies on operating-system
credential isolation and operator authorization; a digest is not an access boundary.

## Discovery and compatibility

Use [runbooks.md](references/runbooks.md) for native operation routing and optional
HAR discovery. Captures describe historical contracts, not live account state. Do
not import stored auth or captured personal values into runtime payloads. External
corpus tools are optional and not bundled dependencies.

Existing native read tools are retained. The historical rent-roll extractor is
disabled until its native contract is verified; accurately label paginated native
query coverage instead.

## Offline verification

From the checkout root:

```sh
uv run --with-requirements requirements-dev.txt python -m unittest discover -s tests -v
```

Tests use synthetic evidence, mocked GraphQL/CDP and real local MCP stdio previews.
The optional corpus test requires `HAR_CORPUS_SERVER` pointing to a separately
installed JavaScript corpus server, plus Node.js. No test sends live messages or
changes financial records.
