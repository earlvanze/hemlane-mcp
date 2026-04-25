#!/usr/bin/env python3
"""Hemlane MCP server - wraps existing Hemlane scripts."""
import json
import subprocess
import sys
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hemlane")

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"

def run_script(script_name: str, args: list = None) -> dict:
    """Run a Hemlane script and return the result."""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {"error": f"Script not found: {script_name}"}
    
    cmd = ["python3", str(script_path)] + (args or [])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return {"error": result.stderr, "stdout": result.stdout}
        return {"success": True, "output": result.stdout}
    except subprocess.TimeoutExpired:
        return {"error": "Script timed out"}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def capture_auth(endpoint_kind: str = "get-properties", out_file: str = None) -> dict:
    """Capture Hemlane auth headers from browser CDP session.
    
    Args:
        endpoint_kind: One of get-properties, get-tenants, get-transactions, 
                       get-maintenance, send-tenant-reply, submit-referral,
                       work-order-comment, maintenance-comment
        out_file: Optional file path to save captured headers
    
    Returns:
        dict with targetId, capturedUrl, capturedMethod, headers
    """
    args = ["--endpoint-kind", endpoint_kind]
    if out_file:
        args.extend(["--out-file", out_file])
    return run_script("capture_hemlane_auth_via_cdp.py", args)

@mcp.tool()
def send_tenant_reply(tenant_group_id: str, message: str, auth_file: str) -> dict:
    """Send a tenant reply via Hemlane GraphQL API.
    
    Args:
        tenant_group_id: The tenant group ID to message
        message: The message content
        auth_file: Path to captured auth headers JSON file
    
    Returns:
        dict with success/error status
    """
    return run_script("send_hemlane_tenant_reply.py", [
        "--tenant-group-id", tenant_group_id,
        "--message", message,
        "--auth-file", auth_file
    ])

@mcp.tool()
def submit_referral(first_name: str, last_name: str, email: str, phone: str, 
                     referrer_name: str, referrer_email: str, auth_file: str) -> dict:
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
    return run_script("submit_hemlane_referral.py", [
        "--first-name", first_name,
        "--last-name", last_name,
        "--email", email,
        "--phone", phone,
        "--referrer-name", referrer_name,
        "--referrer-email", referrer_email,
        "--auth-file", auth_file
    ])

@mcp.tool()
def post_workorder_comment(work_order_id: str, comment: str, auth_file: str,
                           hidden_from_tenants: bool = False, 
                           hidden_from_owners: bool = False) -> dict:
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
    args = [
        "--work-order-id", work_order_id,
        "--comment", comment,
        "--auth-file", auth_file
    ]
    if hidden_from_tenants:
        args.append("--hidden-from-tenants")
    if hidden_from_owners:
        args.append("--hidden-from-owners")
    return run_script("post_hemlane_workorder_comment.py", args)

@mcp.tool()
def post_maintenance_comment(request_id: str, comment: str, auth_file: str,
                             hidden_from_tenants: bool = False,
                             hidden_from_owners: bool = False) -> dict:
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
    args = [
        "--request-id", request_id,
        "--comment", comment,
        "--auth-file", auth_file
    ]
    if hidden_from_tenants:
        args.append("--hidden-from-tenants")
    if hidden_from_owners:
        args.append("--hidden-from-owners")
    return run_script("post_hemlane_maintenance_request_comment.py", args)

@mcp.tool()
def extract_rent_roll(property_id: str, auth_file: str) -> dict:
    """Extract rent roll data for a property.
    
    Args:
        property_id: The Hemlane property ID
        auth_file: Path to captured auth headers JSON file
    
    Returns:
        dict with rent roll data
    """
    return run_script("extract_rent_roll.py", [
        "--property-id", property_id,
        "--auth-file", auth_file
    ])

@mcp.tool()
def list_graphql_operations() -> list:
    """List available Hemlane GraphQL operations from HAR captures.
    
    Returns:
        list of operation names
    """
    catalog_path = SCRIPTS_DIR.parent / "references" / "operation-catalog.json"
    if not catalog_path.exists():
        return {"error": "Operation catalog not found"}
    try:
        catalog = json.loads(catalog_path.read_text())
        return [op.get("name") for op in catalog.get("operations", [])]
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    mcp.run()
