#!/usr/bin/env python3
"""Synthetic agent: consumes the prompted artifact and writes a digest and receipt.

Never render, update state, or deliver here: those are runner responsibilities.
"""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

root = Path(os.environ['JOB_AGENT_ROOT'])
track = os.environ['JOB_AGENT_TRACK']
today = os.environ['JOB_AGENT_TODAY']
prompt = sys.stdin.read()
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
review_path = re.search(r'^Use \./(artifacts/reviews/\S+\.json) as the sole discovery input', prompt, re.M)
artifact = root / review_path[1] if review_path else root / 'artifacts/discovery' / track / f'{today}.json'
if review_path:
    assert f'./{artifact.relative_to(root).with_suffix(".receipt.json")}' in prompt
    (root / 'agent-review-input.txt').write_text(str(artifact.relative_to(root)))
daily_digest = root / 'artifacts/digests' / track / f'{today}.json'
if review_path:
    digest_path = re.search(r'write the complete structured digest for today to \./(artifacts/reviews/\S+\.digest\.json)', prompt)
    output = root / digest_path[1]
else:
    output = daily_digest
output.parent.mkdir(parents=True, exist_ok=True)
discovery = json.loads(artifact.read_text())
seen_path = root / 'tracks' / track / 'seen_jobs.json'
seen = {(job['company'], job['title']) for job in json.loads(seen_path.read_text())['jobs']} if seen_path.exists() else set()
roles = []
notes = []
batches = []
for source in discovery['sources']:
    batch = {'source_id': source['source_id'], 'complete': behavior != 'partial'}
    candidates = source['candidates']
    if behavior == 'partial':
        candidates = candidates[:1]
    # The standalone smoke uses a file board and only tests plumbing.
    usable = [candidate for candidate in candidates if candidate['description'] or candidate['url'].startswith('file:')]
    if review_path:
        if behavior == 'partial':
            batch['reviewed'] = [candidate['candidate_id'] for candidate in usable]
        batch['deferred'] = [candidate['candidate_id'] for candidate in candidates if candidate not in usable]
        batches.append(batch)
    for candidate in usable:
        if behavior == 'no_reports' or (candidate['employer'], candidate['title']) in seen:
            continue
        roles.append({'company': candidate['employer'], 'title': candidate['title'], 'listing_url': candidate['url'],
                      'location': candidate.get('location', 'unknown'), 'source': source['source'],
                      'fit_score': 8.4, 'recommendation': 'watch', 'why_match': ['Synthetic reviewed match.'], 'concerns': []})
    notes.append({'source': source['source'], 'discovery_mode': source['discovery_mode'], 'status': source['status'],
                  'listing_pages_scanned': source['listing_pages_scanned'], 'search_terms_tried': source['search_terms_tried'],
                  'result_pages_summary': source['result_pages_scanned'], 'direct_job_pages_opened': source['direct_job_pages_opened'],
                  'limitations': source['limitations'], 'note': f"{source['matched_jobs']} original matches"})
payload = {'schema_version': 1, 'track': track, 'date': today, 'runs': [{
    'kind': 'initial', 'generated_at': f'{today}T09:00:00+00:00',
    'executive_summary': f'{len(roles)} synthetic matches.', 'recommended_actions': [],
    'top_matches': roles, 'other_new_roles': [], 'filtered_roles': [], 'source_notes': notes,
    'notes_for_next_run': [], 'discovery_artifacts': [str(artifact.relative_to(root))]}]}
previous = None
if daily_digest.is_file():
    try:
        existing = json.loads(daily_digest.read_text())
        if existing.get('schema_version') == 1:
            previous = existing
    except (ValueError, AttributeError):
        pass
unchanged = review_path is not None and previous is not None and not roles
if review_path and behavior != 'missing_receipt':
    receipt = {'run_id': discovery['run_id'], 'digest_unchanged': unchanged, 'batches': batches}
    if behavior == 'unknown_id':
        batches[0]['deferred'] = ['not-in-artifact']
    elif behavior == 'stale_receipt':
        receipt['run_id'] = 'older-run-id'
    artifact.with_suffix('.receipt.json').write_text(json.dumps(receipt))
if unchanged:
    raise SystemExit(0)
if previous:
    payload['runs'][0]['kind'] = 'update'
    payload['runs'] = previous['runs'] + payload['runs']
if behavior == 'invalid_schema':
    payload['schema_version'] = 999
output.write_text('{not JSON' if behavior == 'malformed' else json.dumps(payload, indent=2) + '\n')
