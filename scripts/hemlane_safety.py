"""Credential-safe Hemlane transport and durable local operation receipts. No retries."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib import error, request
from urllib.parse import urlsplit

ENDPOINT = "https://api.hemlane.com/graphql"
KEEP_HEADERS = {"authorization", "cookie", "x-csrf-token", "content-type", "accept",
                "origin", "referer", "user-agent", "apollographql-client-name",
                "apollographql-client-version"}


class SafetyError(Exception):
    """Only fixed, non-sensitive diagnostic codes belong in this exception."""


def validate_endpoint(endpoint):
    u = urlsplit(endpoint)
    if (u.scheme != "https" or u.netloc != "api.hemlane.com"
            or u.path not in ("/graphql", "/graphql/") or u.query or u.fragment):
        raise SafetyError("endpoint_must_be_hemlane_graphql")
    return endpoint


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def load_headers(path):
    data = json.loads(Path(path).read_text())
    data = data.get("headers", data)
    headers = {str(k).lower(): str(v) for k, v in data.items()
               if k.lower() in KEEP_HEADERS and v is not None}
    headers.update({"content-type": "application/json", "accept": "application/json"})
    return headers


def private_json(path, data, *, exclusive=False):
    """Durable receipt; never follows a symlink or overwrites on creation."""
    encoded = json.dumps(data, indent=2, ensure_ascii=False).encode()
    path = Path(path)
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
    else:
        if path.is_symlink():
            raise SafetyError("receipt_symlink_refused")
        fd, temporary = tempfile.mkstemp(prefix=".hemlane-receipt-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(encoded)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SafetyError("redirect_refused")


def has_field_errors(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "errors" and child:
                if not isinstance(child, dict) or any(v for k, v in child.items() if k != "__typename"):
                    return True
            elif has_field_errors(child):
                return True
    elif isinstance(value, list):
        return any(has_field_errors(child) for child in value)
    return False


def graphql(headers, payload, endpoint=ENDPOINT):
    validate_endpoint(endpoint)
    req = request.Request(endpoint, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with request.build_opener(NoRedirect()).open(req, timeout=45) as response:
            result = json.load(response)
    except error.HTTPError as exc:
        raise SafetyError(f"http_{exc.code}_outcome_unverified") from None
    except SafetyError:
        raise
    except Exception:
        raise SafetyError("transport_or_response_error_outcome_unverified") from None
    if not isinstance(result, dict) or not isinstance(result.get("data"), dict) or has_field_errors(result):
        raise SafetyError("graphql_error_outcome_unverified")
    return result
