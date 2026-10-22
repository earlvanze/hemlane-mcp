#!/usr/bin/env python3
import argparse, json, subprocess, sys
from pathlib import Path
from replay_wrapper import add_replay_arguments, replay

ROOT = Path(__file__).resolve().parent.parent
QUERY = ROOT / 'references' / 'workorder-comment.graphql'
REPLAY = ROOT / 'scripts' / 'replay_hemlane_graphql.py'

ap = argparse.ArgumentParser(description='Post a Hemlane maintenance work-order comment.')
add_replay_arguments(ap)
ap.add_argument('--workorder-id', required=True)
ap.add_argument('--body', required=True)
ap.add_argument('--hide-from-tenants', action='store_true')
ap.add_argument('--dry-run', action='store_true')
ap.add_argument('--pretty', action='store_true')
args = ap.parse_args()

payload = {
    'input': {
        'maintenanceWorkOrderId': args.workorder_id,
        'body': args.body,
        'isHiddenFromTenants': bool(args.hide_from_tenants)
    }
}
raise SystemExit(replay(QUERY, 'OwnerMaintenanceWorkOrderCommentCreate', payload, args))
