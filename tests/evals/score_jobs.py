#!/usr/bin/env python3
"""Score opt-in find/rank judgments. Never invokes a model or grades prose."""
import argparse
import json
from pathlib import Path


def score(expected, result, *, scenario_id):
    if scenario_id not in expected['scenarios']:
        raise ValueError(f'Unknown scenario: {scenario_id}')
    if not isinstance(result, dict) or result.get('dataset_id') != expected['dataset_id']:
        raise ValueError('Result dataset_id must match the evaluation dataset')
    if result.get('scenario_id') != scenario_id:
        raise ValueError(f'Result scenario_id must match selected scenario {scenario_id}')
    rubric = expected['scenarios'][scenario_id]
    judgments = result.get('judgments')
    if not isinstance(judgments, list) or any(
        not isinstance(j, dict) or not isinstance(j.get('id'), str) for j in judgments
    ):
        raise ValueError('judgments must be a list of objects with string ids')
    by_id = {j['id']: j for j in judgments}
    wanted = rubric['expected']
    if len(by_id) != len(judgments) or set(by_id) != set(wanted):
        raise ValueError('Require exactly one judgment for every dataset id; no unknown ids')
    errors = []
    critical_misses = []
    false_positives = []
    for key, rule in wanted.items():
        actual = by_id[key]
        if actual.get('admission') not in ('admit', 'filter', 'review'):
            raise ValueError(f'{key}: invalid admission')
        if not isinstance(actual.get('score'), (int, float)) or isinstance(actual['score'], bool) or not 1 <= actual['score'] <= 10:
            raise ValueError(f'{key}: score must be between 1 and 10')
        if actual['admission'] not in rule['admission']:
            errors.append(f'{key}: admission {actual["admission"]}')
            if rule.get('critical_recall') and actual['admission'] == 'filter':
                critical_misses.append(key)
            if rule['admission'] == ['filter']:
                false_positives.append(key)
        low, high = rule['score_range']
        if not low <= actual['score'] <= high:
            errors.append(f'{key}: score outside rubric range [{low}, {high}]')
    for higher, lower in rubric['ordered_pairs']:
        if by_id[higher]['score'] < by_id[lower]['score']:
            errors.append(f'ranking reversal: {higher} below {lower}')
    return {'dataset_id': expected['dataset_id'], 'scenario_id': scenario_id,
            'review_status': rubric['review_status'],
            'critical_false_negatives': critical_misses, 'false_positives': false_positives,
            'issues': errors, 'passes_rubric': not errors}


if __name__ == '__main__':
    expected = json.loads(Path(__file__).with_name('expectations.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', required=True, choices=sorted(expected['scenarios']))
    parser.add_argument('result', type=Path)
    args = parser.parse_args()
    try:
        report = score(expected, json.loads(args.result.read_text()), scenario_id=args.scenario)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passes_rubric'] else 1)
