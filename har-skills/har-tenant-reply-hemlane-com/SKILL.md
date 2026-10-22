---
name: har-tenant-reply-hemlane-com
description: Use native Hemlane threads for scoped message previews, verified tenant-visible sends and read-only recovery. Optionally inspect sanitized HAR metadata when discovering a contract.
---

# Hemlane message workflow

Read the [parent skill](../../SKILL.md) and
[communication runbook](../../references/reconciliation-and-messaging.md).

1. Confirm authorized account, property, tenancy and audience from current records.
   Read the native current user and fully paginated thread before composing text.
   Keep owner-private content out of tenant-visible messages.
2. Business reads use `https://api.hemlane.com/graphql` (optional trailing slash).
   GraphQL POST queries are reads. Analytics/PubNub traffic is not authoritative
   account or message evidence.
3. Preview with maintained `send_hemlane_tenant_reply.py` / MCP `send_tenant_reply`.
   Bind body and scope in the digest. Apply an authorized exact digest with runtime
   auth and a new private journal; independently verify native ID, author, body and
   tenant-visible flags before reporting completion.
4. If submission/readback is uncertain, retain the original journal and use
   `--verify-only` / MCP `verify_tenant_reply`. Never automatically resend or evade
   an unresolved journal with another path.

Current destination-specific authorization persists within its scope. Different
recipients, visibility or ledger changes need authorization covering those actions.

Browser capture requires `HEMLANE_CDP_URL` (or legacy `BRAVE_CDP_URL`) for the
existing authenticated browser and an existing Hemlane tab. Do not launch profiles,
probe ports or navigate unrelated tabs. Credentials stay in new private files;
stdout contains metadata only.

Optional discovery: if a separate HAR corpus service is installed, inspect its
sanitized `tenant-reply-hemlane-com` profile (source basename
`tenant-reply_hemlane.com.har`). Verify template hosts against the selected
endpoint, not a profile primary origin. Captured credentials/payload values must
not be reused. This skill does not bundle raw captures or require corpus tools.

See the [execution checklist](references/workflow.md).
