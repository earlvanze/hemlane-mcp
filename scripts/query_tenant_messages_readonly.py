#!/usr/bin/env python3
"""Read native Hemlane tenant threads using runtime credentials. Keep results private."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request
from hemlane_safety import graphql

ENDPOINT = "https://api.hemlane.com/graphql/"
KEEP_HEADERS = {
    "authorization", "x-csrf-token", "content-type", "origin", "referer",
    "user-agent", "cookie", "accept", "apollographql-client-name",
    "apollographql-client-version",
}
SENSITIVE = {"cookie", "authorization", "x-csrf-token", "x-csrf"}

GROUPS_QUERY = """
query ODTenantsAndLeasesTenantGroups($propertyId: ID, $tenantGroupStatus: [TenantGroupStatus!], $pagination: PagedPaginationInput, $sortBy: String) {
  tenantsAndLeasesTenantGroups(propertyId: $propertyId, tenantGroupStatus: $tenantGroupStatus, pagination: $pagination, sortBy: $sortBy) {
    pageInfo { page totalCount totalPages }
    data { id status evictionStatus terminationDate lastMessageCreated unreadMessagesCount }
  }
}
"""

MESSAGES_QUERY = """
query OwnerTenancyMessages($tenantGroupId: ID!, $first: Int, $after: String) {
  tenantGroup(tenantGroupId: $tenantGroupId) { property { id } }
  tenancyMessages(tenantGroupId: $tenantGroupId, first: $first, after: $after) {
    edges {
      cursor
      node {
        id body createdAt
        createdByInfo { id type }
        isSystem isOwnerPrivate isAdminOnly isPinned
        sourceable {
          ... on TenantGroupMessage {
            serviceType
            messageAttachments(first: 10) { edges { node { id } } }
          }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

PROPERTIES_QUERY = """
query ODPropertiesIndexInfo($page: Int, $limit: Int) {
  currentUser {
    myProperties(isDeleted: false, pagination: {page: $page, limit: $limit}, status: Accepted) {
      data { id nickname addressStreet __typename }
    }
  }
}
"""


def load_headers(path: str) -> dict[str, str]:
    data = json.loads(Path(path).read_text())
    if isinstance(data.get("headers"), dict):
        data = data["headers"]
    headers = {str(k): str(v) for k, v in data.items() if v is not None and k.lower() in KEEP_HEADERS}
    headers.setdefault("content-type", "application/json")
    headers.setdefault("accept", "application/json")
    return headers


def gql(headers: dict[str, str], operation: str, query: str, variables: dict) -> dict:
    payload = {"operationName": operation, "query": query, "variables": variables}
    return graphql(headers, payload, ENDPOINT)["data"]


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def compact_message(node: dict) -> dict:
    source = node.get("sourceable") or {}
    attachments = ((source.get("messageAttachments") or {}).get("edges") or [])
    return {
        "id": node.get("id"),
        "body": node.get("body"),
        "createdAt": node.get("createdAt"),
        "authorType": (node.get("createdByInfo") or {}).get("type"),
        "isSystem": bool(node.get("isSystem")),
        "isOwnerPrivate": bool(node.get("isOwnerPrivate")),
        "isAdminOnly": bool(node.get("isAdminOnly")),
        "isPinned": bool(node.get("isPinned")),
        "serviceType": source.get("serviceType"),
        "attachmentCount": len(attachments),
    }


def list_properties(headers: dict[str, str], search: str | None = None) -> dict:
    data = gql(headers, "ODPropertiesIndexInfo", PROPERTIES_QUERY, {"page": 1, "limit": 500})
    properties = []
    root = (((data.get("currentUser") or {}).get("myProperties") or {}).get("data") or [])
    for item in root:
        if search and search.casefold() not in f"{item.get('nickname', '')} {item.get('addressStreet', '')}".casefold():
            continue
        properties.append({
            "id": item.get("id"),
            "nickname": item.get("nickname"),
            "addressStreet": item.get("addressStreet"),
        })
    return {"count": len(properties), "properties": properties}


def list_groups(headers: dict[str, str], property_id: str, status: list[str], limit: int, max_pages: int) -> dict:
    groups = []
    page = 1
    total_pages = 1
    while page <= min(total_pages, max_pages):
        variables = {"propertyId": property_id, "tenantGroupStatus": status or None,
                     "pagination": {"page": page, "limit": limit}, "sortBy": "lastMessageCreated"}
        root = gql(headers, "ODTenantsAndLeasesTenantGroups", GROUPS_QUERY, variables).get("tenantsAndLeasesTenantGroups") or {}
        for item in root.get("data") or []:
            groups.append({k: item.get(k) for k in (
                "id", "status", "evictionStatus", "terminationDate", "lastMessageCreated", "unreadMessagesCount"
            )})
        info = root.get("pageInfo") or {}
        total_pages = max(1, int(info.get("totalPages") or 1))
        page += 1
    return {"propertyId": property_id, "count": len(groups), "groups": groups,
            "truncated": total_pages > max_pages}


def list_messages(headers: dict[str, str], tenant_group_id: str, since: datetime | None,
                  first: int, max_pages: int) -> dict:
    messages = []
    after = None
    property_id = None
    truncated = False
    for _ in range(max_pages):
        data = gql(headers, "OwnerTenancyMessages", MESSAGES_QUERY,
                   {"tenantGroupId": tenant_group_id, "first": first, "after": after})
        property_id = (((data.get("tenantGroup") or {}).get("property") or {}).get("id")) or property_id
        root = data.get("tenancyMessages") or {}
        stop = False
        for edge in root.get("edges") or []:
            item = compact_message(edge.get("node") or {})
            created = parse_time(item.get("createdAt"))
            if since and created and created < since:
                stop = True
                continue
            messages.append(item)
        info = root.get("pageInfo") or {}
        if stop or not info.get("hasNextPage"):
            break
        after = info.get("endCursor")
        if not after:
            break
    else:
        truncated = True
    return {"tenantGroupId": tenant_group_id, "propertyId": property_id,
            "count": len(messages), "messages": messages, "truncated": truncated}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--auth-file", required=True)
    sub = ap.add_subparsers(dest="command", required=True)
    groups = sub.add_parser("groups")
    groups.add_argument("--property-id", required=True)
    groups.add_argument("--status", action="append")
    groups.add_argument("--limit", type=int, default=50)
    groups.add_argument("--max-pages", type=int, default=5)
    messages = sub.add_parser("messages")
    messages.add_argument("--tenant-group-id", required=True)
    messages.add_argument("--since")
    messages.add_argument("--first", type=int, default=50)
    messages.add_argument("--max-pages", type=int, default=5)
    properties = sub.add_parser("properties")
    properties.add_argument("--search")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    headers = load_headers(args.auth_file)
    if args.dry_run:
        print(json.dumps({"endpoint": ENDPOINT, "command": args.command,
                          "headers": {k: ("<redacted>" if k.lower() in SENSITIVE else v) for k, v in headers.items()}}, indent=2))
        return
    if args.command == "properties":
        result = list_properties(headers, args.search)
    elif args.command == "groups":
        result = list_groups(headers, args.property_id, args.status or ["Active"], max(1, min(args.limit, 100)), max(1, min(args.max_pages, 10)))
    else:
        result = list_messages(headers, args.tenant_group_id, parse_time(args.since),
                               max(1, min(args.first, 100)), max(1, min(args.max_pages, 10)))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
