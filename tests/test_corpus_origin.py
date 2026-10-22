"""Exercise the actual local corpus server over MCP stdio; no HTTP requests."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SERVER = os.environ.get('HAR_CORPUS_SERVER')


@unittest.skipUnless(SERVER and Path(SERVER).is_file(), 'Set HAR_CORPUS_SERVER for optional external corpus integration')
class CorpusOriginTests(unittest.TestCase):
    def test_selected_graphql_host_wins_over_pubnub_primary_origin(self):
        fixture = {'profiles': [{'slug': 'tenant-reply-hemlane-com',
                   'sourceFile': 'synthetic.har', 'primaryOrigin': 'https://ps3.pndsn.com',
                   'endpoints': [{'id': 'graphql', 'method': 'POST',
                                  'host': 'api.hemlane.com', 'path': '/graphql',
                                  'requestJsonKeys': ['query', 'variables']}]}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profiles.json'
            path.write_text(json.dumps(fixture))
            message = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
                'name': 'har_request_template', 'arguments': {
                    'profile': 'tenant-reply-hemlane-com', 'endpointId': 'graphql'}}}
            env = dict(os.environ, HAR_CORPUS_PROFILE_PATH=str(path))
            response = subprocess.run(['node', str(SERVER)], input=json.dumps(message) + '\n',
                                      text=True, capture_output=True, check=True, env=env)
        result = json.loads(json.loads(response.stdout)['result']['content'][0]['text'])
        self.assertIn('https://api.hemlane.com/graphql', result['template'])
        self.assertNotIn('ps3.pndsn.com', result['template'])


if __name__ == '__main__':
    unittest.main()
