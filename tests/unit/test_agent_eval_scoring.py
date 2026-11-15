import json
from pathlib import Path
import sys

import pytest

from evals.score_jobs import score


EVAL_DIR = Path(__file__).resolve().parents[1] / 'evals'
CASES = json.loads((EVAL_DIR / 'cases.json').read_text())
EXPECTATIONS = json.loads((EVAL_DIR / 'expectations.json').read_text())


@pytest.fixture
def rubric():
    return {'dataset_id': 'example', 'scenarios': {
        'engineering': {'review_status': 'pending_human_review', 'ordered_pairs': [['protocols', 'sales']],
            'expected': {'protocols': {'admission': ['admit'], 'score_range': [8, 10], 'critical_recall': True},
                         'sales': {'admission': ['filter'], 'score_range': [1, 3]}}},
        'sales': {'review_status': 'reviewed', 'ordered_pairs': [['sales', 'protocols']],
            'expected': {'protocols': {'admission': ['filter'], 'score_range': [1, 3]},
                         'sales': {'admission': ['admit'], 'score_range': [8, 10], 'critical_recall': True}}},
    }}


def engineering_result():
    return {'dataset_id': 'example', 'scenario_id': 'engineering', 'judgments': [
        {'id': 'protocols', 'admission': 'admit', 'score': 9},
        {'id': 'sales', 'admission': 'filter', 'score': 1},
    ]}


def test_identical_jobs_require_track_specific_decisions(rubric):
    result = engineering_result()
    report = score(rubric, result, scenario_id='engineering')
    assert report['passes_rubric']
    assert report['review_status'] == 'pending_human_review'

    # Reusing engineering judgments in a sales track must fail, even though the
    # candidate IDs and fields are valid. No model calls are involved here.
    result['scenario_id'] = 'sales'
    report = score(rubric, result, scenario_id='sales')
    assert not report['passes_rubric']
    assert report['critical_false_negatives'] == ['sales']
    assert report['false_positives'] == ['protocols']
    assert 'ranking reversal: sales below protocols' in report['issues']
    assert report['scenario_id'] == 'sales'
    assert report['review_status'] == 'reviewed'

    result['judgments'] = [
        {'id': 'protocols', 'admission': 'filter', 'score': 1},
        {'id': 'sales', 'admission': 'admit', 'score': 9},
    ]
    assert score(rubric, result, scenario_id='sales')['passes_rubric']


@pytest.mark.parametrize(('admission', 'misses'), [('review', []), ('filter', ['protocols'])])
def test_retained_uncertainty_is_not_reported_as_a_lost_opportunity(rubric, admission, misses):
    result = engineering_result()
    result['judgments'][0]['admission'] = admission
    report = score(rubric, result, scenario_id='engineering')
    assert not report['passes_rubric']  # The clear evidence calls for admission.
    assert report['critical_false_negatives'] == misses


@pytest.mark.parametrize('judgments', [[], [{'id': 'unknown'}], [{'id': 'protocols'}, {'id': 'protocols'}]])
def test_semantic_evaluation_requires_complete_unique_judgments(rubric, judgments):
    result = engineering_result() | {'judgments': judgments}
    with pytest.raises(ValueError, match='exactly one'):
        score(rubric, result, scenario_id='engineering')


@pytest.mark.parametrize(('updates', 'selected', 'message'), [
    ({'dataset_id': 'old-revision'}, 'engineering', 'dataset_id'),
    ({'scenario_id': 'sales'}, 'engineering', 'scenario_id'),
    ({}, 'unknown', 'Unknown scenario'),
    ({'judgments': None}, 'engineering', 'list of objects'),
    ({'judgments': [None]}, 'engineering', 'list of objects'),
    ({'judgments': [{'id': []}]}, 'engineering', 'string ids'),
])
def test_wrong_context_and_malformed_results_are_rejected(rubric, updates, selected, message):
    with pytest.raises(ValueError, match=message):
        score(rubric, engineering_result() | updates, scenario_id=selected)


@pytest.mark.parametrize('bad_score', [None, True, '9', 0, 11, float('nan'), float('inf')])
def test_scores_must_be_finite_numbers_on_the_fit_scale(rubric, bad_score):
    result = engineering_result()
    result['judgments'][0]['score'] = bad_score
    with pytest.raises(ValueError, match='score must be between'):
        score(rubric, result, scenario_id='engineering')


def test_ranking_reversal_fails_even_when_admission_and_score_bands_pass(rubric):
    rules = rubric['scenarios']['engineering']['expected']
    for rule in rules.values():
        rule.update(admission=['admit'], score_range=[6, 10])
    result = engineering_result()
    result['judgments'] = [
        {'id': 'protocols', 'admission': 'admit', 'score': 7},
        {'id': 'sales', 'admission': 'admit', 'score': 8},
    ]
    report = score(rubric, result, scenario_id='engineering')
    assert report['issues'] == ['ranking reversal: protocols below sales']
    result['judgments'][0]['score'] = 8
    assert score(rubric, result, scenario_id='engineering')['passes_rubric']  # Ties are allowed.


@pytest.mark.parametrize('scenario', CASES['scenarios'], ids=lambda scenario: scenario['id'])
def test_every_scenario_has_complete_independent_review_material(scenario):
    assert CASES['dataset_id'] == EXPECTATIONS['dataset_id']
    scenario_ids = [item['id'] for item in CASES['scenarios']]
    assert len(set(scenario_ids)) == len(scenario_ids)
    assert set(scenario_ids) == set(EXPECTATIONS['scenarios'])
    assert scenario['profile'] and scenario['preferences'] and scenario['candidates']
    ids = [candidate['id'] for candidate in scenario['candidates']]
    assert len(set(ids)) == len(ids)
    expected = EXPECTATIONS['scenarios'][scenario['id']]
    assert set(ids) == set(expected['expected'])
    assert expected['review_status'] in {'pending_human_review', 'reviewed'}
    for rule in expected['expected'].values():
        assert rule['rationale']
        assert rule['admission'] and set(rule['admission']) <= {'admit', 'filter', 'review'}
        assert 1 <= rule['score_range'][0] <= rule['score_range'][1] <= 10
    assert any(rule.get('critical_recall') for rule in expected['expected'].values())
    assert expected['ordered_pairs']
    for higher, lower in expected['ordered_pairs']:
        assert higher in ids and lower in ids and higher != lower


def test_shared_postings_preserve_evidence_while_expected_admission_changes():
    scenarios = {s['id']: s for s in CASES['scenarios']}
    engineering = {j['id']: j for j in scenarios['crypto_engineering']['candidates']}
    sales = {j['id']: j for j in scenarios['security_sales']['candidates']}
    for key, engineer_decision, sales_decision in [('protocols', 'admit', 'filter'), ('sales', 'filter', 'admit')]:
        assert engineering[key] == sales[key]
        assert EXPECTATIONS['scenarios']['crypto_engineering']['expected'][key]['admission'] == [engineer_decision]
        assert EXPECTATIONS['scenarios']['security_sales']['expected'][key]['admission'] == [sales_decision]


@pytest.mark.parametrize('outcome', ['pass', 'critical_miss', 'wrong_scenario', 'malformed'])
def test_cli_scores_the_selected_scenario_and_reports_failures(tmp_path, run_cmd, outcome):
    result = {'dataset_id': 'jobwatch-tracks-v1', 'scenario_id': 'security_sales', 'judgments': [
        {'id': 'protocols', 'admission': 'filter', 'score': 1},
        {'id': 'sales', 'admission': 'admit', 'score': 9},
        {'id': 'enterprise_account', 'admission': 'admit', 'score': 9},
        {'id': 'solutions_consultant', 'admission': 'admit', 'score': 7},
        {'id': 'consumer_account', 'admission': 'filter', 'score': 1},
        {'id': 'keyword_noise', 'admission': 'filter', 'score': 1},
    ]}
    if outcome == 'critical_miss':
        result['judgments'][1].update(admission='filter', score=1)
    if outcome == 'wrong_scenario':
        result['scenario_id'] = 'crypto_engineering'
    path = tmp_path / 'result.json'
    path.write_text('{malformed' if outcome == 'malformed' else json.dumps(result))
    completed = run_cmd(sys.executable, str(EVAL_DIR / 'score_jobs.py'), '--scenario', 'security_sales', str(path))
    if outcome in {'wrong_scenario', 'malformed'}:
        assert completed.returncode == 2
        assert 'error:' in completed.stderr
    else:
        assert completed.returncode == (0 if outcome == 'pass' else 1)
        report = json.loads(completed.stdout)
        assert report['scenario_id'] == 'security_sales'
        assert report['critical_false_negatives'] == ([] if outcome == 'pass' else ['sales'])
