"""Real runner/discovery/rendering/persistence/delivery with local HTTP and agent doubles."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import threading

import pytest


@pytest.fixture
def workflow(tmp_path, repo_root, run_cmd):
    board = {'jobs': [1, 2], 'status': 200, 'descriptions': {}}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/careers':
                body = ''.join(f'<a href="/jobs/{i}">Cryptography Engineer {i}</a>' for i in board['jobs'])
                status = board['status']
            else:
                details = board['descriptions'].get(self.path, 'Build cryptography libraries in Rust.')
                body = f'<main><h2>Responsibilities</h2>{details}</main>' if details else ''
                status = 200
            content = body.encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = tmp_path / 'root'
    shutil.copytree(repo_root / 'scripts', root / 'scripts', ignore=shutil.ignore_patterns('__pycache__', 'local'))
    (root / '.venv').symlink_to(repo_root / '.venv', target_is_directory=True)
    track = root / 'tracks/demo'
    track.mkdir(parents=True)
    (track / 'AGENTS.md').write_text('Consume discovery and produce a structured digest.\n')
    (track / 'sources.json').write_text(json.dumps({'schema_version': 1, 'track': 'demo', 'track_terms': ['cryptography'],
        'sources': [{'id': 'local', 'name': 'Local Careers', 'url': f'http://127.0.0.1:{server.server_port}/careers',
                     'discovery_mode': 'html', 'cadence_group': 'every_run'}]}))
    def run(stamp='2030-01-15', behavior='success', provider='codex', deliver=True, graph=None):
        env = os.environ | {'JOB_AGENT_ROOT': str(root), 'JOB_AGENT_PROVIDER': provider,
            'JOB_AGENT_BIN': str(repo_root / 'tests/e2e/fake_codex.sh'), 'JOB_AGENT_TODAY': stamp,
            'JOB_AGENT_JOURNAL_DATE': stamp.replace('-', '_'), 'TEST_AGENT_BEHAVIOR': behavior,
            'LOGSEQ_GRAPH_DIR': str(graph or root / 'graph'), 'JOB_AGENT_PLATFORM': 'Linux', 'JOB_AGENT_CAFFEINATED': '1'}
        args = ['bash', str(root / 'scripts/run_track.sh'), '--track', 'demo', '--timeout-secs', '1' if behavior == 'timeout' else '15']
        if deliver:
            args += ['--delivery', 'logseq']
        result = run_cmd(*args, env=env, cwd=root)
        return result, (root / f'logs/demo-{stamp}.log').read_text()
    try:
        yield root, board, run
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def read(root, path):
    return json.loads((root / path).read_text())


def review_input(root):
    return read(root, (root / 'agent-review-input.txt').read_text())


@pytest.mark.parametrize('provider', ['codex', 'claude', 'gemini'])
def test_track_runs_real_postprocessing_and_delivery(workflow, provider):
    root, board, run = workflow
    result, log = run(provider=provider)
    assert result.returncode == 0, log
    discovery = read(root, 'artifacts/discovery/demo/2030-01-15.json')
    assert [c['title'] for c in discovery['sources'][0]['candidates']] == ['Cryptography Engineer 1', 'Cryptography Engineer 2']
    assert discovery['sources'][0]['candidates'][0]['description']
    assert len(read(root, 'tracks/demo/seen_jobs.json')['jobs']) == 2
    assert read(root, 'tracks/demo/source_state.json')['sources']['local']['last_checked'] == '2030-01-15'
    assert len(read(root, 'shared/ranked_jobs/demo.json')['jobs']) == 2
    assert read(root, 'artifacts/digests/demo/latest.json') == read(root, 'artifacts/digests/demo/2030-01-15.json')
    digest = (root / 'tracks/demo/digests/2030-01-15.md').read_text()
    assert 'Cryptography Engineer 2' in digest
    assert (root / 'graph/pages/Demo Job Digest 2030-01-15.md').read_text() == digest
    assert 'Demo Job Digest 2030-01-15' in (root / 'graph/journals/2030_01_15.md').read_text()


def test_complete_failed_and_complete_runs_preserve_then_close_jobs(workflow):
    root, board, run = workflow
    assert run()[0].returncode == 0
    before = read(root, 'tracks/demo/seen_jobs.json')
    # Re-execution cannot duplicate reported jobs.
    assert run()[0].returncode == 0
    assert read(root, 'tracks/demo/seen_jobs.json') == before
    assert all(j['times_seen'] == 1 for j in read(root, 'shared/ranked_jobs/demo.json')['jobs'])
    board['status'] = 503
    result, log = run('2030-01-16')
    assert result.returncode == 0, log
    assert read(root, 'artifacts/discovery/demo/2030-01-16.json')['sources'][0]['status'] == 'failed'
    assert read(root, 'tracks/demo/source_state.json')['sources']['local']['last_checked'] == '2030-01-15'
    assert read(root, 'tracks/demo/seen_jobs.json') == before
    assert all(j['closed_on'] is None for j in read(root, 'shared/ranked_jobs/demo.json')['jobs'])
    board.update(status=200, jobs=[1])
    result, log = run('2030-01-17')
    assert result.returncode == 0, log
    jobs = {j['title']: j for j in read(root, 'shared/ranked_jobs/demo.json')['jobs']}
    assert jobs['Cryptography Engineer 1']['closed_on'] is None
    assert jobs['Cryptography Engineer 2']['closed_on'] == '2030-01-17'
    assert read(root, 'tracks/demo/source_state.json')['sources']['local']['last_checked'] == '2030-01-17'
    assert len(read(root, 'tracks/demo/seen_jobs.json')['jobs']) == 2


def test_empty_run_renders_and_delivers_empty_digest(workflow):
    root, board, run = workflow
    board['jobs'] = []
    result, log = run()
    assert result.returncode == 0, log
    assert read(root, 'artifacts/digests/demo/2030-01-15.json')['runs'][0]['top_matches'] == []
    assert read(root, 'tracks/demo/seen_jobs.json')['jobs'] == []
    assert (root / 'graph/pages/Demo Job Digest 2030-01-15.md').exists()


@pytest.mark.parametrize('behavior', [
    'malformed', 'invalid_schema', 'missing', 'failure', 'timeout', 'stale_receipt', 'unknown_id', 'missing_receipt',
])
def test_unsuccessful_agent_output_cannot_advance_state_or_deliver(workflow, behavior):
    root, board, run = workflow
    result, log = run(behavior=behavior)
    assert result.returncode != 0, log
    if behavior == 'timeout':
        assert (root / 'agent-child-started').exists(), log
        assert result.returncode == 124, log
    assert not (root / 'tracks/demo/source_state.json').exists(), log
    assert not (root / 'tracks/demo/seen_jobs.json').exists()
    assert not (root / 'tracks/demo/candidate_review_history.json').exists()
    assert not (root / 'artifacts/digests/demo/2030-01-15.json').exists()
    assert not (root / 'graph/pages').exists()
    result, log = run(deliver=False)
    assert result.returncode == 0, log
    assert [c['title'] for c in review_input(root)['sources'][0]['candidates']] == [
        'Cryptography Engineer 1', 'Cryptography Engineer 2',
    ]
    digest = read(root, 'artifacts/digests/demo/2030-01-15.json')
    assert len(digest['runs']) == 1
    assert len(digest['runs'][0]['top_matches']) == 2


def test_review_input_keeps_coverage_and_sends_only_new_or_changed_bodies(workflow):
    root, board, run = workflow
    board['jobs'] = list(range(1, 101))
    result, log = run(behavior='no_reports', deliver=False)
    assert result.returncode == 0, log
    first = review_input(root)
    assert len(first['sources'][0]['candidates']) == 100
    assert all(c['description'] for c in first['sources'][0]['candidates'])
    assert read(root, 'tracks/demo/seen_jobs.json')['jobs'] == []

    result, log = run('2030-01-16', behavior='no_reports', deliver=False)
    assert result.returncode == 0, log
    second = review_input(root)
    assert second['run_id'] != first['run_id']
    assert second['review_counts'] == {'queued': 0, 'skipped': 100, 'deferred': 0}
    assert second['sources'][0]['candidates'] == []
    full = read(root, 'artifacts/discovery/demo/2030-01-16.json')['sources'][0]
    assert len(full['candidates']) == 100
    assert {k: v for k, v in second['sources'][0].items() if k not in {'candidates', 'review_counts'}} == {
        k: v for k, v in full.items() if k != 'candidates'
    }
    note = read(root, 'artifacts/digests/demo/2030-01-16.json')['runs'][0]['source_notes'][0]
    assert note['note'] == '100 original matches'

    board['jobs'] += [101, 102]
    board['descriptions']['/jobs/3'] = 'Build cryptography libraries in Rust and Go.'
    result, log = run('2030-01-17', behavior='no_reports', deliver=False)
    assert result.returncode == 0, log
    third = review_input(root)
    assert third['review_counts'] == {'queued': 3, 'skipped': 99, 'deferred': 0}
    assert [c['title'] for c in third['sources'][0]['candidates']] == [
        f'Cryptography Engineer {index}' for index in (3, 101, 102)
    ]
    assert 'Rust and Go' in third['sources'][0]['candidates'][0]['description']


def test_partial_review_deferral_and_same_day_receipt_without_digest_update(workflow):
    root, board, run = workflow
    board['jobs'] = [1, 2, 3]
    board['descriptions']['/jobs/2'] = ''
    result, log = run(behavior='partial', deliver=False)
    assert result.returncode == 0, log
    digest = root / 'artifacts/digests/demo/2030-01-15.json'
    first = digest.read_bytes()

    result, log = run(behavior='unknown_id', deliver=False)
    assert result.returncode != 0, log
    assert digest.read_bytes() == first

    # A subsequent attempt handles the remaining candidates, but neither is
    # reportable on this attempt. The earlier digest stays byte-for-byte intact.
    result, log = run(behavior='no_reports', deliver=False)
    assert result.returncode == 0, log
    assert digest.read_bytes() == first
    assert [c['title'] for c in review_input(root)['sources'][0]['candidates']] == [
        'Cryptography Engineer 2', 'Cryptography Engineer 3',
    ]
    result, log = run(deliver=False)
    assert result.returncode == 0, log
    assert review_input(root)['review_counts'] == {'queued': 0, 'skipped': 2, 'deferred': 1}
    assert digest.read_bytes() == first

    board['descriptions'].update({'/jobs/1': 'Now using Go.', '/jobs/2': 'Build cryptography services.'})
    result, log = run('2030-01-16', deliver=False)
    assert result.returncode == 0, log
    assert [c['title'] for c in review_input(root)['sources'][0]['candidates']] == [
        'Cryptography Engineer 1', 'Cryptography Engineer 2',
    ]
    roles = read(root, 'artifacts/digests/demo/2030-01-16.json')['runs'][0]['top_matches']
    assert [role['title'] for role in roles] == ['Cryptography Engineer 2']


def test_delivery_failure_preserves_local_results_and_retry_is_idempotent(workflow):
    root, board, run = workflow
    bad_graph = root / 'not-a-directory'
    bad_graph.write_text('occupied')
    result, log = run(graph=bad_graph)
    assert result.returncode != 0, log
    assert len(read(root, 'tracks/demo/seen_jobs.json')['jobs']) == 2
    assert (root / 'tracks/demo/digests/2030-01-15.md').exists()
    result, log = run()
    assert result.returncode == 0, log
    assert len(read(root, 'tracks/demo/seen_jobs.json')['jobs']) == 2


@pytest.mark.parametrize('behavior', ['replace_history', 'rewrite_history'])
def test_same_day_draft_cannot_replace_previously_reported_roles(workflow, behavior):
    root, board, run = workflow
    board['jobs'] = [1]
    result, log = run(deliver=False)
    assert result.returncode == 0, log
    digest = root / 'artifacts/digests/demo/2030-01-15.json'
    history = root / 'tracks/demo/candidate_review_history.json'
    original_digest = digest.read_bytes()
    original_history = history.read_bytes()

    board['jobs'].append(2)
    result, log = run(behavior=behavior, deliver=False)
    assert result.returncode != 0, log
    assert digest.read_bytes() == original_digest
    assert history.read_bytes() == original_history

    result, log = run(deliver=False)
    assert result.returncode == 0, log
    assert [c['title'] for c in review_input(root)['sources'][0]['candidates']] == ['Cryptography Engineer 2']
    initial, update = json.loads(digest.read_bytes())['runs']
    assert initial == json.loads(original_digest)['runs'][0]
    assert update['kind'] == 'update'
    assert [role['title'] for role in update['top_matches']] == ['Cryptography Engineer 2']


def test_retry_cannot_reuse_stale_agent_output(workflow):
    root, board, run = workflow
    assert run()[0].returncode == 0
    previous = (root / 'tracks/demo/seen_jobs.json').read_bytes()
    result, log = run(behavior='missing')
    assert result.returncode != 0, log
    assert (root / 'tracks/demo/seen_jobs.json').read_bytes() == previous


def test_discovery_fallback_leaves_review_history_untouched(workflow):
    root, board, run = workflow
    result, log = run(behavior='no_reports', deliver=False)
    assert result.returncode == 0, log
    history_path = root / 'tracks/demo/candidate_review_history.json'
    previous = history_path.read_bytes()
    (root / 'scripts/discover_jobs.py').write_text('raise SystemExit(1)\n')

    # Exercise the same-day fallback to the existing discovery snapshot.
    result, log = run(deliver=False)
    assert result.returncode == 0, log
    assert 'will fall back to live discovery as needed' in log
    assert len(list((root / 'artifacts/reviews/demo').glob('*.receipt.json'))) == 1
    assert history_path.read_bytes() == previous


def test_standalone_workflow_smoke_uses_same_agent_boundary(repo_root, tmp_path, run_cmd):
    result = run_cmd('bash', str(repo_root / 'scripts/test_track_workflow.sh'), cwd=repo_root,
        env=os.environ | {'TEST_WORKFLOW_DIR': str(tmp_path / 'smoke'), 'JOB_AGENT_TODAY': '2030-01-15',
                          'JOB_AGENT_JOURNAL_DATE': '2030_01_15', 'JOB_AGENT_CAFFEINATED': '1'})
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / 'smoke/root'
    assert read(root, 'tracks/test_workflow/seen_jobs.json')['jobs'][0]['title'] == 'Cryptography Advisor'
