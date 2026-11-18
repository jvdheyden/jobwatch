"""Paging regressions for families not covered by older specialized suites."""
import json

import pytest

from discover import core, http
from discover.sources import enbw, ibm, workday
from contract.test_source_contract import _source_for_mode


@pytest.mark.parametrize('mode', ['workday_api', 'ibm_api', 'enbw_phenom'])
@pytest.mark.parametrize('scenario', ['later_page', 'repeated_page', 'early_empty', 'malformed'])
def test_pagination_does_not_claim_complete_when_jobs_are_missing(mode, scenario, monkeypatch):
    calls = []
    monkeypatch.setattr(workday, 'WORKDAY_RESULTS_PAGE_SIZE', 1)
    monkeypatch.setattr(ibm, 'IBM_RESULTS_PAGE_SIZE', 1)
    def payload(offset):
        calls.append(offset)
        if scenario == 'malformed':
            return {'unexpected': 'upstream schema changed'}
        n = 1 if scenario == 'repeated_page' else offset + 1
        empty = scenario == 'early_empty' and offset > 0
        if mode == 'workday_api':
            return {'total': 2, 'jobPostings': [] if empty else [{'title': f'Security Engineer {n}', 'externalPath': f'/job/{n}'}]}
        if mode == 'ibm_api':
            return {'hits': {'total': {'value': 2}, 'hits': [] if empty else [{'_id': str(n), '_source': {'title': f'Security Engineer {n}', 'url': f'https://careers.ibm.com/job/{n}'}}]}}
        return {'eagerLoadRefineSearch': {'hits': 1, 'totalHits': 2, 'data': {'jobs': [] if empty else [{'jobId': str(n), 'title': f'Security Engineer {n}'}]}}}
    def post(url, data, timeout_seconds, headers=None):
        return payload(data.get('offset', data.get('from', 0)))
    def text(url, timeout_seconds, headers=None):
        from urllib.parse import parse_qs, urlparse
        return '<script>phApp.ddo = ' + json.dumps(payload(int(parse_qs(urlparse(url).query).get('from', ['0'])[0]))) + ';</script>'
    monkeypatch.setattr(http, 'post_json', post)
    monkeypatch.setattr(http, 'fetch_text', text)
    monkeypatch.setattr(http, 'fetch_json', lambda *a, **k: {'jobPostingInfo': {'jobDescription': 'Build security tools.'}})
    coverage = core.discover_source(_source_for_mode(mode), ['security'], 1)
    assert len(calls) <= 5, 'Enumeration must terminate when the server repeats a page'
    if scenario == 'later_page':
        assert coverage.status == 'complete'
        assert {c.title for c in coverage.candidates} == {'Security Engineer 1', 'Security Engineer 2'}
        assert calls == [0, 1]
    else:
        assert coverage.status in {'partial', 'failed'}
        assert coverage.limitations
        if scenario != 'malformed':
            assert [c.title for c in coverage.candidates] == ['Security Engineer 1']
