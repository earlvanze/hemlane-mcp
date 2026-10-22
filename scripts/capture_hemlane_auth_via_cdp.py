#!/usr/bin/env python3
"""Capture Hemlane credentials into a private file, never standard output.

Attach to the existing canonical Chrome bridge. No browser launch, arbitrary
tab navigation, page credential hooks, or unrelated-domain cookie capture.
"""
import argparse
import json
import os
import stat
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

CDP_BASE = os.environ.get('HEMLANE_CDP_URL', os.environ.get('BRAVE_CDP_URL', '')).rstrip('/')
API_URL = 'https://api.hemlane.com/graphql/'
UI_HOSTS = {'hemlane.com', 'www.hemlane.com', 'app.hemlane.com'}
SECRET_HEADERS = {'authorization', 'cookie', 'x-csrf-token'}
KEEP_HEADERS = SECRET_HEADERS | {'content-type', 'origin', 'referer', 'user-agent'}
ENDPOINT_HINTS = {
    'get-properties': 'properties', 'get-tenants': 'tenants',
    'get-transactions': 'transactions', 'get-maintenance': 'maintenance',
    'send-tenant-reply': 'tenantGroupMessageAdd',
    'submit-referral': 'hubspotFormSubmission',
    'work-order-comment': 'workOrderCommentCreate',
    'maintenance-comment': 'maintenanceRequestCommentCreate',
    'financials-recurring': 'recurringPaymentRequests',
    'financials-transactions': 'financialTransactions',
}


def is_hemlane_tab(url):
    try:
        parsed = urlparse(url)
        return (parsed.scheme == 'https' and parsed.hostname in UI_HOSTS
                and parsed.port in (None, 443) and not parsed.username
                and not parsed.password)
    except (ValueError, TypeError):
        return False


def is_api_graphql(url):
    try:
        parsed = urlparse(url)
        return (parsed.scheme == 'https' and parsed.hostname == 'api.hemlane.com'
                and parsed.port in (None, 443) and not parsed.username
                and not parsed.password and parsed.path in ('/graphql', '/graphql/')
                and not parsed.query and not parsed.fragment)
    except (ValueError, TypeError):
        return False


def through_cdp_bridge(wsurl):
    advertised = urlparse(wsurl)
    bridge = urlparse(CDP_BASE)
    if bridge.scheme not in ('http', 'https') or not bridge.hostname or bridge.username or bridge.password:
        raise ValueError('Invalid CDP bridge configuration')
    if not advertised.path.startswith('/devtools/page/'):
        raise ValueError('Invalid page debugger target')
    return urlunparse(('wss' if bridge.scheme == 'https' else 'ws',
                      bridge.netloc, advertised.path, '', '', ''))


def get_tabs():
    bridge = urlparse(CDP_BASE)
    if bridge.scheme not in ('http', 'https') or not bridge.hostname or bridge.username or bridge.password:
        raise ValueError('Configure HEMLANE_CDP_URL for the existing authenticated browser')
    with urlopen(f'{CDP_BASE}/json', timeout=20) as response:
        return json.loads(response.read())


def select_tab(tabs, target_id=None):
    candidates = [tab for tab in tabs if tab.get('type') == 'page'
                  and is_hemlane_tab(tab.get('url', ''))]
    if target_id:
        candidates = [tab for tab in candidates if tab.get('id') == target_id]
    if not candidates:
        raise ValueError('No existing Hemlane page target; no other tab was changed')
    return candidates[0]


def ensure_hemlane_cdp_context(close_extras=False):
    # Retained for callers; this function intentionally never navigates tabs.
    return {'targetId': select_tab(get_tabs())['id']}


def normalize_headers(headers):
    return {str(key).lower(): value for key, value in headers.items()
            if str(key).lower() in KEEP_HEADERS and isinstance(value, str)}


def select_captured_auth(events):
    """Join ExtraInfo only to an explicitly observed API GraphQL request ID."""
    requests = {}
    extras = {}
    redirected = set()
    for event in events:
        params = event.get('params', {})
        request_id = params.get('requestId')
        if not request_id:
            continue
        if event.get('method') == 'Network.requestWillBeSent':
            request = params.get('request', {})
            if request_id in requests or params.get('redirectResponse'):
                redirected.add(request_id)
            requests[request_id] = request
        elif event.get('method') == 'Network.requestWillBeSentExtraInfo':
            extras[request_id] = params.get('headers', {})
    for request_id, request in reversed(list(requests.items())):
        if (request_id in redirected or not is_api_graphql(request.get('url', ''))
                or request.get('method') != 'POST'):
            continue
        headers = normalize_headers(request.get('headers', {}))
        headers.update(normalize_headers(extras.get(request_id, {})))
        if any(headers.get(key) for key in SECRET_HEADERS):
            return headers, {'url': request['url'], 'method': request['method']}
    return None, None


def scoped_cookie_header(cookies):
    # Network.getCookies is additionally restricted to API_URL by the caller.
    allowed_domains = {'hemlane.com', '.hemlane.com', 'api.hemlane.com', '.api.hemlane.com'}
    return '; '.join(f"{cookie['name']}={cookie['value']}" for cookie in cookies
                     if cookie.get('domain') in allowed_domains
                     and cookie.get('name') and isinstance(cookie.get('value'), str))


def write_auth_exclusive(path, headers):
    """Refuse existing files/symlinks; restrictive permissions apply at creation."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(os.fspath(path), flags, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, 'w') as output:
        json.dump(headers, output, indent=2)
        output.write('\n')


def capture(args):
    import websocket
    # Fail before browser work if the destination already exists, including a
    # dangling symlink. O_EXCL below closes the race with concurrent captures.
    if os.path.lexists(args.out_file):
        raise ValueError('Auth output already exists; choose a new private file')
    tab = select_tab(get_tabs(), args.target_id)
    ws = websocket.WebSocket()
    events = []
    sequence = 0

    def command(method, params=None):
        nonlocal sequence
        sequence += 1
        ws.send(json.dumps({'id': sequence, 'method': method, 'params': params or {}}))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            obj = json.loads(ws.recv())
            if obj.get('method'):
                events.append(obj)
            if obj.get('id') == sequence:
                if obj.get('error'):
                    raise ValueError('Browser capture command failed')
                return obj.get('result', {})
        raise TimeoutError('Browser capture command timed out')

    try:
        ws.connect(through_cdp_bridge(tab['webSocketDebuggerUrl']), timeout=20,
                   origin=None, suppress_origin=True)
        command('Network.enable')
        command('Page.reload', {'ignoreCache': False})
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            ws.settimeout(min(1, max(0.01, deadline - time.monotonic())))
            try:
                obj = json.loads(ws.recv())
                if obj.get('method'):
                    events.append(obj)
            except websocket.WebSocketTimeoutException:
                pass
        ws.settimeout(20)
        headers, source = select_captured_auth(events)
        if not headers:
            cookies = command('Network.getCookies', {'urls': [API_URL]}).get('cookies', [])
            cookie = scoped_cookie_header(cookies)
            if cookie:
                headers = {'cookie': cookie}
                source = {'url': API_URL, 'method': 'POST'}
        if not headers:
            raise ValueError('No API-scoped Hemlane credentials captured')
        headers.setdefault('content-type', 'application/json')
        headers.setdefault('origin', 'https://www.hemlane.com')
        headers.setdefault('referer', 'https://www.hemlane.com/')
        write_auth_exclusive(args.out_file, headers)
        return {'success': True, 'targetId': tab['id'], 'endpointKind': args.endpoint_kind,
                'capturedUrl': source['url'], 'capturedMethod': source['method'],
                'authFile': str(Path(args.out_file)),
                'capturedHeaderNames': sorted(headers)}
    finally:
        ws.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-id')
    parser.add_argument('--endpoint-kind', choices=sorted(ENDPOINT_HINTS), default='get-properties')
    parser.add_argument('--out-file', required=True)
    # Compatibility: never close unrelated tabs, even if older callers send it.
    parser.add_argument('--close-extra-tabs', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        print(json.dumps(capture(args), indent=2))
    except Exception as exc:
        # Browser/HTTP exceptions can contain request headers, URLs, or bodies.
        print(json.dumps({'error': 'auth_capture_failed', 'errorType': type(exc).__name__,
                          'message': 'No credentials printed. Check target, private output path, and canonical browser bridge.'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
