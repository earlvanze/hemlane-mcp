#!/usr/bin/env python3
import argparse, json, os, re, sys
from pathlib import Path
from urllib import request, error
from hemlane_safety import SafetyError, digest, graphql, load_headers, private_json, validate_endpoint

DEFAULT_ENDPOINT = os.environ.get('HEMLANE_GRAPHQL_ENDPOINT', 'https://api.hemlane.com/graphql')


def load_text(value: str) -> str:
    p = Path(value)
    if p.exists():
        return p.read_text()
    return value


def load_json(value: str):
    if value == '-':
        return json.load(sys.stdin)
    p = Path(value)
    text = p.read_text() if p.exists() else value
    return json.loads(text)


def build_headers(args):
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': os.environ.get('HEMLANE_USER_AGENT', 'OpenClaw-Hemlane-Replay/1.0'),
    }
    if args.auth_file:
        return load_headers(args.auth_file)
    cookie = args.cookie or os.environ.get('HEMLANE_COOKIE')
    csrf = args.csrf or os.environ.get('HEMLANE_CSRF_TOKEN')
    auth = args.authorization or os.environ.get('HEMLANE_AUTHORIZATION')
    apollo_name = os.environ.get('HEMLANE_APOLLO_CLIENT_NAME')
    apollo_version = os.environ.get('HEMLANE_APOLLO_CLIENT_VERSION')
    referer = os.environ.get('HEMLANE_REFERER')
    origin = os.environ.get('HEMLANE_ORIGIN', 'https://www.hemlane.com')

    if cookie:
        headers['Cookie'] = cookie
    if csrf:
        headers['x-csrf-token'] = csrf
    if auth:
        headers['Authorization'] = auth
    if apollo_name:
        headers['apollographql-client-name'] = apollo_name
    if apollo_version:
        headers['apollographql-client-version'] = apollo_version
    if referer:
        headers['Referer'] = referer
    if origin:
        headers['Origin'] = origin
    return headers


def redacted_headers(headers):
    out = {}
    for k, v in headers.items():
        if k.lower() in {'cookie', 'authorization', 'x-csrf-token'}:
            out[k] = '<redacted>'
        else:
            out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser(description='Replay a Hemlane GraphQL request using env-based auth.')
    ap.add_argument('--query', required=True, help='GraphQL query string or path to file')
    ap.add_argument('--variables', default='{}', help='JSON string or path to variables file')
    ap.add_argument('--operation-name', help='Optional GraphQL operationName')
    ap.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    ap.add_argument('--auth-file', help='Runtime-only local headers; never printed')
    ap.add_argument('--cookie', help='Override HEMLANE_COOKIE')
    ap.add_argument('--csrf', help='Override HEMLANE_CSRF_TOKEN')
    ap.add_argument('--authorization', help='Override HEMLANE_AUTHORIZATION')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--pretty', action='store_true')
    ap.add_argument('--apply', action='store_true', help='Explicit mutation submission; no automatic retry')
    ap.add_argument('--confirm-digest')
    ap.add_argument('--journal', help='New private receipt path; required for mutation apply')
    args = ap.parse_args()

    payload = {
        'query': load_text(args.query),
        'variables': load_json(args.variables),
    }
    if args.operation_name:
        payload['operationName'] = args.operation_name

    validate_endpoint(args.endpoint)
    # Conservative: any mutation in a document requires the mutation gate, even
    # if a different operationName was selected. Unknown operation types stop.
    # Inspect raw text: stripping comments without lexing strings can hide a
    # real mutation following a '#' inside a quoted value. False-positive gates
    # on comments/string values are intentionally safe.
    is_mutation = bool(re.search(r'\bmutation\b', payload['query']))
    document = re.sub(r'#[^\n]*', '', payload['query'])
    if not is_mutation and not re.match(r'\s*(?:query\b|\{)', document):
        raise SafetyError('unsupported_graphql_document')
    plan = {'endpoint': args.endpoint, 'payload': payload}
    plan_digest = digest(plan)

    if args.dry_run or (is_mutation and not args.apply):
        print(json.dumps({
            'status': 'preview', 'digest': plan_digest,
            'endpoint': args.endpoint,
            'payload': payload,
        }, indent=2))
        return

    if is_mutation:
        if not args.journal or args.confirm_digest != plan_digest:
            raise SafetyError('mutation_requires_new_journal_and_exact_preview_digest')
    # Local credential errors cannot leave a journal suggesting a request was sent.
    headers = build_headers(args)
    if is_mutation:
        # Receipt survives timeout/interruption; reusing its path refuses replay.
        private_json(args.journal, {'status': 'attempting_do_not_replay',
                                   'digest': plan_digest, 'plan': plan}, exclusive=True)
    try:
        data = graphql(headers, payload, args.endpoint)
        if is_mutation:
            private_json(args.journal, {'status': 'submitted_readback_required',
                'digest': plan_digest, 'plan': plan, 'response': data})
            print(json.dumps({'status': 'submitted_readback_required', 'digest': plan_digest}))
        else:
            print(json.dumps(data, indent=2 if args.pretty else None))
    except Exception:
        if is_mutation:
            private_json(args.journal, {'status': 'outcome_unverified_do_not_replay',
                                       'digest': plan_digest, 'plan': plan})
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        code = str(exc) if isinstance(exc, SafetyError) else 'local_input_or_receipt_error'
        print(json.dumps({'error': code}), file=sys.stderr)
        sys.exit(2)
