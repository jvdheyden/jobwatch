"""Persist successive runs through the actual state and overview components."""
import copy
import json
from pathlib import Path
import sys

import pytest

import source_config
import render_digest
import update_ranked_overview
import update_seen_jobs
import update_source_state


def test_partial_failure_and_authoritative_recovery(tmp_path, load_json_fixture, monkeypatch):
    track = tmp_path / 'tracks/core_crypto'
    track.mkdir(parents=True)
    (track / 'sources.json').write_text(json.dumps({'schema_version': 1, 'track': 'core_crypto', 'track_terms': ['cryptography'],
        'sources': [{'id': 'iacr', 'name': 'IACR Jobs', 'url': 'https://www.iacr.org/jobs/', 'discovery_mode': 'iacr_jobs', 'cadence_group': 'every_run'}]}))
    monkeypatch.setenv('JOB_AGENT_ROOT', str(tmp_path))
    monkeypatch.setattr(update_source_state, 'ROOT', tmp_path)
    template = load_json_fixture('digests/core_crypto_minimal.json')
    first = template['runs'][0]['top_matches'][0]
    second = dict(first, title='Second Cryptographer', listing_url='https://www.iacr.org/jobs/item/4190')
    for stamp, status, roles in [('2030-01-01', 'complete', [first, second]),
                                 ('2030-01-02', 'failed', []), ('2030-01-03', 'partial', []),
                                 ('2030-01-04', 'complete', [first])]:
        discovery = tmp_path / f'artifacts/discovery/core_crypto/{stamp}.json'
        discovery.parent.mkdir(parents=True, exist_ok=True)
        discovery.write_text(json.dumps({'sources': [{'source': 'IACR Jobs', 'source_id': 'iacr', 'status': status,
            'candidates': [{'url': r['listing_url']} for r in roles]}]}))
        payload = copy.deepcopy(template)
        payload['date'] = stamp
        payload['runs'][0]['top_matches'] = roles
        artifact = tmp_path / f'artifacts/digests/core_crypto/{stamp}.json'
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps(payload))
        # Validate the same boundary the real runner validates before persistence.
        markdown = track / f'digests/{stamp}.md'
        monkeypatch.setattr(sys, 'argv', ['render_digest.py', '--track', 'core_crypto', '--date', stamp,
            '--input', str(artifact), '--output', str(markdown), '--latest-output', str(artifact.parent / 'latest.json')])
        assert render_digest.main() == 0
        for _ in range(2):
            monkeypatch.setattr(sys, 'argv', ['update_source_state.py', '--track', 'core_crypto', '--date', stamp])
            assert update_source_state.main() == 0
            monkeypatch.setattr(sys, 'argv', ['update_seen_jobs.py', '--track', 'core_crypto', '--date', stamp])
            assert update_seen_jobs.main() == 0
        _, _, jobs = update_ranked_overview.write_ranked_outputs('core_crypto', root=tmp_path)
        assert len(jobs) == 2
        assert len(json.loads((track / 'seen_jobs.json').read_text())['jobs']) == 2
        state = json.loads((track / 'source_state.json').read_text())['sources']['iacr']
        assert state['last_checked'] == (stamp if status == 'complete' else '2030-01-01')
        closed = {j.title: j.closed_on for j in jobs}
        assert closed[first['title']] is None
        assert closed[second['title']] == ('2030-01-04' if stamp == '2030-01-04' else None)
    # A truncated next discovery artifact is not authoritative closure evidence.
    (discovery.parent / '2030-01-05.json').write_text('{interrupted')
    _, _, jobs = update_ranked_overview.rebuild_track_state('core_crypto', root=tmp_path)
    assert {j.title: j.closed_on for j in jobs} == closed


def test_atomic_state_write_failure_preserves_old_state_and_retry(tmp_path, monkeypatch):
    target = tmp_path / 'state.json'
    source_config.write_json_atomic(target, {'known': ['job-1', 'job-2']})
    previous = target.read_bytes()
    replace = Path.replace
    def interrupted(self, dest):
        if dest == target:
            raise OSError('interrupted before rename')
        return replace(self, dest)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'replace', interrupted)
        with pytest.raises(OSError, match='interrupted'):
            source_config.write_json_atomic(target, {'known': ['job-1']})
    assert target.read_bytes() == previous
    source_config.write_json_atomic(target, {'known': ['job-1']})
    assert json.loads(target.read_text()) == {'known': ['job-1']}


def test_corrupt_seen_state_is_not_replaced(tmp_path, load_json_fixture, monkeypatch):
    monkeypatch.setenv('JOB_AGENT_ROOT', str(tmp_path))
    state = tmp_path / 'tracks/core_crypto/seen_jobs.json'
    state.parent.mkdir(parents=True)
    state.write_text('{corrupted')
    artifact = tmp_path / 'digest.json'
    artifact.write_text(json.dumps(load_json_fixture('digests/core_crypto_minimal.json')))
    monkeypatch.setattr(sys, 'argv', ['update_seen_jobs.py', '--track', 'core_crypto', '--date', '2026-03-29', '--artifact', str(artifact)])
    assert update_seen_jobs.main() == 2
    assert state.read_text() == '{corrupted'
