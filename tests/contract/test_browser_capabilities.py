"""Pagination exercises actual browser provider loops and parsers."""
import copy
import json

import pytest

from browser_fixtures import install_browser
from discover import core
from discover.sources import browser
from contract.test_source_contract import FIXTURES, _source_for_mode


def pages_for(mode):
    page = json.loads((FIXTURES / mode / 'response.json').read_text())[0]
    if mode == 'asml_browser':
        cards = page['a.search-results__item']
        pages = []
        for index, card in enumerate(cards, 1):
            result = copy.deepcopy(page)
            result['a.search-results__item'] = [card]
            result['nav[aria-label="Pagination"] li.pagination-next button[role="link"]'] = [{'disabled': index == 2}]
            result['nav[aria-label="Pagination"] li.pagination-link.active button[role="link"]'] = [{'text': str(index)}]
            pages.append(result)
        return pages, {c['href'] for c in cards}
    if mode == 'thales_browser':
        cards = page['a[href*="/global/en/job/"]']
        pages = []
        for index, card in enumerate(cards, 1):
            result = copy.deepcopy(page)
            result['a[href*="/global/en/job/"]'] = [card]
            result['body'] = [{'text': f'Showing {index} - {index} of 2 results'}]
            result['a[data-ph-at-id="pagination-next-link"]'] = [{'href': 'https://careers.thalesgroup.com/global/en/search-results?page=2'}] if index == 1 else []
            pages.append(result)
        return pages, {c['href'] for c in cards}
    jobs = [[str(i), 'Security Engineer', '', None, None, None, None, 'Google', None, [['Remote']]] for i in range(1, 22)]
    def page_for(rows):
        return {'script': [{'text': "AF_initDataCallback({key: 'ds:1', data:" + json.dumps([rows]) + ', sideChannel: {}});'}]}
    return [page_for(jobs[:20]), page_for(jobs[20:])], {
        f'https://www.google.com/about/careers/applications/jobs/results/{i}-security-engineer' for i in range(1, 22)
    }


@pytest.mark.parametrize('mode', ['asml_browser', 'thales_browser', 'browser'])
@pytest.mark.parametrize('scenario', ['later_page', 'repeated_page', 'page_failure'])
def test_browser_pagination(mode, scenario, monkeypatch):
    pages, expected = pages_for(mode)
    if scenario == 'repeated_page':
        pages[1] = copy.deepcopy(pages[0])
    fake = install_browser(monkeypatch, pages)
    if scenario == 'page_failure':
        original_goto = fake.page.goto
        original_locator = fake.page.locator
        def goto(url, **kwargs):
            if 'page=2' in url:
                raise TimeoutError('second page unavailable')
            return original_goto(url, **kwargs)
        def locator(selector):
            if fake.page.index == 1:
                raise TimeoutError('second page unavailable')
            return original_locator(selector)
        monkeypatch.setattr(fake.page, 'goto', goto)
        monkeypatch.setattr(fake.page, 'locator', locator)
    coverage = core.discover_source(_source_for_mode(mode), ['security'], 1)
    if scenario == 'later_page':
        assert coverage.status == 'complete'
        assert {c.url for c in coverage.candidates} == expected
        assert coverage.listing_pages_scanned >= 2
        assert fake.closed
    else:
        assert coverage.status in {'partial', 'failed'}
        assert coverage.limitations


def test_browser_page_limit_reports_partial(monkeypatch):
    from dataclasses import replace
    pages, _ = pages_for('browser')
    install_browser(monkeypatch, pages)
    monkeypatch.setitem(browser.BROWSER_STRATEGIES, 'Google', replace(browser.BROWSER_STRATEGIES['Google'], max_pages=1))
    coverage = core.discover_source(_source_for_mode('browser'), ['security'], 1)
    assert coverage.status == 'partial'
    assert len(coverage.candidates) == 20
    assert any('cap' in note for note in coverage.limitations)


def test_browser_missing_listing_payload_is_not_authoritative_empty(monkeypatch):
    install_browser(monkeypatch, [{'script': [{'text': 'window.challenge = true;'}]}])
    coverage = core.discover_source(_source_for_mode('browser'), ['security'], 1)
    assert coverage.status == 'partial'
    assert not coverage.candidates
    assert coverage.limitations


@pytest.mark.parametrize('strategy', sorted(browser.BROWSER_STRATEGIES))
def test_every_named_browser_strategy_extracts_expected_jobs(strategy, monkeypatch):
    if strategy == 'Google':
        contract = json.loads((FIXTURES / 'browser/contract.json').read_text())
        pages = json.loads((FIXTURES / 'browser/response.json').read_text())
    else:
        path = FIXTURES / 'browser' / f'{strategy.lower()}.json'
        assert path.is_file(), f'Add raw DOM and independent expectations for new browser strategy {strategy}'
        contract = json.loads(path.read_text())
        pages = contract['pages']
    fake = install_browser(monkeypatch, pages)
    source = core.SourceConfig(**contract['source'], discovery_mode='browser', last_checked=None, cadence_group='every_run')
    coverage = core.discover_source(source, ['security'], 1)
    assert coverage.status == 'complete', coverage.limitations
    assert {(c.title, c.url) for c in coverage.candidates} == {(c['title'], c['url']) for c in contract['expected']}
    assert fake.closed
    if strategy == 'Meta':
        assert coverage.direct_job_pages_opened == 2
        assert all('Build security libraries' in c.notes for c in coverage.candidates)
        assert all('Generic marketing' not in c.notes for c in coverage.candidates)
