#!/usr/bin/env python3
"""Offline bank-backed payment allocation and responsibility planner. Never writes Hemlane."""
from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from hemlane_safety import SafetyError, digest


def cents(value):
    if isinstance(value, bool):
        raise SafetyError("invalid_money")
    try:
        amount = Decimal(str(value)) * 100
    except InvalidOperation:
        raise SafetyError("invalid_money") from None
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise SafetyError("money_requires_exact_cents")
    return int(amount)


def nonnegative(value):
    value = cents(value)
    if value < 0:
        raise SafetyError("negative_source_amount")
    return value


def reconcile(data):
    scope = data.get("scope") or {}
    if not all(scope.get(k) for k in ("userId", "propertyId", "recordId",)):
        raise SafetyError("account_property_record_scope_required")
    if data.get("responsibilityConfirmed") is not True:
        raise SafetyError("remaining_responsibility_must_be_confirmed")
    periods = {}
    for period in data["periods"]:
        month = period["month"]
        if not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month) or month in periods:
            raise SafetyError("invalid_or_duplicate_month")
        if period.get("treatment") not in ("true_up", "correct_regular", "exclude"):
            raise SafetyError("month_requires_single_treatment")
        periods[month] = period
    external = {month: 0 for month in periods}
    deposit_ids = set()
    for deposit in data["deposits"]:
        if not deposit.get("id") or deposit["id"] in deposit_ids:
            raise SafetyError("duplicate_or_missing_bank_deposit_id")
        deposit_ids.add(deposit["id"])
        if (deposit.get("verified") is not True or not deposit.get("evidenceRef")
                or not deposit.get("postedDate")):
            raise SafetyError("bank_deposit_requires_verified_evidence_and_posted_date")
        allocations = deposit["allocations"]
        seen = set()
        total = 0
        for allocation in allocations:
            month = allocation["month"]
            if month not in periods or month in seen:
                raise SafetyError("unknown_or_duplicate_deposit_allocation_month")
            seen.add(month)
            amount = nonnegative(allocation["amount"])
            external[month] += amount
            total += amount
        if total != nonnegative(deposit["amount"]):
            raise SafetyError("bank_deposit_allocation_does_not_balance")
    rows = []
    true_up = 0
    for month, p in sorted(periods.items()):
        if p["treatment"] == "exclude":
            rows.append({"month": month, "treatment": "exclude", "reason": "unverified_or_out_of_scope"})
            continue
        if p.get("verified") is not True or external[month] <= 0:
            raise SafetyError("included_month_requires_verified_charge_and_bank_receipts")
        charge = nonnegative(p["charge"]) - external[month]
        if charge < 0:
            raise SafetyError("external_exceeds_charge_review_credit_separately")
        shortage = charge - nonnegative(p["responsiblePaid"])
        existing_charge = nonnegative(p["existingResponsibleCharge"])
        unbilled_delta = charge - existing_charge
        # A month is either included in the historical adjustment or corrected
        # on its regular request. Never both. Credits stay signed rather than vanishing.
        if p["treatment"] == "true_up":
            true_up += unbilled_delta
        rows.append({"month": month, "treatment": p["treatment"],
                     "externalPaidCents": external[month], "responsibleChargeCents": charge,
                     "responsiblePaidCents": nonnegative(p["responsiblePaid"]),
                     "existingResponsibleChargeCents": existing_charge,
                     "shortageOrCreditCents": shortage,
                     "trueUpContributionCents": unbilled_delta if p["treatment"] == "true_up" else 0})
    plan = {"version": 1, "scope": scope, "rows": rows, "trueUpCents": true_up,
            "status": "offline_plan_only", "sourceDigest": digest(data),
            "balanceCaveat": "Charges are not current outstanding balance. Read scheduled payments, credits, and amountRemaining separately."}
    return {**plan, "digest": digest(plan)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="Local verified evidence JSON; schema in reconciliation runbook")
    args = ap.parse_args()
    try:
        print(json.dumps(reconcile(json.loads(Path(args.input).read_text())), indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc) if isinstance(exc, SafetyError) else "invalid_reconciliation_input"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
