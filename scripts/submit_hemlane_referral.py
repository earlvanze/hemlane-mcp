#!/usr/bin/env python3
import argparse, json, os, subprocess, sys
from pathlib import Path
from replay_wrapper import add_replay_arguments, replay

ROOT = Path(__file__).resolve().parent.parent
QUERY = ROOT / 'references' / 'example-hubspot-submit.graphql'
REPLAY = ROOT / 'scripts' / 'replay_hemlane_graphql.py'

ap = argparse.ArgumentParser(description='Submit a Hemlane referral using the HAR-derived HubspotFormSubmit mutation.')
add_replay_arguments(ap)
ap.add_argument('--first-name', required=True)
ap.add_argument('--last-name', required=True)
ap.add_argument('--phone', required=True)
ap.add_argument('--email', required=True)
ap.add_argument('--referrer-name', required=True)
ap.add_argument('--referrer-email', required=True)
ap.add_argument('--form-id', required=True)
ap.add_argument('--page-uri', default='https://www.hemlane.com/dashboards/owner/')
ap.add_argument('--dry-run', action='store_true')
ap.add_argument('--pretty', action='store_true')
args = ap.parse_args()

mapv = {
    'firstname': args.first_name,
    'lastname': args.last_name,
    'phone': args.phone,
    'email': args.email,
    'referrername': args.referrer_name,
    'referreremail': args.referrer_email,
}
payload = {'input': {'formId': args.form_id,
    'fields': [{'name': key, 'value': value} for key, value in mapv.items()],
    'context': {'pageUri': args.page_uri}}}

raise SystemExit(replay(QUERY, 'HubspotFormSubmit', payload, args))
