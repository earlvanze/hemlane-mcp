# Hemlane MCP

Native Hemlane GraphQL tools, reusable workflow skills and offline reconciliation.
Credentials and business evidence are supplied at runtime. See [SKILL.md](SKILL.md)
for operator instructions and [runbooks](references/runbooks.md) for native routing.

## Reusable workflows

- Allocate verified external-payer receipts to periodic charges and calculate the
  responsible party's adjustment, excluding amounts already billed. The offline
  planner uses generic account/property/record scope and explicit confirmation of
  responsibility; it has no organization, assistance program or tenant defaults.
- Preview tenant replies, check account/property/thread identity, journal one
  authorized submission and verify native delivery. Recover uncertain sends with
  read-only verification using the original journal.
- Preview referrals and maintenance/work-order comments. Apply requires an exact
  reviewed digest and a fresh private journal, then independent native readback.
- Retain catalog, tenant-group, maintenance, recurring-request and transaction
  reads. The historical rent-roll extractor fails closed pending contract review.

## Installation and runtime

Use Python 3.10+ on POSIX. Install `mcp` and `websocket-client` in the deployment's
Python environment and run `python mcp/server.py` over stdio from this checkout.
The standalone planner and replay transport use the standard library.

Configure the trusted stdio host with `HEMLANE_CALLER_ID` and comma-separated
`HEMLANE_ALLOWED_CALLER_SHA256`. Apply and credential capture fail closed unless
the host-supplied caller's SHA-256 matches the allowlist. Preview and other reads
remain available. Use separate trusted processes for different caller identities;
tool arguments cannot establish identity.

For browser auth capture, set `HEMLANE_CDP_URL` to the existing authenticated CDP
bridge (`BRAVE_CDP_URL` is also accepted). There is no implicit endpoint/profile
fallback. Supply a new private output file; credential values are never printed by
capture. Use a verified Hemlane account and authorized records. Runtime credential
files, journals, financial evidence and raw HAR captures must stay out of Git.
Standalone CLI access relies on OS credential isolation and operator authorization.

## Preview, apply and recovery

Maintained mutation wrappers default to preview without reading credentials or
sending requests. Authorized apply requires `--apply`, `--confirm-digest` and
`--journal`, plus runtime credentials. A digest binds a plan; it does not authorize
it. Never retry uncertain mutations automatically or bypass a journal by changing
its filename. Generic replay returns `submitted_readback_required`, not verified
completion. Journal checks do not provide distributed server-side idempotency.

Read [reconciliation and communications](references/reconciliation-and-messaging.md)
for the synthetic planner schema, balance semantics and native message verification.
Attachments need independent content verification. Corpus discovery is optional;
no separately installed corpus server or captured personal payload is required.

## Offline verification

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The suite uses synthetic evidence, mocked API/CDP calls and real local MCP stdio
previews. It makes no live financial changes or sends. One optional corpus test
requires Node.js and `HAR_CORPUS_SERVER` pointing to a separately installed server;
it is skipped by default. GitHub Actions runs the self-contained offline suite.
