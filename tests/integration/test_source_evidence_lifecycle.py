"""Independent expected postings exercise the real setup/curation/evaluation boundary."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import curate_sources
import eval_source_quality
import integrate_next_source
import probe_career_source
import scaffold_track
import setup_contracts
import source_evidence
import update_source_canary
from source_config import load_source_state, mutate_source_state
from source_quality import validate_source_coverage

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures/setup'
TODAY = '2026-11-17'
URL = 'https://jobs.example.test/jobs/42'


def canary(**changes):
    return source_evidence.normalize_canaries([dict(id='desired_role', source_id='example_labs', title='Privacy Engineer', url=URL,
        provenance='user_supplied', availability='live', scope='in_scope', checked_on=TODAY, evidence_url=URL,
        evidence_note='User independently found this open official posting.', **changes)])[0]


def source():
    return {'source': 'Example Labs', 'source_id': 'example_labs', 'source_url': 'https://jobs.example.test/careers',
        'status': 'complete', 'discovery_mode': 'greenhouse_api', 'enumerated_jobs': 15, 'matched_jobs': 1,
        'search_terms_tried': ['privacy'], 'candidates': [{'employer': 'Example Labs', 'title': 'Privacy Engineer',
        'url': 'https://jobs.example.test/jobs/99', 'source_url': 'https://jobs.example.test/careers', 'location': 'Berlin',
        'description': 'Responsibilities: build privacy protocols. Requirements: experience in applied cryptography.'}]}


def selected_setup():
    setup = setup_contracts.normalize_setup(json.loads((FIXTURES / 'setup.json').read_text()))
    pack = json.loads((FIXTURES / 'source-pack.json').read_text())
    pack['input_hash'] = setup_contracts.artifact_hash(setup)
    result = setup_contracts.apply_source_selection(setup, pack)
    result['canaries'] = [canary()]
    return setup_contracts.normalize_setup(result)


def configure(tmp_path, entry='existing'):
    setup = selected_setup()
    directory = tmp_path / 'tracks/applied_crypto'
    if entry == 'setup':
        (tmp_path / 'shared').mkdir()
        shutil.copytree(Path(__file__).resolve().parents[2] / 'shared/templates', tmp_path / 'shared/templates')
        setup_path = tmp_path / 'setup.json'
        setup_contracts.write_setup(setup_path, setup)
        scaffold_track.scaffold_track(setup_path, root=tmp_path)
    else:
        directory.mkdir(parents=True)
        (directory / 'sources.json').write_text(json.dumps({'schema_version': 1, 'track': 'applied_crypto',
            'track_terms': ['privacy'], 'sources': []}))
        curate_sources.register(tmp_path, 'applied_crypto', setup=setup)
        # Repeated source registration must be safe after interrupted multi-file writes.
        curate_sources.register(tmp_path, 'applied_crypto', setup=setup)
    return directory


def evaluate(tmp_path, monkeypatch, coverage, *, today=TODAY):
    artifact = tmp_path / 'discovery.json'
    artifact.write_text(json.dumps({'sources': [coverage]}))
    output = tmp_path / 'quality.json'
    monkeypatch.setenv('JOB_AGENT_ROOT', str(tmp_path))
    monkeypatch.setattr(sys, 'argv', ['eval_source_quality.py', '--track', 'applied_crypto', '--source', 'Example Labs',
        '--today', today, '--artifact-path', str(artifact), '--output', str(output), '--reviewer', 'off'])
    status = eval_source_quality.main()
    return status, json.loads(output.read_text())


@pytest.mark.parametrize('entry', ['setup', 'existing'])
def test_complete_scraper_missing_live_canary_fails_from_either_onboarding_path(tmp_path, monkeypatch, entry):
    configure(tmp_path, entry)
    status, result = evaluate(tmp_path, monkeypatch, source())
    assert status == 1
    assert result['final_status'] == 'integration_needed'
    assert result['verification'] == 'failed'
    assert result['canaries'][0]['url'] == URL
    assert result['integration_ticket']['canary_results'][0]['status'] == 'fail'
    coverage = source()
    coverage['candidates'][0]['url'] = URL
    status, result = evaluate(tmp_path, monkeypatch, coverage)
    assert status == 0
    assert result['quality_level'] == 'independently_verified'


@pytest.mark.parametrize('observation', ['live', 'unknown', 'expired'])
def test_missing_posting_is_checked_independently_and_evidence_is_preserved(tmp_path, monkeypatch, observation):
    directory = configure(tmp_path)
    references = {'reference_jobs': [{'id': 'calibration', 'source_id': 'example_labs', 'url': URL,
        'title': 'Privacy Engineer', 'relevance': 'Useful example after expiration'}]}
    update_source_canary.register_evidence(root=tmp_path, track='applied_crypto', source_query='Example Labs', payload=references)
    def discover(root, track, name, today, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({'sources': [source()]}))
        return subprocess.CompletedProcess([], 0, '', '')
    monkeypatch.setattr(update_source_canary, 'run_discovery', discover)
    def fetch(url, timeout):
        if observation == 'unknown':
            return '', url, 403, ['Access blocked']
        if observation == 'expired':
            return '', url, 410, []
        return '<script type="application/ld+json">' + json.dumps({'@type': 'JobPosting', 'url': URL,
            'title': 'Privacy Engineer', 'description': 'Build privacy protocols.'}) + '</script>', url, 200, []
    monkeypatch.setattr(probe_career_source, 'fetch_http', fetch)
    monkeypatch.setattr(update_source_canary, 'probe', lambda *_a, **_k: {'candidate_canaries': []})
    before = load_source_state(directory / 'source_state.json', 'applied_crypto')['example_labs']['integration']['canaries'][0]
    ok, result = update_source_canary.refresh_canary(root=tmp_path, track='applied_crypto', source_query='Example Labs', today=TODAY)
    integration = load_source_state(directory / 'source_state.json', 'applied_crypto')['example_labs']['integration']
    if observation == 'expired':
        assert ok
        assert integration['canary_history'][0]['url'] == URL
        assert integration['canary_history'][0]['reason'] == 'confirmed_expiration'
        assert integration['canaries'][0]['url'].endswith('/99')
        assert integration['canaries'][0]['provenance'] == 'discovery_output'
    else:
        assert not ok
        assert result['status'] == ('missing_live' if observation == 'live' else 'inconclusive')
        assert integration['canaries'][0]['url'] == URL
        assert 'canary_history' not in integration
        if observation == 'unknown':
            assert integration['canaries'][0] == before
    assert source_evidence.load_references(directory / 'reference_jobs.json', 'applied_crypto')[0]['relevance'] == 'Useful example after expiration'


def test_inconclusive_evaluation_does_not_authorize_provider_changes(tmp_path, monkeypatch):
    directory = configure(tmp_path)
    def age(state):
        c = state['example_labs']['integration']['canaries'][0]
        c['checked_on'], c['expires_on'] = '2026-10-01', '2026-10-15'
    mutate_source_state(directory / 'source_state.json', 'applied_crypto', ['example_labs'], age)
    before = (directory / 'source_state.json').read_bytes()
    monkeypatch.setattr(probe_career_source, 'fetch_http', lambda url, timeout: ('', url, 0, ['Timeout']))
    status, result = evaluate(tmp_path, monkeypatch, source())
    assert status == 1
    assert result['final_status'] == 'inconclusive'
    assert result['integration_ticket'] is None
    assert result['canaries'][0]['prior_evidence']['url'] == URL
    assert (directory / 'source_state.json').read_bytes() == before


@pytest.mark.parametrize('present', [False, True], ids=['missing', 'present'])
@pytest.mark.parametrize('review_path', ['manual', 'refresh'])
def test_latest_unknown_review_defers_evaluation_until_conclusive_review(tmp_path, monkeypatch, present, review_path):
    directory = configure(tmp_path)
    state_path = directory / 'source_state.json'
    prior = load_source_state(state_path, 'applied_crypto')['example_labs']['integration']['canaries'][0]
    monkeypatch.setattr(probe_career_source, 'fetch_http', lambda url, timeout: ('', url, 403, ['Access blocked']))
    if review_path == 'manual':
        update_source_canary.review_canary(root=tmp_path, track='applied_crypto', source_query='example_labs', evidence_id='desired_role',
            observation={'availability': 'unknown', 'scope': 'unknown', 'evidence_url': URL, 'evidence_note': 'Official page unavailable.'}, today=TODAY)
    else:
        def discover(root, track, name, today, output):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({'sources': [source()]}))
            return subprocess.CompletedProcess([], 0, '', '')
        monkeypatch.setattr(update_source_canary, 'run_discovery', discover)
        ok, review = update_source_canary.refresh_canary(root=tmp_path, track='applied_crypto', source_query='example_labs', today=TODAY)
        assert not ok and review['status'] == 'inconclusive'

    before = state_path.read_bytes()
    integration = load_source_state(state_path, 'applied_crypto')['example_labs']['integration']
    assert integration['canaries'] == [prior]
    latest = integration['canary_checks']['desired_role']
    coverage = source()
    if present:
        coverage['candidates'][0]['url'] = URL
    status, result = evaluate(tmp_path, monkeypatch, coverage)
    assert status == 1
    assert result['final_status'] == 'inconclusive'
    assert result['verification'] == 'inconclusive'
    assert result['quality_level'] == 'basic_support'
    assert result['integration_ticket'] is None
    assert result['canaries'][0]['availability'] == 'unknown'
    assert result['canaries'][0]['scope'] == ('unknown' if review_path == 'manual' else 'in_scope')
    assert result['canaries'][0]['evidence_note'] == latest['evidence_note']
    assert result['canaries'][0]['prior_evidence'] == prior
    assert state_path.read_bytes() == before

    if review_path == 'manual':
        update_source_canary.review_canary(root=tmp_path, track='applied_crypto', source_query='example_labs', evidence_id='desired_role',
            observation={'availability': 'live', 'evidence_url': URL, 'evidence_note': 'Official page open again.'}, today=TODAY)
        status, result = evaluate(tmp_path, monkeypatch, coverage)
        assert status == 1
        assert result['verification'] == 'inconclusive'
        assert result['canaries'][0]['availability'] == 'live'
        assert result['canaries'][0]['scope'] == 'unknown'
        assert result['integration_ticket'] is None

    update_source_canary.review_canary(root=tmp_path, track='applied_crypto', source_query='example_labs', evidence_id='desired_role',
        observation={'availability': 'live', 'scope': 'in_scope', 'evidence_url': URL, 'evidence_note': 'Official page confirmed open again.'}, today=TODAY)
    status, result = evaluate(tmp_path, monkeypatch, coverage)
    assert status == (0 if present else 1)
    assert result['verification'] == ('independently_verified' if present else 'failed')
    assert result['final_status'] == ('pass' if present else 'integration_needed')
    assert result['canaries'][0]['provenance'] == 'user_supplied'


@pytest.mark.parametrize('present', [False, True], ids=['missing', 'present'])
def test_live_availability_refresh_preserves_unknown_scope(tmp_path, monkeypatch, present):
    directory = configure(tmp_path)
    update_source_canary.review_canary(
        root=tmp_path, track='applied_crypto', source_query='example_labs', evidence_id='desired_role', today=TODAY,
        observation={'availability': 'unknown', 'scope': 'unknown', 'evidence_url': URL,
                     'evidence_note': 'Official page unavailable; scope unclear.'},
    )
    coverage = source()
    if present:
        coverage['candidates'][0]['url'] = URL

    def discover(root, track, name, today, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({'sources': [coverage]}))
        return subprocess.CompletedProcess([], 0, '', '')

    body = '<script type="application/ld+json">' + json.dumps({'@type': 'JobPosting', 'url': URL,
        'title': 'Privacy Engineer', 'description': 'Build privacy protocols.'}) + '</script>'
    monkeypatch.setattr(update_source_canary, 'run_discovery', discover)
    monkeypatch.setattr(probe_career_source, 'fetch_http', lambda url, timeout: (body, url, 200, []))
    ok, refresh = update_source_canary.refresh_canary(
        root=tmp_path, track='applied_crypto', source_query='example_labs', today=TODAY,
    )
    status, result = evaluate(tmp_path, monkeypatch, coverage)
    assert result['verification'] == 'inconclusive'
    assert status == 1
    assert result['final_status'] == 'inconclusive'
    assert result['integration_ticket'] is None
    assert result['canaries'][0]['availability'] == 'live'
    assert result['canaries'][0]['scope'] == 'unknown'
    assert result['canaries'][0]['provenance'] == 'user_supplied'
    assert not ok
    assert refresh['status'] == 'inconclusive'
    assert refresh['missing_live_ids'] == []
    assert refresh['checks']['desired_role']['availability'] == 'live'
    integration = load_source_state(directory / 'source_state.json', 'applied_crypto')['example_labs']['integration']
    assert integration['verification'] == 'inconclusive'
    assert integration['canary_checks']['desired_role']['scope'] == 'unknown'


def test_refresh_preserves_scope_review_recorded_during_discovery(tmp_path, monkeypatch):
    directory = configure(tmp_path)

    def discover(root, track, name, today, output):
        update_source_canary.review_canary(
            root=root, track=track, source_query=name, evidence_id='desired_role', today=today,
            observation={'availability': 'unknown', 'scope': 'unknown', 'evidence_url': URL,
                         'evidence_note': 'Scope review submitted during discovery.'},
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({'sources': [source()]}))
        return subprocess.CompletedProcess([], 0, '', '')

    monkeypatch.setattr(update_source_canary, 'run_discovery', discover)
    monkeypatch.setattr(probe_career_source, 'fetch_http', lambda url, timeout: ('', url, 403, ['Access blocked']))
    with pytest.raises(source_evidence.EvidenceError, match='canaries changed during refresh'):
        update_source_canary.refresh_canary(root=tmp_path, track='applied_crypto', source_query='example_labs', today=TODAY)

    integration = load_source_state(directory / 'source_state.json', 'applied_crypto')['example_labs']['integration']
    assert integration['canaries'] == [canary()]
    assert integration['canary_checks']['desired_role']['scope'] == 'unknown'


@pytest.mark.parametrize('observation', ['live', 'unknown'])
def test_older_unknown_review_requires_fresh_independent_evidence(tmp_path, monkeypatch, observation):
    directory = configure(tmp_path)
    update_source_canary.review_canary(root=tmp_path, track='applied_crypto', source_query='example_labs', evidence_id='desired_role',
        observation={'availability': 'unknown', 'evidence_url': URL, 'evidence_note': 'Official page unavailable.'}, today=TODAY)
    before = (directory / 'source_state.json').read_bytes()
    body = '<script type="application/ld+json">' + json.dumps({'@type': 'JobPosting', 'url': URL,
        'title': 'Privacy Engineer', 'description': 'Build privacy protocols.'}) + '</script>'
    monkeypatch.setattr(probe_career_source, 'fetch_http', lambda url, timeout:
        (body, url, 200, []) if observation == 'live' else ('', url, 403, ['Access blocked']))
    coverage = source()
    coverage['candidates'][0]['url'] = URL
    status, result = evaluate(tmp_path, monkeypatch, coverage, today='2026-11-18')
    assert status == (0 if observation == 'live' else 1)
    assert result['verification'] == ('independently_verified' if observation == 'live' else 'inconclusive')
    assert result['canaries'][0]['availability'] == observation
    assert result['canaries'][0]['checked_on'] == '2026-11-18'
    assert result['canaries'][0]['prior_evidence']['checked_on'] == TODAY
    assert result['canaries'][0]['provenance'] == 'user_supplied'
    assert result['integration_ticket'] is None
    assert (directory / 'source_state.json').read_bytes() == before


def test_multiple_canaries_require_every_applicable_identity():
    evidence = [canary(), dict(canary(), id='second_role', url='https://jobs.example.test/jobs/99')]
    result = validate_source_coverage(source(), canaries=evidence)
    assert [r['status'] for r in result['canary_results']] == ['fail', 'pass']
    assert result['verification'] == 'failed'


@pytest.mark.parametrize('provenance', ['legacy', 'discovery_output'])
def test_regression_canaries_do_not_certify_independent_coverage(provenance):
    evidence = dict(canary(), url='https://jobs.example.test/jobs/99', provenance=provenance)
    result = validate_source_coverage(source(), canaries=[evidence])
    assert result['verification'] == 'regression_only'
    assert result['quality_level'] == 'basic_support'


def test_available_posting_filtered_by_track_rule_has_specific_diagnosis():
    coverage = source()
    coverage['filter_rejections'] = [{'url': URL, 'title': 'Privacy Engineer', 'rule_id': 'too_narrow'}]
    result = validate_source_coverage(coverage, canaries=[canary()])
    assert result['canary_results'][0]['diagnosis'] == 'track_match_rules'


def test_integration_state_write_preserves_concurrent_evidence_and_cadence(tmp_path, monkeypatch):
    directory = configure(tmp_path)
    config = json.loads((directory / 'sources.json').read_text())
    old = load_source_state(directory / 'source_state.json', 'applied_crypto')
    old['example_labs']['integration']['status'] = 'pass'
    old['example_labs']['integration']['verification'] = 'independently_verified'
    def concurrent(state):
        state['example_labs']['last_checked'] = TODAY
        state['example_labs']['integration']['canaries'].append(dict(canary(), id='new_evidence', url=URL + '1'))
        state['another_source'] = {'last_checked': TODAY}
    mutate_source_state(directory / 'source_state.json', 'applied_crypto', ['example_labs', 'another_source'], concurrent)
    monkeypatch.setattr(integrate_next_source, 'ROOT', tmp_path)
    integrate_next_source.write_state('applied_crypto', config, old, source_id='example_labs')
    state = load_source_state(directory / 'source_state.json', 'applied_crypto')
    assert state['example_labs']['last_checked'] == TODAY
    assert len(state['example_labs']['integration']['canaries']) == 2
    assert state['example_labs']['integration']['status'] == 'pending'
    assert 'another_source' in state


def test_explicit_registration_reaches_evaluator_without_overwriting_other_sources(tmp_path, monkeypatch):
    directory = configure(tmp_path)
    mutate_source_state(directory / 'source_state.json', 'applied_crypto', ['example_labs', 'unrelated'],
        lambda state: state.update(unrelated={'last_checked': TODAY, 'custom': 'preserve'}))
    extra = dict(canary(), id='new_example', url='https://jobs.example.test/jobs/77')
    update_source_canary.register_evidence(root=tmp_path, track='applied_crypto', source_query='example_labs', payload={'canaries': [extra]})
    _, result = evaluate(tmp_path, monkeypatch, source())
    assert {c['url'] for c in result['canaries']} == {URL, 'https://jobs.example.test/jobs/77'}
    state = load_source_state(directory / 'source_state.json', 'applied_crypto')
    assert state['unrelated'] == {'last_checked': TODAY, 'custom': 'preserve'}


def test_narrow_reverification_queues_only_affected_sources(tmp_path):
    directory = configure(tmp_path)
    config = json.loads((directory / 'sources.json').read_text())
    config['sources'].append(dict(config['sources'][0], id='unrelated', name='Unrelated', url='https://unrelated.test/careers'))
    (directory / 'sources.json').write_text(json.dumps(config))
    def mark_passed(state):
        state['example_labs']['integration'].update(status='pass', verification='independently_verified', last_attempted=TODAY)
        state['unrelated'] = {'last_checked': TODAY, 'integration': {'status': 'pass'}}
    mutate_source_state(directory / 'source_state.json', 'applied_crypto', ['example_labs', 'unrelated'], mark_passed)
    before = load_source_state(directory / 'source_state.json', 'applied_crypto')
    result = curate_sources.queue_verification(tmp_path, 'applied_crypto', ['Example Labs'])
    after = load_source_state(directory / 'source_state.json', 'applied_crypto')
    assert result['source_ids'] == ['example_labs']
    assert after['example_labs']['integration']['status'] == 'pending'
    assert 'last_attempted' not in after['example_labs']['integration']
    assert after['unrelated'] == before['unrelated']


def test_no_canary_source_has_basic_support_without_claiming_independent_coverage():
    result = validate_source_coverage(source())
    assert result['quality_level'] == 'basic_support'
    assert result['verification'] == 'unverified'


def test_reviewed_expiration_archives_but_inconclusive_review_preserves_evidence(tmp_path):
    directory = configure(tmp_path)
    prior = load_source_state(directory / 'source_state.json', 'applied_crypto')['example_labs']['integration']['canaries']
    update_source_canary.review_canary(root=tmp_path, track='applied_crypto', source_query='example_labs', evidence_id='desired_role',
        observation={'availability': 'unknown', 'evidence_url': URL, 'evidence_note': 'Official page unavailable.'}, today=TODAY)
    state = load_source_state(directory / 'source_state.json', 'applied_crypto')['example_labs']['integration']
    assert state['canaries'] == prior
    assert state['canary_checks']['desired_role']['availability'] == 'unknown'
    update_source_canary.review_canary(root=tmp_path, track='applied_crypto', source_query='example_labs', evidence_id='desired_role',
        observation={'availability': 'expired', 'evidence_url': URL, 'evidence_note': 'Official page explicitly says applications closed.'}, today=TODAY)
    state = load_source_state(directory / 'source_state.json', 'applied_crypto')['example_labs']['integration']
    assert state['canaries'] == []
    assert state['canary_history'][0]['url'] == URL


def test_completed_integration_clears_stale_result_fields_but_preserves_curation_hints(tmp_path, monkeypatch):
    directory = configure(tmp_path)
    def queued(state):
        state['example_labs']['integration'].update(next_action='old ticket', last_note='stale', priority=12)
    mutate_source_state(directory / 'source_state.json', 'applied_crypto', ['example_labs'], queued)
    snapshot = load_source_state(directory / 'source_state.json', 'applied_crypto')
    integrate_next_source.update_integration_state(snapshot['example_labs'], today=TODAY, status='pass')
    mutate_source_state(directory / 'source_state.json', 'applied_crypto', ['example_labs'],
        lambda state: state['example_labs']['integration'].update(priority=30))
    monkeypatch.setattr(integrate_next_source, 'ROOT', tmp_path)
    integrate_next_source.write_state('applied_crypto', json.loads((directory / 'sources.json').read_text()), snapshot, source_id='example_labs')
    integration = load_source_state(directory / 'source_state.json', 'applied_crypto')['example_labs']['integration']
    assert integration['status'] == 'pass'
    assert integration['priority'] == 30
    assert 'next_action' not in integration and 'last_note' not in integration


def test_missing_canary_already_matching_terms_escalates_past_redundant_tuning(tmp_path, monkeypatch):
    configure(tmp_path)
    _, result = evaluate(tmp_path, monkeypatch, source())
    assert result['integration_ticket']['suggested_strategy'] == 'dedicated_provider_logic'
    coverage = source()
    coverage['search_terms_tried'] = ['blockchain']
    _, result = evaluate(tmp_path, monkeypatch, coverage)
    assert result['integration_ticket']['suggested_strategy'] == 'config_terms_append'
    coverage['search_terms_tried'] = ['privacy']
    coverage['filters'] = {'location': ['US']}
    _, result = evaluate(tmp_path, monkeypatch, coverage)
    assert result['integration_ticket']['suggested_strategy'] == 'config_native_filters'


def test_registration_retry_recovers_queue_after_configuration_commit(tmp_path):
    directory = configure(tmp_path)
    (directory / 'source_state.json').unlink()  # Interrupted between file commits.
    curate_sources.register(tmp_path, 'applied_crypto', setup=dict(selected_setup(), canaries=[]))
    state = load_source_state(directory / 'source_state.json', 'applied_crypto')
    assert state['example_labs']['integration']['status'] == 'pending'
