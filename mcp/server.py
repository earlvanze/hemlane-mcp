#!/usr/bin/env python3
"""Hemlane MCP server - wraps existing Hemlane scripts."""
import json
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hemlane")

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def require_operator():
    """Trusted stdio host supplies identity/policy; never accept identity in tool args."""
    caller = os.environ.get("HEMLANE_CALLER_ID", "")
    allowed = {value.strip().lower() for value in
               os.environ.get("HEMLANE_ALLOWED_CALLER_SHA256", "").split(",") if value.strip()}
    if caller and hashlib.sha256(caller.encode()).hexdigest() in allowed:
        return None
    return {"error": "write_blocked_unverified_operator",
            "nextStep": "Configure trusted runtime caller identity and allowed hashes; preview remains available."}


def run_script(script_name: str, args: list = None) -> dict:
    """Run a Hemlane script and return the result."""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {"error": f"Script not found: {script_name}"}
    
    cmd = [sys.executable, str(script_path)] + (args or [])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            # Old scripts can put credentials/tenant data into exception text.
            return {"success": False, "error": "script_failed_or_outcome_unverified",
                    "exitCode": result.returncode,
                    "nextStep": "Inspect the private receipt; verify server state before any retry."}
        try:
            data = json.loads(result.stdout)
        except ValueError:
            return {"success": False, "error": "unstructured_script_output_withheld"}
        output = {"success": True, "result": data}
        if isinstance(data, dict) and data.get("status"):
            output["status"] = data["status"]
            output["verified"] = data["status"] == "sent_verified"
        return output
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout_outcome_unverified_do_not_retry"}
    except Exception:
        return {"success": False, "error": "local_script_execution_error"}


def mutation_options(apply, confirm_digest, journal):
    """Preview unless an exact reviewed plan and fresh receipt are supplied."""
    if not apply:
        return []
    if require_operator():
        raise ValueError("write_blocked_unverified_operator")
    if not confirm_digest or not journal:
        raise ValueError("apply_requires_digest_and_journal")
    return ["--apply", "--confirm-digest", confirm_digest, "--journal", journal]

@mcp.tool()
def capture_auth(endpoint_kind: str = "get-properties", out_file: str = None) -> dict:
    """Capture Hemlane auth headers from browser CDP session.
    
    Args:
        endpoint_kind: One of get-properties, get-tenants, get-transactions, 
                       get-maintenance, send-tenant-reply, submit-referral,
                       work-order-comment, maintenance-comment
        out_file: Required new private file path to save captured headers
    
    Returns:
        Redacted capture metadata; credentials stay in the required private file.
    """
    denied = require_operator()
    if denied:
        return denied
    if not out_file:
        return {"error": "new_private_out_file_required"}
    args = ["--endpoint-kind", endpoint_kind, "--out-file", out_file]
    return run_script("capture_hemlane_auth_via_cdp.py", args)

@mcp.tool()
def send_tenant_reply(tenant_group_id: str, message: str, auth_file: str,
                      expected_user_id: str = None, property_id: str = None,
                      apply: bool = False, confirm_digest: str = None,
                      journal: str = None, notify_immediately: bool = True) -> dict:
    """Preview a tenant-visible message. Apply only an authorized exact digest;
    account/property scope and new journal are mandatory. Never retry uncertain sends.
    """
    if not expected_user_id or not property_id:
        return {"error": "expected_user_id_and_property_id_required"}
    try:
        options = mutation_options(apply, confirm_digest, journal)
    except ValueError as exc:
        return {"error": str(exc)}
    return run_script("send_hemlane_tenant_reply.py", [
        "--tenant-group-id", tenant_group_id,
        "--body", message, "--expected-user-id", expected_user_id,
        "--property-id", property_id, "--auth-file", auth_file,
        "--notify-immediately" if notify_immediately else "--no-notify-immediately",
    ] + options)


@mcp.tool()
def verify_tenant_reply(auth_file: str, journal: str) -> dict:
    """Read-only recovery of an interrupted send. Never submits another message."""
    return run_script("send_hemlane_tenant_reply.py", ["--auth-file", auth_file,
                      "--journal", journal, "--verify-only"])


@mcp.tool()
def plan_payment_reconciliation(input_file: str) -> dict:
    """Offline verified-bank allocation and responsible-party adjustment plan. No live financial writes."""
    return run_script("reconcile_payment_allocations.py", ["--input", input_file])

@mcp.tool()
def submit_referral(first_name: str, last_name: str, email: str, phone: str, 
                     referrer_name: str, referrer_email: str, auth_file: str, form_id: str,
                     apply: bool = False, confirm_digest: str = None, journal: str = None) -> dict:
    """Submit a referral via Hemlane HubSpot form.
    
    Args:
        first_name: Referral first name
        last_name: Referral last name  
        email: Referral email
        phone: Referral phone
        referrer_name: Name of person making referral
        referrer_email: Email of person making referral
        auth_file: Path to captured auth headers JSON file
    
    Returns:
        dict with success/error status
    """
    try:
        options = mutation_options(apply, confirm_digest, journal)
    except ValueError as exc:
        return {"error": str(exc)}
    return run_script("submit_hemlane_referral.py", [
        "--first-name", first_name,
        "--last-name", last_name,
        "--email", email,
        "--phone", phone,
        "--referrer-name", referrer_name,
        "--referrer-email", referrer_email, "--form-id", form_id,
        "--auth-file", auth_file
    ] + options)

@mcp.tool()
def post_workorder_comment(work_order_id: str, comment: str, auth_file: str,
                           hidden_from_tenants: bool = False, 
                           hidden_from_owners: bool = False, apply: bool = False,
                           confirm_digest: str = None, journal: str = None) -> dict:
    """Post a comment on a work order.
    
    Args:
        work_order_id: The work order ID
        comment: The comment content
        auth_file: Path to captured auth headers JSON file
        hidden_from_tenants: Whether to hide from tenants
        hidden_from_owners: Whether to hide from owners
    
    Returns:
        dict with success/error status
    """
    if hidden_from_owners:
        return {"error": "owner_visibility_not_supported_by_verified_workorder_contract"}
    try:
        options = mutation_options(apply, confirm_digest, journal)
    except ValueError as exc:
        return {"error": str(exc)}
    args = [
        "--workorder-id", work_order_id,
        "--body", comment,
        "--auth-file", auth_file
    ]
    if hidden_from_tenants:
        args.append("--hide-from-tenants")
    return run_script("post_hemlane_workorder_comment.py", args + options)

@mcp.tool()
def post_maintenance_comment(request_id: str, comment: str, auth_file: str,
                             hidden_from_tenants: bool = False,
                             hidden_from_owners: bool = False, apply: bool = False,
                             confirm_digest: str = None, journal: str = None) -> dict:
    """Post a comment on a maintenance request.
    
    Args:
        request_id: The maintenance request ID
        comment: The comment content
        auth_file: Path to captured auth headers JSON file
        hidden_from_tenants: Whether to hide from tenants
        hidden_from_owners: Whether to hide from owners
    
    Returns:
        dict with success/error status
    """
    try:
        options = mutation_options(apply, confirm_digest, journal)
    except ValueError as exc:
        return {"error": str(exc)}
    args = [
        "--request-id", request_id,
        "--body", comment,
        "--auth-file", auth_file
    ]
    if hidden_from_tenants:
        args.append("--hide-from-tenants")
    if hidden_from_owners:
        args.append("--hide-from-owners")
    return run_script("post_hemlane_maintenance_request_comment.py", args + options)

@mcp.tool()
def extract_rent_roll(property_id: str, auth_file: str) -> dict:
    """Extract rent roll data for a property.
    
    Args:
        property_id: The Hemlane property ID
        auth_file: Path to captured auth headers JSON file
    
    Returns:
        dict with rent roll data
    """
    return {"error": "rent_roll_contract_unverified",
            "nextStep": "Use native paginated tenant/lease queries; the historical extractor is not a verified rent roll."}

@mcp.tool()
def query_recurring_payment_requests(auth_file: str, search: str = None, property_id: str = None,
                                     property_unit_id: str = None, status: str = "Active",
                                     all_pages: bool = True) -> dict:
    """Query Hemlane recurring rent/payment requests via HAR-derived GraphQL.

    Args:
        auth_file: Path to captured auth headers JSON file
        search: Optional text filter across property/unit/tenant/request fields
        property_id: Optional Hemlane property ID filter
        property_unit_id: Optional Hemlane property unit ID filter
        status: Recurring request status, defaults to Active
        all_pages: Fetch all pages when true

    Returns:
        dict with count and recurring request summaries
    """
    args = ["--auth-file", auth_file, "--limit", "50"]
    if search:
        args.extend(["--search", search])
    if property_id:
        args.extend(["--property-id", property_id])
    if property_unit_id:
        args.extend(["--property-unit-id", property_unit_id])
    if status is not None:
        args.extend(["--status", status])
    if all_pages:
        args.append("--all-pages")
    result = run_script("query_recurring_payment_requests.py", args)
    if result.get("success"):
        try:
            return result["result"]
        except Exception:
            return result
    return result

@mcp.tool()
def query_financials_operation(auth_file: str, operation_name: str, variables_json: str = "{}",
                               page: int = None, limit: int = None, all_pages: bool = False) -> dict:
    """Replay a read-oriented Hemlane Financials GraphQL operation from captured HAR samples.

    Useful operations from the financials HARs include RecurringNextCursorQuery,
    TransactionsNextCursorQuery, PagedFinancialTransactions,
    FinancialsScheduledActionPanelStats, BankTransactionsPageFiltersQuery, and
    GetPlaidSyncItems. Pass variables_json as a JSON object merged into the HAR
    sample variables.
    """
    args = ["--auth-file", auth_file, "--operation-name", operation_name, "--variables-json", variables_json]
    if page is not None:
        args.extend(["--page", str(page)])
    if limit is not None:
        args.extend(["--limit", str(limit)])
    if all_pages:
        args.append("--all-pages")
    result = run_script("query_financials_operation.py", args)
    if result.get("success"):
        try:
            return result["result"]
        except Exception:
            return result
    return result

def _json_output(result: dict) -> dict:
    if result.get("success"):
        try:
            return result["result"]
        except Exception:
            return result
    return result


@mcp.tool()
def query_catalog_operation(auth_file: str, operation_name: str, variables_json: str = "{}", dry_run: bool = False) -> dict:
    """Replay any read-only Hemlane GraphQL operation from the HAR-derived catalog.

    Args:
        auth_file: Path to captured auth headers JSON file. Can be omitted only when HEMLANE_* env auth is set.
        operation_name: Operation from references/operation-catalog.json, e.g. ODGetContextValues.
        variables_json: JSON object merged into the captured sample variables.
        dry_run: Return redacted request plan without sending it.
    """
    args = ["--operation-name", operation_name, "--variables-json", variables_json]
    if auth_file:
        args.extend(["--auth-file", auth_file])
    if dry_run:
        args.append("--dry-run")
    return _json_output(run_script("query_catalog_operation.py", args))


@mcp.tool()
def get_context_values(auth_file: str, variables_json: str = "{}") -> dict:
    """Get Hemlane owner dashboard context values/properties from ODGetContextValues."""
    return query_catalog_operation(auth_file, "ODGetContextValues", variables_json)


@mcp.tool()
def get_tenant_groups(auth_file: str, variables_json: str = "{}") -> dict:
    """Query tenant groups / leases using ODTenantsAndLeasesTenantGroups."""
    return query_catalog_operation(auth_file, "ODTenantsAndLeasesTenantGroups", variables_json)


@mcp.tool()
def get_maintenance_requests(auth_file: str, variables_json: str = "{}") -> dict:
    """Query maintenance request list using ODMaintenanceRequests."""
    return query_catalog_operation(auth_file, "ODMaintenanceRequests", variables_json)


@mcp.tool()
def get_transactions(auth_file: str, variables_json: str = "{}", page: int = None, limit: int = None, all_pages: bool = False) -> dict:
    """Query financial transactions using the HAR-derived TransactionsNextCursorQuery."""
    args = ["--auth-file", auth_file, "--operation-name", "TransactionsNextCursorQuery", "--variables-json", variables_json]
    if page is not None:
        args.extend(["--page", str(page)])
    if limit is not None:
        args.extend(["--limit", str(limit)])
    if all_pages:
        args.append("--all-pages")
    return _json_output(run_script("query_financials_operation.py", args))


@mcp.tool()
def list_graphql_operations(kind: str = None, read_only: bool = False) -> list | dict:
    """List available Hemlane GraphQL operations from HAR captures.

    Args:
        kind: Optional filter, usually query or mutation.
        read_only: When true, return only query operations.
    """
    catalog_path = SCRIPTS_DIR.parent / "references" / "operation-catalog.json"
    if not catalog_path.exists():
        return {"error": "Operation catalog not found"}
    try:
        catalog = json.loads(catalog_path.read_text())
        ops = catalog if isinstance(catalog, list) else catalog.get("operations", [])
        out = []
        for op in ops:
            name = op.get("operationName") or op.get("name")
            op_kind = op.get("kind")
            if kind and str(op_kind).lower() != str(kind).lower():
                continue
            if read_only and str(op_kind).lower() != "query":
                continue
            out.append({
                "operationName": name,
                "kind": op_kind,
                "files": op.get("files", []),
                "count": op.get("count"),
            })
        return out
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    mcp.run()
