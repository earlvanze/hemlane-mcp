#!/usr/bin/env python3
"""Preview, send once, and independently verify a scoped tenant-visible reply."""
import argparse
import json
from pathlib import Path
from hemlane_safety import ENDPOINT, SafetyError, digest, graphql, load_headers, private_json
from query_tenant_messages_readonly import MESSAGES_QUERY

QUERY = (Path(__file__).resolve().parent.parent / "references/tenant-reply.graphql").read_text()


def plan_message(tenant_group_id, body, expected_user_id, property_id,
                 notify_immediately=True, attachment_url=None):
    if not all(isinstance(v, str) and v.strip() for v in
               (tenant_group_id, body, expected_user_id, property_id)):
        raise SafetyError("nonempty_message_and_account_property_scope_required")
    return {"version": 1, "endpoint": ENDPOINT,
            "scope": {"userId": expected_user_id, "propertyId": property_id,
                      "tenantGroupId": tenant_group_id},
            "payload": {"operationName": "ODProspectiveTenantGroupMessageCreate", "query": QUERY,
                "variables": {"input": {"tenantGroupId": tenant_group_id, "body": body,
                "notifyImmediately": notify_immediately, "isOwnerPrivate": False,
                "attachmentUrl": attachment_url}}}}


def scoped_messages(headers, plan, call):
    scope = plan["scope"]
    data = call(headers, {"operationName": "HemlaneMessagePreflight", "query":
        "query HemlaneMessagePreflight($tenantGroupId: ID!) { currentUser { id } "
        "tenantGroup(tenantGroupId: $tenantGroupId) { property { id } } }",
        "variables": {"tenantGroupId": scope["tenantGroupId"]}})["data"]
    user_id = (data.get("currentUser") or {}).get("id")
    property_id = ((data.get("tenantGroup") or {}).get("property") or {}).get("id")
    if user_id != scope["userId"] or property_id != scope["propertyId"]:
        raise SafetyError("account_or_property_scope_mismatch")
    messages, after, cursors = [], None, set()
    for _ in range(10):
        data = call(headers, {"operationName": "OwnerTenancyMessages", "query": MESSAGES_QUERY,
            "variables": {"tenantGroupId": scope["tenantGroupId"], "first": 100, "after": after}})["data"]
        property_id = ((data.get("tenantGroup") or {}).get("property") or {}).get("id")
        if property_id != scope["propertyId"]:
            raise SafetyError("readback_property_scope_mismatch")
        root = data.get("tenancyMessages")
        if not isinstance(root, dict) or not isinstance(root.get("edges"), list):
            raise SafetyError("messages_response_incomplete")
        messages.extend(e["node"] for e in root["edges"])
        info = root.get("pageInfo") or {}
        if info.get("hasNextPage") is False:
            return messages
        after = info.get("endCursor")
        if not after or after in cursors:
            raise SafetyError("message_pagination_incomplete")
        cursors.add(after)
    raise SafetyError("message_history_truncated_review_required")


def verify_receipt(headers, receipt, journal, call=graphql):
    # Safe recovery after interruption; never sends another mutation.
    plan = receipt["plan"]
    messages = scoped_messages(headers, plan, call)
    body = plan["payload"]["variables"]["input"]["body"]
    matches = [m for m in messages if m.get("body") == body
               and m.get("id") not in receipt["baselineIds"]
               and (not receipt.get("messageId") or m.get("id") == receipt["messageId"])
               and (m.get("createdByInfo") or {}).get("id") == plan["scope"]["userId"]
               and all(m.get(flag) is False for flag in ("isOwnerPrivate", "isAdminOnly", "isSystem"))]
    if len(matches) == 1:
        status = ("attachment_verification_required"
                  if plan["payload"]["variables"]["input"].get("attachmentUrl")
                  else "sent_verified")
        receipt.update(status=status, messageId=matches[0]["id"])
    else:
        receipt["status"] = "outcome_unverified_do_not_resend"
    private_json(journal, receipt)
    return {k: receipt[k] for k in ("status", "digest", "messageId") if k in receipt}


def send_once(headers, plan, confirmed_digest, journal, call=graphql):
    if confirmed_digest != digest(plan):
        raise SafetyError("plan_digest_mismatch")
    if Path(journal).exists():
        raise SafetyError("journal_exists_use_verify_only")
    before = scoped_messages(headers, plan, call)
    body = plan["payload"]["variables"]["input"]["body"]
    if any(m.get("body") == body for m in before):
        raise SafetyError("matching_message_already_exists_review_thread")
    receipt = {"status": "attempting_do_not_resend", "digest": digest(plan), "plan": plan,
               "baselineIds": [m["id"] for m in before]}
    private_json(journal, receipt, exclusive=True)
    try:
        data = call(headers, plan["payload"])["data"]
        message = ((data.get("tenantGroupMessageAdd") or {}).get("tenantGroupMessage") or {})
        if not message.get("id") or message.get("body") != body:
            raise SafetyError("mutation_response_unverified")
        receipt.update(status="submitted_unverified", messageId=message["id"])
        private_json(journal, receipt)
        return verify_receipt(headers, receipt, journal, call)
    except Exception:
        receipt["status"] = "outcome_unverified_do_not_resend"
        private_json(journal, receipt)
        raise SafetyError("outcome_unverified_use_verify_only_never_resend") from None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant-group-id")
    ap.add_argument("--body", "--message", dest="body")
    ap.add_argument("--expected-user-id")
    ap.add_argument("--property-id")
    ap.add_argument("--auth-file")
    ap.add_argument("--notify-immediately", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--attachment-url")
    ap.add_argument("--dry-run", action="store_true", help="Preview is the default")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-digest")
    ap.add_argument("--journal")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    try:
        if args.verify_only:
            if args.apply or not args.journal or not args.auth_file:
                raise SafetyError("verify_requires_auth_and_journal_without_apply")
            receipt = json.loads(Path(args.journal).read_text())
            if receipt["digest"] != digest(receipt["plan"]):
                raise SafetyError("receipt_digest_mismatch")
            result = verify_receipt(load_headers(args.auth_file), receipt, args.journal)
        else:
            plan = plan_message(args.tenant_group_id, args.body, args.expected_user_id,
                                args.property_id, args.notify_immediately, args.attachment_url)
            if args.apply:
                if args.dry_run or not args.auth_file or not args.journal or not args.confirm_digest:
                    raise SafetyError("apply_requires_auth_journal_digest_without_dry_run")
                result = send_once(load_headers(args.auth_file), plan, args.confirm_digest, args.journal)
            else:
                result = {"status": "preview", "digest": digest(plan), "plan": plan}
        print(json.dumps(result, indent=2 if args.pretty else None))
        return 0 if result["status"] in ("preview", "sent_verified") else 2
    except Exception as exc:
        code = str(exc) if isinstance(exc, SafetyError) else "local_input_or_receipt_error"
        print(json.dumps({"status": "blocked_or_unverified", "error": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
