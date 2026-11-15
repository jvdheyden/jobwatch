#!/usr/bin/env python3
"""Synthetic agent: consumes discovery and writes ONLY a structured digest.

Never render, update state, or deliver here: those are runner responsibilities.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

root = Path(os.environ['JOB_AGENT_ROOT'])
track = os.environ['JOB_AGENT_TRACK']
today = os.environ['JOB_AGENT_TODAY']
sys.stdin.read()
behavior = os.environ.get('TEST_AGENT_BEHAVIOR', 'success')
if behavior == 'failure':
    raise SystemExit(7)
if behavior == 'timeout':
    # Real agent CLIs launch tools. A child retaining stdout must not keep the
    # runner's reader alive after its parent exits on TERM.
    subprocess.Popen([sys.executable, '-c',
        "import os, signal; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "Path(os.environ['JOB_AGENT_ROOT'], 'agent-child-started').touch(); signal.pause()"])
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.pause()
if behavior == 'missing':
    raise SystemExit(0)
artifact = root / 'artifacts/discovery' / track / f'{today}.json'
output = root / 'artifacts/digests' / track / f'{today}.json'
output.parent.mkdir(parents=True, exist_ok=True)
if behavior == 'malformed':
    output.write_text('{not JSON')
    raise SystemExit(0)
discovery = json.loads(artifact.read_text())
roles = []
notes = []
for source in discovery['sources']:
    for candidate in source['candidates']:
        roles.append({'company': candidate['employer'], 'title': candidate['title'], 'listing_url': candidate['url'],
                      'location': candidate.get('location', 'unknown'), 'source': source['source'],
                      'fit_score': 8.4, 'recommendation': 'watch', 'why_match': ['Synthetic reviewed match.'], 'concerns': []})
    notes.append({'source': source['source'], 'discovery_mode': source['discovery_mode'], 'status': source['status'],
                  'listing_pages_scanned': source['listing_pages_scanned'], 'search_terms_tried': source['search_terms_tried'],
                  'result_pages_summary': source['result_pages_scanned'], 'direct_job_pages_opened': source['direct_job_pages_opened'],
                  'limitations': source['limitations']})
payload = {'schema_version': 1, 'track': track, 'date': today, 'runs': [{
    'kind': 'initial', 'generated_at': f'{today}T09:00:00+00:00',
    'executive_summary': f'{len(roles)} synthetic matches.', 'recommended_actions': [],
    'top_matches': roles, 'other_new_roles': [], 'filtered_roles': [], 'source_notes': notes,
    'notes_for_next_run': [], 'discovery_artifacts': [str(artifact.relative_to(root))]}]}
if behavior == 'invalid_schema':
    payload['schema_version'] = 999
output.write_text(json.dumps(payload, indent=2) + '\n')
