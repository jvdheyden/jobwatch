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
    board = {'jobs': [1, 2], 'status': 200}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/careers':
                body = ''.join(f'<a href="/jobs/{i}">Cryptography Engineer {i}</a>' for i in board['jobs'])
                status = board['status']
            else:
                body = '<main><h2>Responsibilities</h2>Build cryptography libraries in Rust.</main>'
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


@pytest.mark.parametrize('behavior', ['malformed', 'invalid_schema', 'missing', 'failure', 'timeout'])
def test_unsuccessful_agent_output_cannot_advance_state_or_deliver(workflow, behavior):
    root, board, run = workflow
    result, log = run(behavior=behavior)
    assert result.returncode != 0, log
    if behavior == 'timeout':
        assert (root / 'agent-child-started').exists(), log
        assert result.returncode == 124, log
    assert not (root / 'tracks/demo/source_state.json').exists(), log
    assert not (root / 'tracks/demo/seen_jobs.json').exists()
    assert not (root / 'graph/pages').exists()


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


def test_retry_cannot_reuse_stale_agent_output(workflow):
    root, board, run = workflow
    assert run()[0].returncode == 0
    previous = (root / 'tracks/demo/seen_jobs.json').read_bytes()
    result, log = run(behavior='missing')
    assert result.returncode != 0, log
    assert (root / 'tracks/demo/seen_jobs.json').read_bytes() == previous


def test_standalone_workflow_smoke_uses_same_agent_boundary(repo_root, tmp_path, run_cmd):
    result = run_cmd('bash', str(repo_root / 'scripts/test_track_workflow.sh'), cwd=repo_root,
        env=os.environ | {'TEST_WORKFLOW_DIR': str(tmp_path / 'smoke'), 'JOB_AGENT_TODAY': '2030-01-15',
                          'JOB_AGENT_JOURNAL_DATE': '2030_01_15', 'JOB_AGENT_CAFFEINATED': '1'})
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / 'smoke/root'
    assert read(root, 'tracks/test_workflow/seen_jobs.json')['jobs'][0]['title'] == 'Cryptography Advisor'
