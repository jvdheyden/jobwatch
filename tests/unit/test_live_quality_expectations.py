import json
import sys

import pytest

import eval_source_quality
from source_quality import validate_source_coverage


def source(status='complete'):
    return {'source': 'Example', 'source_url': 'https://jobs.example.com', 'discovery_mode': 'greenhouse_api',
            'status': status, 'enumerated_jobs': 20, 'candidates': []}


@pytest.mark.parametrize('status', ['failed', 'partial'])
def test_successful_transport_does_not_override_incomplete_execution(status):
    result = validate_source_coverage(source(status))
    assert any(c['name'] == 'execution_complete' and c['status'] == 'fail' for c in result['checks'])


def test_nonempty_board_with_zero_matches_fails_independent_recall_floor():
    result = validate_source_coverage(source(), minimum_candidates=1, minimum_enumerated=30)
    checks = {c['name']: c for c in result['checks']}
    assert checks['candidate_recall']['status'] == 'fail'
    assert checks['enumeration_recall']['status'] == 'fail'
    assert 'retrieval constraints' in checks['candidate_recall']['details']


def test_stale_canary_review_is_inconclusive_without_availability_evidence(tmp_path, monkeypatch):
    artifact = tmp_path / 'discovery.json'
    artifact.write_text(json.dumps({'sources': [source()]}))
    output = tmp_path / 'eval.json'
    monkeypatch.setenv('JOB_AGENT_ROOT', str(tmp_path))
    monkeypatch.setattr(sys, 'argv', ['eval_source_quality.py', '--track', 'demo', '--source', 'Example', '--today', '2030-02-01',
        '--artifact-path', str(artifact), '--output', str(output), '--reviewer', 'off',
        '--canary-title', 'Closed role', '--canary-expires-on', '2030-01-31'])
    eval_source_quality.main()
    payload = json.loads(output.read_text())
    assert payload['canary_review']['status'] == 'review_due'
    assert payload['verification'] == 'inconclusive'
    assert payload['canary']['title'] == ''
    assert not any(c['name'] == 'canary_present' and c['status'] == 'fail' for c in payload['deterministic']['checks'])


def test_unexpired_missing_canary_remains_a_failure():
    result = validate_source_coverage(source(), canary_title='Known current vacancy')
    assert any(c['name'] == 'canary_present' and c['status'] == 'fail' for c in result['checks'])


def test_legacy_canaries_load_as_review_needed_without_erasing_evidence():
    from source_evidence import stored_canaries
    original = {'title': 'Reviewed vacancy', 'url': 'https://jobs.example.com/jobs/1', 'expires_on': '2030-01-31'}
    integration = {'canary': dict(original)}
    loaded = stored_canaries(integration, 'example')
    assert loaded[0]['url'] == original['url']
    assert loaded[0]['availability'] == 'unknown'
    assert loaded[0]['provenance'] == 'legacy'
    assert integration['canary'] == original


@pytest.mark.parametrize(('floor', 'status'), [(0.75, 'fail'), (0.3, 'pass')])
def test_one_good_description_does_not_hide_widespread_loss(floor, status):
    coverage = source()
    coverage['candidates'] = [
        {'employer': 'Example', 'title': f'Security Engineer {n}', 'url': f'https://jobs.example.com/jobs/{n}',
         'source_url': coverage['source_url'], 'description': description}
        for n, description in enumerate([
            "Responsibilities: build secure software. Requirements: applied cryptography experience.",
            'About us. Competitive salary and benefits.',
            '',
        ])
    ]
    result = validate_source_coverage(coverage, minimum_detail_fraction=floor,
        raw_text_fetcher=lambda *_: pytest.fail('Stored role detail needs no fetch'))
    check = next(c for c in result['checks'] if c['name'] == 'detail_coverage')
    assert check['status'] == status
    assert '1/3' in check['details']


@pytest.mark.parametrize('status', ['failed', 'partial'])
def test_failed_canary_refresh_preserves_reviewed_state(tmp_path, monkeypatch, status):
    import subprocess
    import update_source_canary
    track = tmp_path / 'tracks/demo'
    track.mkdir(parents=True)
    (track / 'sources.json').write_text(json.dumps({'schema_version': 1, 'track': 'demo', 'track_terms': ['security'],
        'sources': [{'id': 'example', 'name': 'Example', 'url': 'https://jobs.example.com', 'discovery_mode': 'html', 'cadence_group': 'every_run'}]}))
    state = track / 'source_state.json'
    original = json.dumps({'schema_version': 1, 'track': 'demo', 'sources': {'example': {'last_checked': '2030-01-01',
        'integration': {'canary': {'title': 'Reviewed vacancy', 'url': 'https://jobs.example.com/jobs/1'}}}}})
    state.write_text(original)
    def discover(root, track, name, today, output):
        output.parent.mkdir(parents=True)
        output.write_text(json.dumps({'sources': [{'source': name, 'status': status, 'candidates': []}]}))
        return subprocess.CompletedProcess([], 0, '', '')
    monkeypatch.setattr(update_source_canary, 'run_discovery', discover)
    ok, result = update_source_canary.refresh_canary(root=tmp_path, track='demo', source_query='Example', today='2030-01-02')
    assert not ok
    assert result['status'] == 'incomplete_discovery'
    assert state.read_text() == original
