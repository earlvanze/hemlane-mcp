"""Shared CLI options for legacy HAR wrappers; previews need no credentials."""
import json
import subprocess
import sys
from pathlib import Path


def add_replay_arguments(parser):
    parser.add_argument('--auth-file')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-digest')
    parser.add_argument('--journal')


def replay(query, operation, payload, args):
    cmd = [sys.executable, str(Path(__file__).parent / 'replay_hemlane_graphql.py'),
           '--query', str(query), '--variables', '-', '--operation-name', operation]
    for flag in ('auth_file', 'confirm_digest', 'journal'):
        if getattr(args, flag, None):
            cmd.extend(['--' + flag.replace('_', '-'), getattr(args, flag)])
    for flag in ('dry_run', 'pretty', 'apply'):
        if getattr(args, flag, False):
            cmd.append('--' + flag.replace('_', '-'))
    return subprocess.run(cmd, input=json.dumps(payload), text=True).returncode
