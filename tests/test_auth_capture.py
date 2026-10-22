"""Offline auth-capture boundary tests; all credentials are synthetic fixtures."""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'capture_hemlane_auth_via_cdp.py'
spec = importlib.util.spec_from_file_location('capture_auth_under_test', SCRIPT)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def request(request_id, url=capture.API_URL, headers=None, **extra):
    return {'method': 'Network.requestWillBeSent', 'params': {
        'requestId': request_id,
        'request': {'url': url, 'method': 'POST', 'headers': headers or {}}, **extra}}


def extra(request_id, headers):
    return {'method': 'Network.requestWillBeSentExtraInfo',
            'params': {'requestId': request_id, 'headers': headers}}


class CaptureBoundaryTests(unittest.TestCase):
    def test_exact_origins_reject_suffix_userinfo_ports_and_paths(self):
        self.assertTrue(capture.is_api_graphql(capture.API_URL))
        for url in ('http://api.hemlane.com/graphql', 'https://api.hemlane.com.evil.invalid/graphql',
                    'https://evil.invalid/api.hemlane.com/graphql',
                    'https://api.hemlane.com@evil.invalid/graphql',
                    'https://u@api.hemlane.com/graphql', 'https://api.hemlane.com:8443/graphql',
                    'https://api.hemlane.com/graphql-else', 'https://api.hemlane.com/graphql?x=1'):
            with self.subTest(url=url):
                self.assertFalse(capture.is_api_graphql(url))
        self.assertTrue(capture.is_hemlane_tab('https://www.hemlane.com/dashboards/owner/'))
        self.assertFalse(capture.is_hemlane_tab('https://hemlane.com.evil.invalid/'))

    def test_no_target_hijack_or_wrong_explicit_target(self):
        tabs = [{'id': 'other', 'type': 'page', 'url': 'https://example.invalid'},
                {'id': 'hem', 'type': 'page', 'url': 'https://www.hemlane.com/'}]
        self.assertEqual(capture.select_tab(tabs)['id'], 'hem')
        with self.assertRaises(ValueError):
            capture.select_tab(tabs, 'other')
        with self.assertRaises(ValueError):
            capture.select_tab(tabs[:1])

    def test_unattributed_extra_info_and_other_hosts_are_ignored(self):
        events = [extra('unobserved', {'Authorization': 'fixture-secret'}),
                  request('other', 'https://evil.invalid/graphql'),
                  extra('other', {'Authorization': 'fixture-secret'})]
        self.assertEqual(capture.select_captured_auth(events), (None, None))

    def test_extra_info_is_joined_by_id_even_when_delivered_first(self):
        events = [extra('api', {'Authorization': 'fixture-secret'}),
                  request('api'), extra('other', {'Authorization': 'wrong-fixture'})]
        headers, source = capture.select_captured_auth(events)
        self.assertEqual(headers, {'authorization': 'fixture-secret'})
        self.assertEqual(source['url'], capture.API_URL)

    def test_redirect_reused_id_is_rejected(self):
        events = [request('reused', 'https://evil.invalid/graphql'),
                  extra('reused', {'Authorization': 'unrelated-fixture'}),
                  request('reused', redirectResponse={'status': 302})]
        self.assertEqual(capture.select_captured_auth(events), (None, None))

    def test_cookie_domains_are_exact_and_api_scoped(self):
        cookies = [{'domain': '.hemlane.com', 'name': 'session', 'value': 'fixture'},
                   {'domain': '.evil-hemlane.com', 'name': 'bad', 'value': 'fixture'},
                   {'domain': 'hemlane.com.evil.invalid', 'name': 'bad', 'value': 'fixture'},
                   {'domain': 'www.hemlane.com', 'name': 'ui-only', 'value': 'fixture'}]
        self.assertEqual(capture.scoped_cookie_header(cookies), 'session=fixture')

    def test_private_output_refuses_overwrite_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'auth.json'
            capture.write_auth_exclusive(output, {'cookie': 'synthetic-fixture'})
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                capture.write_auth_exclusive(output, {})
            link = Path(directory) / 'link.json'
            link.symlink_to(output)
            with self.assertRaises(FileExistsError):
                capture.write_auth_exclusive(link, {})
            self.assertEqual(json.loads(output.read_text()), {'cookie': 'synthetic-fixture'})

    def test_existing_output_stops_before_browser_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'existing'
            output.touch()
            args = argparse.Namespace(out_file=str(output), target_id=None)
            with patch.object(capture, 'get_tabs') as tabs:
                with self.assertRaises(ValueError):
                    capture.capture(args)
                tabs.assert_not_called()

    def test_bridge_rewrites_advertised_host_to_canonical_bridge(self):
        with patch.object(capture, 'CDP_BASE', 'http://bridge.example.invalid:9222'):
            self.assertEqual(capture.through_cdp_bridge('ws://untrusted.invalid/devtools/page/one'),
                             'ws://bridge.example.invalid:9222/devtools/page/one')

    def test_error_output_never_contains_exception_body(self):
        stdout = io.StringIO()
        with patch.object(sys, 'argv', ['capture', '--out-file', '/unused-fixture']), \
             patch.object(capture, 'capture', side_effect=RuntimeError('SYNTHETIC_PRIVATE_BODY')), \
             contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit):
                capture.main()
        self.assertNotIn('SYNTHETIC_PRIVATE_BODY', stdout.getvalue())
        self.assertEqual(json.loads(stdout.getvalue())['error'], 'auth_capture_failed')

    def test_capture_uses_network_events_and_returns_metadata_only(self):
        class Timeout(Exception):
            pass

        class Socket:
            def __init__(self):
                self.messages = [{'id': 1, 'result': {}}, {'id': 2, 'result': {}},
                                 request('api', headers={'Authorization': 'synthetic-only'})]
                self.sent = []
                self.closed = False
            def connect(self, *args, **kwargs):
                pass
            def settimeout(self, timeout):
                pass
            def send(self, body):
                command = json.loads(body)
                self.sent.append(command)
                if command['method'] == 'Network.getCookies':
                    self.messages.append({'id': command['id'], 'result': {'cookies': [
                        {'domain': '.hemlane.com', 'name': 'session', 'value': 'cookie-fixture'},
                        {'domain': 'other.invalid', 'name': 'unrelated', 'value': 'excluded'}]}})
            def recv(self):
                if self.messages:
                    return json.dumps(self.messages.pop(0))
                raise Timeout()
            def close(self):
                self.closed = True

        socket = Socket()
        fake_ws = types.SimpleNamespace(WebSocket=lambda: socket, WebSocketTimeoutException=Timeout)
        clock = iter(value / 2 for value in range(200))
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(out_file=str(Path(directory) / 'auth.json'),
                                      target_id=None, endpoint_kind='get-properties')
            tabs = [{'id': 'hem', 'type': 'page', 'url': 'https://www.hemlane.com/',
                     'webSocketDebuggerUrl': 'ws://example.invalid/devtools/page/hem'}]
            with patch.dict(sys.modules, {'websocket': fake_ws}), \
                 patch.object(capture, 'CDP_BASE', 'http://browser.example.invalid:9222'), \
                 patch.object(capture, 'get_tabs', return_value=tabs), \
                 patch.object(capture.time, 'monotonic', side_effect=lambda: next(clock)):
                result = capture.capture(args)
            self.assertNotIn('synthetic-only', json.dumps(result))
            self.assertNotIn('headers', result)
            self.assertEqual(json.loads(Path(args.out_file).read_text())['authorization'], 'synthetic-only')
            self.assertEqual(json.loads(Path(args.out_file).read_text())['cookie'], 'session=cookie-fixture')
            self.assertEqual(socket.sent[-1]['params'], {'urls': [capture.API_URL]})
            self.assertEqual([message['method'] for message in socket.sent],
                             ['Network.enable', 'Page.reload', 'Network.getCookies'])
            self.assertTrue(socket.closed)


if __name__ == '__main__':
    unittest.main()
