# Hemlane runbooks

## Referral submit
1. Use `references/graphql-operations.md` and locate `HubspotFormSubmit`.
2. Reconstruct the mutation payload with fields for first name, last name, phone, email, referrer name, and referrer email.
3. Supply the currently verified `formId`, referrer name and email explicitly. The maintained wrapper builds its payload from these inputs, without captured personal values.
4. Preview with `scripts/submit_hemlane_referral.py`. Apply an authorized exact digest with a fresh private journal and runtime credentials; MCP also requires trusted caller configuration.
5. Independently verify `hubspotFormSubmission.id`, empty `errors` and the native submission before reporting completion. Uncertain outcomes require readback, never automatic replay.

Key operation:
- `HubspotFormSubmit`

## Tenant reply
Use [reconciliation-and-messaging.md](reconciliation-and-messaging.md) for the
maintained preview/apply/verify-only path. The steps below describe native contracts;
they do not bypass account scope, journals or the read-after-write requirement.
1. Identify the target tenant group ID from `ODTenantsAndLeasesTenantGroups` or an existing message thread.
2. Optionally re-read context with:
   - `TGTenantGroup`
   - `OwnerTenancyMessages`
3. Send the reply with the confirmed HAR-derived mutation:
   - `ODProspectiveTenantGroupMessageCreate`
4. Use `scripts/send_hemlane_tenant_reply.py` for the live wrapper.
5. Confirm by re-querying `OwnerTenancyMessages` after submit.

Confirmed live mutation:
- `ODProspectiveTenantGroupMessageCreate`
- field alias: `tenantGroupMessageAdd: tenantGroupMessageAdd2(input: $input)`

## Maintenance / work-order comment
1. Find the maintenance request or work order ID from the UI or prior query.
2. Query request/work-order details first to confirm the record:
   - `OwnerDashboardMaintenanceMaintenanceRequest`
   - `OwnerDashboardMaintenanceMaintenanceRequestComments`
   - `OwnerDashboardMaintenanceMaintenanceRequestWorkOrders`
   - `OwnerMaintenanceWorkOrder`
   - `OwnerMaintenanceWorkOrderComments`
3. Post the comment using the matching create mutation:
   - `OwnerDashboardMaintenanceMaintenanceRequestCommentCreate`
   - or `OwnerMaintenanceWorkOrderCommentCreate`
4. Include visibility flags exactly as captured (`isHiddenFromTenants`, `isHiddenFromOwners`) when applicable.
5. Re-query comments after submit to verify persistence.

## Transaction lookup
1. Use `PagedFinancialTransactions` or `TransactionsNextCursorQuery` to page through transactions.
2. Use `FinancialsScheduledActionPanelStats` for summary context and `GetPlaidSyncItems` if bank-sync state matters.
3. Preserve pagination variables/cursors from the captured pattern.
4. Re-run query with tighter filters (property, owner, due date, category) when narrowing a result set.
5. Validate by comparing total count / next cursor / returned transaction IDs.

## Payment reconciliation / adjustments / ledger communications

Read [reconciliation-and-messaging.md](reconciliation-and-messaging.md).
Never infer received money from an override or infer current balance from charge sums.

## Workflow-specific wrappers
- `scripts/submit_hemlane_referral.py`
- `scripts/post_hemlane_workorder_comment.py`
- `scripts/post_hemlane_maintenance_request_comment.py`
- `scripts/send_hemlane_tenant_reply.py`
