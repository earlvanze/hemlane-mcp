# Payment reconciliation and verified communications

## Scope and evidence

Use for periodic charge allocations, external-payer receipts, manual payment
corrections, responsible-party adjustments and related communications. Identify
account, property, source record and parties from current evidence. External payers
may be co-payers, insurers, sponsors or assistance programs. The agreement and
operator determine who owes any remainder; external receipt alone does not prove
another party's liability.

Authorization persists within its scope. Summary requests do not authorize ledger
edits. Earlier read-only restrictions persist until specific writes are authorized.
Estimates, stale captures and unreachable sources remain unresolved rather than
becoming booked entries. Verify native account/destination identity before writes.
Bank receipts establish received money; manual overrides alone do not. Retain private
source IDs, bank posted dates and allocation evidence.

## Offline planner

Run `scripts/reconcile_payment_allocations.py --input /private/evidence.json` or MCP
`plan_payment_reconciliation`. It makes no network requests or ledger mutations.
Inputs use decimal dollars; outputs use integer cents.

Required scope: `userId`, `propertyId`, opaque `recordId` identifying the agreement,
tenancy or account. Additional scope fields are retained. Set
`responsibilityConfirmed` only after verifying responsibility for the remainder.
Deposits require unique IDs and allocations totaling the full amount. For deposits
covering several properties, establish an evidenced property allocation first; do
not mislabel an allocation as the original full bank deposit.

Synthetic example:

```json
{
  "scope": {"userId":"user-example", "propertyId":"property-example", "recordId":"agreement-example"},
  "responsibilityConfirmed": true,
  "periods": [
    {"month":"2030-01", "charge":"1000.00", "responsiblePaid":"150.00", "existingResponsibleCharge":"150.00", "verified":true, "treatment":"true_up"},
    {"month":"2030-02", "charge":"1000.00", "responsiblePaid":"150.00", "existingResponsibleCharge":"150.00", "verified":true, "treatment":"correct_regular"},
    {"month":"2029-12", "treatment":"exclude"}
  ],
  "deposits": [
    {"id":"bank-example", "amount":"1650.00", "postedDate":"2030-02-05", "verified":true,
     "evidenceRef":"private/bank-readback.json#bank-example",
     "allocations":[{"month":"2030-01", "amount":"825.00"}, {"month":"2030-02", "amount":"825.00"}]}
  ]
}
```

Corrected responsibility is $175 each period. January contributes $25 to the
historical adjustment; February is corrected on its regular request. Each period
has one treatment: `true_up`, `correct_regular`, or `exclude`.

`existingResponsibleCharge` is the verified net billed amount, including earlier
adjustments and excluding separate bookkeeping mirrors. New adjustment = corrected
responsibility minus existing billed charge. Existing unpaid amounts stay on their
original requests. `shortageOrCreditCents` separately describes responsibility minus
actual receipts. Credits stay signed; a negative result requires credit handling,
not a guessed charge/refund. External receipts exceeding the charge require separate
credit review. Exclude unverified periods.

Included periods require a positive, evidenced external receipt. A zero-receipt
period is excluded for separate review; this planner does not infer nonpayment
from missing deposits.

The planner validates arithmetic and declared evidence, not source authenticity.
Its digest binds the input/output but does not authorize or execute changes.

## Applying an authorized correction

1. Read native identity, requests/payments, recurring templates, scheduled
   instructions, fee terms and bookkeeping mirrors. Verify pagination completeness.
2. Prepare an immutable scoped plan with source evidence, IDs, before/after terms
   and digest. Use the latest correction/readback and record authorized scope.
3. Replace specifically identified historical manual overrides. Preserve real,
   failed, pending and scheduled payments. Correct request terms, then record the
   verified receipt using its bank posted date. Recording already received money
   must not initiate another debit or collection.
4. Journal before each mutation. On interruption, timeout, validation errors or
   ambiguous results, stop and read the exact native record. Do not replay batches
   or use another journal to evade unresolved outcomes.
5. Independently read affected requests/payments and linked mirrors. Verify IDs,
   amounts, dates and preserved terms. Apply authorized accounting rules to
   management-fee/bookkeeping mirrors; exclude them from customer charge totals.
6. If a period is restored to its regular charge, remove that period's difference
   from the historical adjustment so it appears once.

Incident scripts contain historical IDs/totals and are not reusable apply engines.
Generic replay does not replace scoped financial preflight and native verification.

## Interpreting balances

Separate regular charges, adjustments and due dates from successful receipts,
failed payments, credits, scheduled instructions and native `amountRemaining`.
A sum of charges is not necessarily current ledger balance. Zero `successAmount`
and an empty `payments` list do not prove a charge is fully outstanding: scheduled
instructions may affect remaining amounts. Preserve instructions and explain any
discrepancy. Updating an instance does not prove a recurring template or payment
instruction changed.

## Verified messages

Reusable sequence: scope → exact preview → private journal → one submission →
independent native readback. Verify destination, author, content and visibility;
HTTP success alone is not delivery. Authorization does not expand to other audiences.

For Hemlane tenant-visible replies, use `send_hemlane_tenant_reply.py` / MCP
`send_tenant_reply`. Preview requires `--tenant-group-id`, `--expected-user-id`,
`--property-id` and `--body` (`--message` alias); no credentials are needed. Authorized
apply adds runtime `--auth-file`, `--apply`, exact `--confirm-digest` and a new
`--journal`. It checks native scope and duplicates, journals before POST and reads
back the thread. `sent_verified` requires a unique new message, matching returned ID
when known, exact body, expected author and explicit false `isOwnerPrivate`,
`isAdminOnly` and `isSystem`. Ten pages of 100 is the pagination cap; incomplete
coverage blocks sending. Exclude owner-only content from tenant-visible messages.

Recover uncertain outcomes using the original journal, without another POST:

```sh
python3 scripts/send_hemlane_tenant_reply.py --verify-only \
  --auth-file /private/runtime-headers.json --journal /private/send-receipt.json
```

MCP equivalent: `verify_tenant_reply`. Unresolved verification stays unresolved.
Attachments require independent content verification. Owner-private delivery is a
different contract. Journal/thread checks do not provide distributed server-side
idempotency across concurrent callers.

## Ledger attachment email (optional channel)

Use the available email connector or maintained email workflow; no particular
provider or sibling skill is required. Verify the actual sending mailbox and current
recipient from current account data/correspondence. Include authorized recipients
only. Preserve provided attachment bytes, size and hash.

Separate current charges, waived/uncollectible amounts, receipts and settlement
cutoffs. Attribute terms to the operator if the agreement was not reviewed; ask
counsel to assess legal steps rather than asserting an outcome.

After sending, use the API-returned immutable message ID to read back sender,
recipients, subject, body, sent state and attachment content/hash. Providers may
rewrite RFC `Message-ID`; that alone is not failure and must not trigger resending.
