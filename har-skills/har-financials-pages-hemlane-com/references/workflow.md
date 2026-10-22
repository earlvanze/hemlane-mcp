# Financial reconciliation execution checklist

Follow the [parent skill](../../../SKILL.md) and
[reconciliation runbook](../../../references/reconciliation-and-messaging.md).

1. Confirm authorized read/write scope and native account/property/record identity.
2. Fully paginate requests/payments and inspect recurring terms, scheduled
   instructions and bookkeeping mirrors. Use the exact Hemlane API endpoint.
3. Verify bank receipts and responsibility for any remainder. Run the offline
   allocation planner with periods, unique bank IDs, balanced allocations, existing
   billed amounts and actual responsible-party receipts. Exclude unverified periods.
4. Assign each period one treatment. Preserve existing unpaid charges; compute
   newly unbilled differences separately. Regular corrections and historical
   adjustments must not include the same difference twice.
5. For authorized live corrections, prepare immutable before/after terms and digest,
   journal before submission, preserve unrelated terms/payments and independently
   verify all affected records and authorized mirrors. No general live apply engine
   is supplied by this planner or optional corpus integration.
6. On interruption, timeout or ambiguous result, stop and read exact native records.
   Never automatically retry or use another journal to evade an unresolved outcome.
7. Communicate charge amounts, receipts, scheduled instructions and native balance
   separately. Use the channel's scoped preview/apply/verify workflow for any message.

Stop on missing session, scope mismatch, incomplete pagination, unverified evidence,
auth/validation failure or rate limit. Report safe status and private evidence paths.
Browser capture uses the explicitly configured existing bridge and Hemlane tab;
no alternate browser/profile/port probing. External corpus tooling is optional.
