# Message execution checklist

Follow the [parent skill](../../../SKILL.md) and
[maintained runbook](../../../references/reconciliation-and-messaging.md).

1. Confirm authorization and native account/property/tenancy identity. Messaging
   does not authorize financial changes or a broader audience.
2. Read the fully paginated native thread through the exact Hemlane API host.
   GraphQL POST queries are reads. Compose from verified records; exclude private
   owner notes and unsupported outstanding-balance claims.
3. Preview using the maintained sender with expected user, property, tenant-group
   ID and exact body. Apply the authorized digest with private runtime auth and a
   new journal. MCP apply additionally requires trusted host caller configuration.
4. Verify the native message ID, exact text, expected author and visibility. An
   uncertain result requires original-journal `--verify-only`, never resending.
5. If needed, capture credentials through the configured existing browser bridge
   and a Hemlane tab. Refuse alternate profiles/ports and unrelated tabs.

Stop on scope mismatch, incomplete pagination, auth/validation failure, rate limit
or uncertain delivery. Report safe status and private receipt path, not raw private
responses or credentials. Optional HAR discovery is described in the containing
skill and is not a runtime dependency.
