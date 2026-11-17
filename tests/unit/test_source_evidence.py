import json
from pathlib import Path

import pytest

import curate_sources
import setup_contracts as contracts
from source_evidence import EvidenceError, normalize_canaries, normalize_references

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures/setup'


def brief():
    setup = json.loads((FIXTURES / 'setup.json').read_text())
    setup['reference_jobs'] = [{'id': 'interesting', 'title': 'Privacy Engineer',
        'url': 'https://jobs.example.test/jobs/42', 'relevance': 'Hands-on privacy protocols'}]
    return contracts.normalize_setup(setup)


def pack(setup):
    result = json.loads((FIXTURES / 'source-pack.json').read_text())
    result['input_hash'] = contracts.artifact_hash(setup)
    result['reference_associations'] = [{'reference_job_id': 'interesting', 'source_id': 'example_labs', 'reason': 'Official employer board'}]
    result['canaries'] = [{'id': 'posting_42', 'source_id': 'example_labs', 'reference_job_id': 'interesting',
        'title': 'Privacy Engineer', 'url': 'https://jobs.example.test/jobs/42',
        'provenance': 'user_supplied', 'availability': 'live', 'scope': 'in_scope', 'checked_on': '2026-11-17',
        'evidence_url': 'https://jobs.example.test/jobs/42', 'evidence_note': 'Official vacancy is open.'}]
    return result


def test_reference_associations_and_canaries_survive_selection():
    setup = brief()
    selected = contracts.apply_source_selection(setup, pack(setup))
    assert selected['reference_jobs'][0]['url'] == setup['reference_jobs'][0]['url']
    assert selected['reference_jobs'][0]['relevance'] == 'Hands-on privacy protocols'
    assert selected['reference_jobs'][0]['source_id'] == 'example_labs'
    assert selected['canaries'][0]['provenance'] == 'user_supplied'
    assert selected['canaries'][0]['expires_on'] == '2026-12-01'
    assert all(s['source_id'] == 'example_labs' for s in selected['seed_outcomes'])


@pytest.mark.parametrize('mutation', ['missing_association', 'wrong_source', 'wrong_posting', 'claimed_user', 'silent_seed'])
def test_pack_rejects_lost_or_misattributed_evidence(mutation):
    setup = brief()
    value = pack(setup)
    if mutation == 'missing_association':
        value['reference_associations'] = []
    elif mutation == 'wrong_source':
        value['reference_associations'][0]['source_id'] = 'another_source'
    elif mutation == 'wrong_posting':
        value['canaries'][0]['url'] = 'https://jobs.example.test/jobs/99'
    elif mutation == 'claimed_user':
        value['canaries'][0]['reference_job_id'] = None
    else:
        value['seed_outcomes'] = []
    with pytest.raises(contracts.SetupContractError):
        contracts.normalize_source_pack(value, setup)


def test_unresolved_examples_and_seeds_are_explicit_and_preserved():
    setup = brief()
    setup['source_seeds']['employers'].append('Unresolved Employer')
    value = pack(setup)
    value['reference_associations'][0].update(source_id=None, reason='Employer association could not be established.')
    value['canaries'] = []
    selected = contracts.apply_source_selection(setup, value)
    assert selected['reference_jobs'][0]['source_id'] is None
    assert 'could not' in selected['reference_jobs'][0]['association_reason']
    assert any(s['seed'] == 'Unresolved Employer' and s['source_id'] is None and s['reason'] for s in selected['seed_outcomes'])


@pytest.mark.parametrize('field', ['id', 'url', 'scope', 'provenance', 'checked_on'])
def test_evidence_validation_rejects_invalid_identity_or_assertions(field):
    canary = pack(brief())['canaries'][0]
    canary[field] = {'id': '../escape', 'url': 'https://user:password@example.test/42', 'scope': 'probably',
                     'provenance': 'guessed', 'checked_on': ''}[field]
    with pytest.raises(ValueError):
        normalize_canaries([canary])


def test_evidence_contracts_enforce_bounds_and_unknown_fields():
    reference = brief()['reference_jobs'][0]
    with pytest.raises(EvidenceError):
        normalize_references([dict(reference, transcript='private')])
    with pytest.raises(EvidenceError):
        normalize_references([dict(reference, id=f'job_{n}') for n in range(21)])
    canary = pack(brief())['canaries'][0]
    with pytest.raises(EvidenceError):
        normalize_canaries([dict(canary, id=f'job_{n}') for n in range(6)])


def test_existing_portfolio_projection_prevents_duplicate_recommendations(tmp_path):
    setup = brief()
    directory = tmp_path / 'tracks/applied_crypto'
    directory.mkdir(parents=True)
    existing = pack(setup)['recommended_sources'][0]
    existing = {k: v for k, v in existing.items() if k not in {'confidence', 'fit_reason'}}
    config = {'schema_version': 1, 'track': 'applied_crypto', 'track_terms': ['privacy'], 'sources': [existing]}
    (directory / 'sources.json').write_text(json.dumps(config))
    path = tmp_path / 'brief.json'
    contracts.write_setup(path, setup)
    prepared = curate_sources.prepare(tmp_path, 'applied_crypto', path, tmp_path / 'prepared.json')
    assert prepared['existing_sources'][0]['id'] == 'example_labs'
    for change in ({}, {'id': 'renamed'}, {'id': 'renamed', 'url': existing['url'] + '#jobs'},
                   {'id': 'renamed', 'url': 'https://another.example.test/jobs'}):
        value = pack(prepared)
        value['recommended_sources'][0].update(change)
        with pytest.raises(contracts.SetupContractError, match='already configured'):
            contracts.normalize_source_pack(value, prepared)
    value = pack(prepared)
    value['recommended_sources'] = []
    value['recommended_source_ids'] = []
    selected = contracts.apply_source_selection(prepared, value)
    result = curate_sources.register(tmp_path, 'applied_crypto', setup=selected)
    assert result['added_source_ids'] == []
    state = json.loads((directory / 'source_state.json').read_text())
    assert state['sources']['example_labs']['integration']['canaries'][0]['url'].endswith('/42')
    assert json.loads((directory / 'sources.json').read_text())['track_terms'] == ['privacy']
    assert json.loads((directory / 'reference_jobs.json').read_text())['reference_jobs'][0]['source_id'] == 'example_labs'


@pytest.mark.parametrize(('candidate', 'evidence', 'expected'), [
    ({'title': 'Same title', 'url': 'https://jobs.example.test/2'}, {'title': 'Same title', 'url': 'https://jobs.example.test/1'}, False),
    ({'title': 'Same title', 'posting_id': '2'}, {'title': 'Same title', 'posting_id': '1'}, False),
    ({'title': 'Different title', 'posting_id': '1'}, {'posting_id': '1'}, True),
    ({'title': 'Same title'}, {'title': 'same title'}, True),
    ({'url': 'https://jobs.example.test/job?id=42&utm_source=mail#apply'}, {'url': 'https://jobs.example.test/job?id=42'}, True),
    ({'url': 'https://jobs.example.test/job?id=43'}, {'url': 'https://jobs.example.test/job?id=42'}, False),
    ({'url': 'https://example.test/apply', 'alternate_url': 'https://jobs.example.test/42'}, {'url': 'https://jobs.example.test/42'}, True),
])
def test_posting_identity_uses_strongest_available_identifier(candidate, evidence, expected):
    from source_evidence import matches_posting
    assert matches_posting(candidate, evidence) is expected


@pytest.mark.parametrize(('status', 'body', 'expected'), [
    (404, '', 'expired'),
    (410, '', 'expired'),
    (403, '', 'unknown'),
    (200, '<h1>Enable JavaScript</h1>', 'unknown'),
    (200, '<script type="application/ld+json">{"@type":"JobPosting","title":"Privacy Engineer","url":"https://jobs.example.test/jobs/42","description":"Work on privacy","validThrough":"2026-10-01"}</script>', 'expired'),
    (200, '<script type="application/ld+json">{"@type":"JobPosting","title":"Privacy Engineer","url":"https://jobs.example.test/jobs/42","description":"Work on privacy","validThrough":"2026-12-01"}</script>', 'live'),
    (200, '<script type="application/ld+json">{"@type":"JobPosting","title":"Privacy Engineer","url":"https://jobs.example.test/jobs/99","description":"Unrelated identical title"}</script>', 'unknown'),
])
def test_availability_requires_independent_matching_vacancy(monkeypatch, status, body, expected):
    import probe_career_source
    from source_evidence import check_posting_availability
    monkeypatch.setattr(probe_career_source, 'fetch_http', lambda url, timeout: (body, url, status, []))
    result = check_posting_availability({'url': 'https://jobs.example.test/jobs/42', 'title': 'Privacy Engineer'}, today='2026-11-17')
    assert result['availability'] == expected


def test_selection_resolves_provisional_canary_source_without_losing_user_evidence():
    setup = brief()
    supplied = dict(pack(setup)['canaries'][0], source_id='provisional_employer')
    setup['canaries'] = [supplied]
    setup = contracts.normalize_setup(setup)
    result = contracts.apply_source_selection(setup, pack(setup))
    assert result['canaries'][0]['source_id'] == 'example_labs'
    assert result['canaries'][0]['evidence_note'] == supplied['evidence_note']
    assert result['canaries'][0]['provenance'] == 'user_supplied'


def test_worker_cannot_reassign_a_confirmed_existing_reference():
    setup = brief()
    setup['existing_sources'] = [{k: v for k, v in pack(setup)['recommended_sources'][0].items() if k not in {'confidence', 'fit_reason'}}]
    setup['reference_jobs'][0]['source_id'] = 'example_labs'
    setup = contracts.normalize_setup(setup)
    recommendation = pack(setup)
    recommendation['recommended_sources'] = []
    recommendation['recommended_source_ids'] = []
    recommendation['reference_associations'][0]['source_id'] = None
    recommendation['canaries'] = []
    with pytest.raises(contracts.SetupContractError, match='confirmed existing reference'):
        contracts.normalize_source_pack(recommendation, setup)
