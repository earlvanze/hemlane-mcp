"""Offline regressions for payment allocation, messaging and uncertain-outcome workflows."""
import copy
import asyncio
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import hemlane_safety as safety
import replay_hemlane_graphql as replay
import send_hemlane_tenant_reply as sender
from reconcile_payment_allocations import cents, reconcile


class FakeAPI:
    def __init__(self, messages=None, wrong_scope=False, timeout=False):
        self.messages = messages or []
        self.wrong_scope = wrong_scope
        self.timeout = timeout
        self.mutations = 0

    def __call__(self, headers, payload):
        operation = payload['operationName']
        if operation == 'HemlaneMessagePreflight':
            return {'data': {'currentUser': {'id': 'wrong' if self.wrong_scope else 'owner'},
                             'tenantGroup': {'property': {'id': 'property'}}}}
        if operation == 'OwnerTenancyMessages':
            return {'data': {'tenantGroup': {'property': {'id': 'property'}},
                'tenancyMessages': {'edges': [{'node': m} for m in self.messages],
                                   'pageInfo': {'hasNextPage': False, 'endCursor': None}}}}
        if operation == 'ODProspectiveTenantGroupMessageCreate':
            self.mutations += 1
            message = {'id': 'sent-id', 'body': payload['variables']['input']['body'],
                       'createdByInfo': {'id': 'owner'}, 'isOwnerPrivate': False,
                       'isAdminOnly': False, 'isSystem': False}
            self.messages.append(message)
            if self.timeout:
                raise safety.SafetyError('transport_or_response_error_outcome_unverified')
            return {'data': {'tenantGroupMessageAdd': {'tenantGroupMessage': message}}}
        raise AssertionError(operation)


class TransportTests(unittest.TestCase):
    def test_wrong_origins_never_reach_transport(self):
        urls = ['https://ps3.pndsn.com/graphql', 'http://api.hemlane.com/graphql',
                'https://api.hemlane.com.evil.test/graphql', 'https://api.hemlane.com:443/graphql',
                'https://user@api.hemlane.com/graphql', 'https://api.hemlane.com/graphql?token=x',
                'https://api.hemlane.com/graphql#fragment', 'https://api.hemlane.com/elsewhere']
        with patch.object(safety.request, 'build_opener') as opener:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(safety.SafetyError):
                    safety.graphql({'authorization': 'fake-secret'}, {}, url)
            opener.assert_not_called()

    def test_redirect_refused(self):
        with self.assertRaisesRegex(safety.SafetyError, 'redirect_refused'):
            safety.NoRedirect().redirect_request(None, None, 302, None, {}, 'https://evil.test')

    def test_graphql_field_errors_do_not_report_success(self):
        response = io.StringIO(json.dumps({'data': {'mutation': {'id': None,
            'errors': {'base': ['private body or secret'], '__typename': 'Errors'}}}}))
        with patch.object(safety.request, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(safety.SafetyError, '^graphql_error_outcome_unverified$'):
                safety.graphql({}, {'query': 'mutation M { m }'})
        self.assertFalse(safety.has_field_errors({'data': {'m': {'errors': {'base': [], '__typename': 'E'}}}}))

    def test_atomic_receipt_and_no_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'journal.json'
            safety.private_json(path, {'status': 'attempting'}, exclusive=True)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                safety.private_json(path, {}, exclusive=True)
            with patch.object(safety.os, 'replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    safety.private_json(path, {'status': 'done'})
            self.assertEqual(json.loads(path.read_text()), {'status': 'attempting'})
            link = Path(directory) / 'link'
            link.symlink_to(path)
            with self.assertRaises(safety.SafetyError):
                safety.private_json(link, {})

    def test_hash_in_string_cannot_hide_mutation(self):
        document = 'query Q { tenantGroup(tenantGroupId:"#") {property{id}} } mutation M { change {id} }'
        args = ['replay', '--query', document, '--operation-name', 'M']
        with patch.object(sys, 'argv', args), patch.object(replay, 'graphql') as network, redirect_stdout(io.StringIO()) as out:
            replay.main()
        network.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())['status'], 'preview')

    def test_generic_mutation_requires_digest_and_new_receipt(self):
        args = ['replay', '--query', 'mutation M { change {id} }', '--apply']
        with patch.object(sys, 'argv', args), patch.object(replay, 'graphql') as network:
            with self.assertRaises(safety.SafetyError):
                replay.main()
        network.assert_not_called()


class SendTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.journal = Path(self.directory.name) / 'send.json'
        self.plan = sender.plan_message('tenancy', 'Your charge has been updated.', 'owner', 'property')

    def test_native_readback_and_single_send(self):
        api = FakeAPI()
        result = sender.send_once({}, self.plan, safety.digest(self.plan), self.journal, api)
        self.assertEqual(result['status'], 'sent_verified')
        self.assertEqual(api.mutations, 1)
        with self.assertRaisesRegex(safety.SafetyError, 'journal_exists'):
            sender.send_once({}, self.plan, safety.digest(self.plan), self.journal, api)
        self.assertEqual(api.mutations, 1)

    def test_timeout_recovery_never_resends(self):
        api = FakeAPI(timeout=True)
        with self.assertRaisesRegex(safety.SafetyError, 'never_resend'):
            sender.send_once({}, self.plan, safety.digest(self.plan), self.journal, api)
        receipt = json.loads(self.journal.read_text())
        self.assertEqual(receipt['status'], 'outcome_unverified_do_not_resend')
        result = sender.verify_receipt({}, receipt, self.journal, api)
        self.assertEqual(result['status'], 'sent_verified')
        self.assertEqual(api.mutations, 1)

    def test_wrong_account_and_changed_body_block_before_mutation(self):
        api = FakeAPI(wrong_scope=True)
        with self.assertRaisesRegex(safety.SafetyError, 'scope_mismatch'):
            sender.send_once({}, self.plan, safety.digest(self.plan), self.journal, api)
        with self.assertRaisesRegex(safety.SafetyError, 'digest_mismatch'):
            sender.send_once({}, self.plan, 'stale-digest', self.journal, api)
        self.assertEqual(api.mutations, 0)
        self.assertFalse(self.journal.exists())

    def test_duplicate_thread_message_stops_send(self):
        api = FakeAPI(messages=[{'id': 'existing', 'body': self.plan['payload']['variables']['input']['body']}])
        with self.assertRaisesRegex(safety.SafetyError, 'already_exists'):
            sender.send_once({}, self.plan, safety.digest(self.plan), self.journal, api)
        self.assertEqual(api.mutations, 0)

    def test_private_or_wrong_author_message_cannot_verify(self):
        body = self.plan['payload']['variables']['input']['body']
        receipt = {'plan': self.plan, 'digest': safety.digest(self.plan), 'baselineIds': []}
        for flag in ('isOwnerPrivate', 'isAdminOnly', 'isSystem', 'wrongAuthor'):
            message = {'id': 'new', 'body': body, 'createdByInfo': {'id': 'owner'},
                       'isOwnerPrivate': False, 'isAdminOnly': False, 'isSystem': False}
            if flag == 'wrongAuthor':
                message['createdByInfo']['id'] = 'tenant'
            else:
                message[flag] = True
            with self.subTest(flag=flag):
                result = sender.verify_receipt({}, copy.deepcopy(receipt), self.journal, FakeAPI([message]))
                self.assertEqual(result['status'], 'outcome_unverified_do_not_resend')

    def test_incomplete_pagination_cannot_be_used_as_preflight(self):
        api = FakeAPI()
        def incomplete(headers, payload):
            response = api(headers, payload)
            if payload['operationName'] == 'OwnerTenancyMessages':
                response['data']['tenancyMessages']['pageInfo'] = {'hasNextPage': True, 'endCursor': None}
            return response
        with self.assertRaisesRegex(safety.SafetyError, 'pagination_incomplete'):
            sender.send_once({}, self.plan, safety.digest(self.plan), self.journal, incomplete)
        self.assertEqual(api.mutations, 0)


def evidence():
    months = [f'2030-{i:02}' for i in range(1, 13)] + ['2031-01']
    periods, deposits = [], []
    for i, month in enumerate(months):
        amount = '800.00' if i < 7 else '825.00'
        periods.append({'month': month, 'charge': '1000', 'responsiblePaid': '150',
                        'existingResponsibleCharge': '150' if i < 12 else '175',
                        'verified': True, 'treatment': 'true_up' if i < 12 else 'correct_regular'})
        deposits.append({'id': f'deposit-{i}', 'amount': amount, 'postedDate': month + '-05',
                         'verified': True, 'evidenceRef': 'synthetic-evidence.json',
                         'allocations': [{'month': month, 'amount': amount}]})
    # A single combined deposit for two distinct rent periods.
    deposits[0]['amount'] = '1600.00'
    deposits[0]['allocations'] += deposits[1]['allocations']
    del deposits[1]
    return {'scope': {'userId': 'owner', 'propertyId': 'property', 'recordId': 'agreement'}, 'responsibilityConfirmed': True, 'periods': periods, 'deposits': deposits}


class ReconciliationTests(unittest.TestCase):
    def test_historical_shortages_exclude_corrected_current_month(self):
        plan = reconcile(evidence())
        self.assertEqual(plan['trueUpCents'], 47500)
        self.assertEqual(plan['rows'][-1]['responsibleChargeCents'], 17500)
        self.assertEqual(plan['rows'][-1]['trueUpContributionCents'], 0)

    def test_already_billed_unpaid_charge_is_not_charged_again(self):
        data = evidence()
        data['periods'][0].update(existingResponsibleCharge='200', responsiblePaid='0')
        plan = reconcile(data)
        self.assertEqual(plan['rows'][0]['shortageOrCreditCents'], 20000)
        self.assertEqual(plan['rows'][0]['trueUpContributionCents'], 0)
        self.assertEqual(plan['trueUpCents'], 42500)

    def test_overbilled_credit_is_signed(self):
        data = evidence()
        data['periods'][0]['existingResponsibleCharge'] = '250'
        self.assertEqual(reconcile(data)['rows'][0]['trueUpContributionCents'], -5000)

    def test_duplicate_month_or_deposit_and_unbalanced_allocation_block(self):
        mutations = [lambda d: d['periods'].append(copy.deepcopy(d['periods'][0])),
                     lambda d: d['deposits'].append(copy.deepcopy(d['deposits'][0])),
                     lambda d: d['deposits'][0].update(amount='800.00'),
                     lambda d: d['deposits'][0].update(verified=False),
                     lambda d: d['periods'][0].pop('existingResponsibleCharge')]
        for mutate in mutations:
            data = evidence()
            mutate(data)
            with self.subTest(mutate=mutate), self.assertRaises((safety.SafetyError, KeyError)):
                reconcile(data)

    def test_responsibility_is_explicit_and_payer_role_is_generic(self):
        data = evidence()
        data['scope']['recordId'] = 'insurance-agreement-example'
        plan = reconcile(data)
        self.assertEqual(plan['scope']['recordId'], 'insurance-agreement-example')
        self.assertNotIn('tenantGroupId', plan['scope'])
        self.assertEqual(plan['rows'][0]['externalPaidCents'], 80000)
        data['responsibilityConfirmed'] = False
        with self.assertRaisesRegex(safety.SafetyError, 'responsibility_must_be_confirmed'):
            reconcile(data)

    def test_fractional_cents_or_nonfinite_money_rejected(self):
        for value in ('1.001', 'NaN', 'Infinity', True):
            with self.subTest(value=value), self.assertRaises(safety.SafetyError):
                cents(value)
        self.assertEqual(cents('17.50'), 1750)


class MCPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('hemlane_test_server', ROOT / 'mcp/server.py')
        cls.server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.server)

    def test_tenant_and_legacy_wrappers_preview_without_network_or_auth(self):
        cases = [
            lambda: self.server.send_tenant_reply('tenancy', 'Synthetic preview.', '/nonexistent', 'owner', 'property'),
            lambda: self.server.post_workorder_comment('workorder', 'Synthetic preview.', '/nonexistent'),
            lambda: self.server.post_maintenance_comment('request', 'Synthetic preview.', '/nonexistent'),
            lambda: self.server.submit_referral('Test', 'Person', 'test@example.invalid', '0000000000',
                                               'Referrer', 'ref@example.invalid', '/nonexistent', 'synthetic-form')]
        for call in cases:
            result = call()
            self.assertTrue(result.get('success'), result)
            self.assertEqual(result['result']['status'], 'preview')

    def test_apply_and_auth_capture_require_trusted_operator(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(self.server, 'run_script') as run:
            out = self.server.send_tenant_reply('record', 'body', '/none', 'owner',
                'property', apply=True, confirm_digest='digest', journal='/private/journal')
            self.assertEqual(out['error'], 'write_blocked_unverified_operator')
            self.assertEqual(self.server.capture_auth(out_file='/private/auth')['error'],
                             'write_blocked_unverified_operator')
            run.assert_not_called()
        import hashlib
        allowed = hashlib.sha256(b'synthetic-operator').hexdigest()
        with patch.dict(os.environ, {'HEMLANE_CALLER_ID': 'synthetic-operator',
                'HEMLANE_ALLOWED_CALLER_SHA256': allowed}, clear=True):
            self.assertIsNone(self.server.require_operator())
            self.assertEqual(self.server.mutation_options(True, 'digest', '/private/journal'),
                ['--apply', '--confirm-digest', 'digest', '--journal', '/private/journal'])

    def test_referral_preview_contains_only_explicit_personal_inputs(self):
        result = self.server.submit_referral('Example', 'Person', 'person@example.invalid',
            '0000000000', 'Example Referrer', 'referrer@example.invalid',
            '/nonexistent', 'form-example')
        self.assertTrue(result.get('success'), result)
        payload = result['result']['payload']['variables']['input']
        self.assertEqual(payload, {
            'formId': 'form-example',
            'fields': [
                {'name': 'firstname', 'value': 'Example'},
                {'name': 'lastname', 'value': 'Person'},
                {'name': 'phone', 'value': '0000000000'},
                {'name': 'email', 'value': 'person@example.invalid'},
                {'name': 'referrername', 'value': 'Example Referrer'},
                {'name': 'referreremail', 'value': 'referrer@example.invalid'}],
            'context': {'pageUri': 'https://www.hemlane.com/dashboards/owner/'}})

    def test_existing_upstream_read_contracts_are_retained(self):
        with patch.object(self.server, 'run_script', return_value={'success': True,
                'result': {'count': 2}}) as run:
            self.assertEqual(self.server.query_recurring_payment_requests('/none'), {'count': 2})
            self.assertEqual(self.server.get_context_values('/none'), {'count': 2})
            self.assertEqual(self.server.query_financials_operation('/none', 'Query'), {'count': 2})
        self.assertEqual(run.call_count, 3)
        self.assertTrue(callable(self.server.get_tenant_groups))
        self.assertTrue(callable(self.server.get_maintenance_requests))

    def test_subprocess_errors_withhold_raw_output(self):
        result = subprocess.CompletedProcess([], 2, 'fake-secret-content', 'fake-secret-header')
        with patch.object(self.server.subprocess, 'run', return_value=result):
            out = self.server.run_script('send_hemlane_tenant_reply.py')
        self.assertNotIn('fake-secret', json.dumps(out))
        self.assertFalse(out['success'])

    def test_unverified_rent_roll_and_unsupported_visibility_fail_closed(self):
        with patch.object(self.server, 'run_script') as run:
            self.assertIn('error', self.server.extract_rent_roll('property', '/nonexistent'))
            self.assertIn('error', self.server.post_workorder_comment('w', 'body', '/none', hidden_from_owners=True))
        run.assert_not_called()

    def test_real_stdio_schema_and_preview(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        async def smoke():
            parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'mcp/server.py')])
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    names = {tool.name for tool in listing.tools}
                    self.assertTrue({'send_tenant_reply', 'verify_tenant_reply',
                                     'plan_payment_reconciliation'} <= names)
                    result = await session.call_tool('send_tenant_reply', {
                        'tenant_group_id': 'synthetic-tenancy', 'message': 'Offline MCP preview.',
                        'auth_file': '/nonexistent', 'expected_user_id': 'synthetic-owner',
                        'property_id': 'synthetic-property'})
                    data = json.loads(result.content[0].text)
                    self.assertEqual(data['status'], 'preview')
                    self.assertFalse(data['verified'])
        asyncio.run(smoke())


if __name__ == '__main__':
    unittest.main()
