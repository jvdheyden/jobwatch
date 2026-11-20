from __future__ import annotations

import json
from dataclasses import asdict
from urllib.parse import parse_qs, urlparse

import pytest

import discover_jobs
from discover.constants import JD_DESCRIPTION_CHAR_BUDGET
from discover.sources import browser as browser_source
from update_source_state import complete_source_ids


class FakeLink:
    def __init__(self, href: str, text: str, row_text: str | None = None) -> None:
        self._href = href
        self._text = text
        self._row_text = row_text or text

    def get_attribute(self, name: str) -> str:
        assert name == "href"
        return self._href

    def inner_text(self) -> str:
        return self._text

    def evaluate(self, script: str) -> str:
        assert "closest('tr')" in script
        return self._row_text


class FakeLocator:
    def __init__(self, items: list[FakeLink]) -> None:
        self._items = items

    def count(self) -> int:
        return len(self._items)

    def nth(self, index: int) -> FakeLink:
        return self._items[index]


class FakePage:
    def __init__(self, links: list[FakeLink]) -> None:
        self._links = links

    def locator(self, selector: str) -> FakeLocator:
        assert selector == 'a[href^="/profile/job_details/"]'
        return FakeLocator(self._links)


class FakeGizPage:
    def __init__(self, links: list[FakeLink]) -> None:
        self._links = links

    def locator(self, selector: str) -> FakeLocator | FakeHitLocator:
        if selector == 'a[href*="ac=jobad"]':
            return FakeLocator(self._links)
        assert selector == ".js-gjb-hits"
        return FakeHitLocator(str(len(self._links)))


class FakeHitLocator:
    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def first(self) -> FakeHitLocator:
        return self

    def count(self) -> int:
        return 1

    def inner_text(self) -> str:
        return self._text


class FakeBodyLocator:
    def __init__(self, text: str) -> None:
        self._text = text

    def inner_text(self, timeout: int | None = None) -> str:
        del timeout
        return self._text


class FakeDetailPage:
    def __init__(self, detail_text_by_url: dict[str, str]) -> None:
        self._detail_text_by_url = detail_text_by_url
        self._current_url = ""

    def goto(self, url: str, wait_until: str | None = None, timeout: int | None = None) -> None:
        del wait_until, timeout
        self._current_url = url

    def wait_for_function(self, script: str, timeout: int | None = None) -> None:
        del script, timeout

    def wait_for_timeout(self, timeout: int) -> None:
        del timeout

    def locator(self, selector: str) -> FakeBodyLocator:
        assert selector == "body"
        return FakeBodyLocator(self._detail_text_by_url[self._current_url])

    def close(self) -> None:
        return None


class FakeContext:
    def __init__(self, detail_text_by_url: dict[str, str]) -> None:
        self._detail_text_by_url = detail_text_by_url
        self.new_page_calls = 0

    def new_page(self) -> FakeDetailPage:
        self.new_page_calls += 1
        return FakeDetailPage(self._detail_text_by_url)


class FakeEnrichmentPage:
    def __init__(self, detail_text_by_url: dict[str, str]) -> None:
        self.context = FakeContext(detail_text_by_url)


def test_extract_meta_jobs_extracts_visible_result_cards():
    page = FakePage(
        [
            FakeLink(
                "/profile/job_details/1884811572142821",
                "Research Scientist Intern, Applied Perception Science (PhD)\n"
                "Redmond, WA\n⋅\nResearch\n⋅\nHardware\nRedmond, WA\nResearch\nHardware",
            ),
            FakeLink(
                "/profile/job_details/9999999999999999",
                "Software Engineer\nMenlo Park, CA\n⋅\nInfrastructure",
            ),
        ]
    )
    source = discover_jobs.SourceConfig(
        source="Meta",
        url="https://www.metacareers.com/jobs",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    result = discover_jobs.extract_meta_jobs(
        page,
        source,
        term="research scientist",
        terms=["research scientist", "privacy-preserving", "cryptography"],
        page_num=1,
    )

    assert result.visible_results == 2
    assert len(result.raw_ids) == 2
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.title == "Research Scientist Intern, Applied Perception Science (PhD)"
    assert candidate.location == "Redmond, WA"
    assert candidate.url == "https://www.metacareers.com/profile/job_details/1884811572142821"
    assert candidate.matched_terms == ["research scientist"]


def test_extract_giz_jobs_extracts_visible_job_links():
    page = FakeGizPage(
        [
            FakeLink(
                "index.php?ac=jobad&id=81770",
                "Advisor (m/f/d) Agricultural Value Chains",
                "Advisor (m/f/d) Agricultural Value Chains\nBonn\nAdvisory services\n8/31/26",
            ),
            FakeLink(
                "https://jobs.giz.de/index.php?ac=jobad&id=81771",
                "IT Support Specialist (m/f/d)",
                "IT Support Specialist (m/f/d)\nEschborn\nIT\n8/31/26",
            ),
        ]
    )
    source = discover_jobs.SourceConfig(
        source="GIZ Career Opportunities",
        url="https://www.giz.de/en/career/jobs",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    result = discover_jobs.extract_giz_jobs(
        page,
        source,
        term="agricultural value chain",
        terms=["agricultural value chain", "rural development"],
        page_num=1,
    )

    assert result.visible_results == 2
    assert result.declared_total == 2
    assert result.raw_ids == [
        "https://jobs.giz.de/index.php?ac=jobad&id=81770",
        "https://jobs.giz.de/index.php?ac=jobad&id=81771",
    ]
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.title == "Advisor (m/f/d) Agricultural Value Chains"
    assert candidate.location == "Bonn"
    assert candidate.matched_terms == ["agricultural value chain"]


def test_discover_giz_jobs_uses_search_api_without_playwright(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="GIZ Career Opportunities",
        url="https://www.giz.de/en/career/jobs",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    search_payload = {
        "SearchResult": {
            "SearchResultCount": 1,
            "SearchResultCountAll": 1,
            "SearchResultItems": [
                {
                    "MatchedObjectDescriptor": {
                        "ID": "81770",
                        "PositionTitle": "Advisor (m/f/d) Agricultural Value Chains",
                        "PositionURI": "https://jobs.giz.de/index.php?ac=jobad&id=81770",
                        "PositionLocation": [{"CountryName": "Germany", "CityName": "Bonn"}],
                    }
                }
            ],
        }
    }
    empty_search_payload = {
        "SearchResult": {
            "SearchResultCount": 0,
            "SearchResultCountAll": 0,
            "SearchResultItems": [],
        }
    }
    detail_html = """
    <main>
      <nav>Login | Language | Bookmark job ad | Share</nav>
      <h1>Advisor (m/f/d) Agricultural Value Chains</h1>
      <dl>
        <dt>Einsatzort</dt><dd>Bonn</dd>
      </dl>
      <h2>Your tasks</h2>
      <p>Advise agricultural value-chain programmes and rural producer organisations.</p>
      <h2>Your profile</h2>
      <p>Several years of international rural-development experience.</p>
      <footer>JavaScript is disabled | Login | Share</footer>
    </main>
    """

    monkeypatch.setattr(
        browser_source.http,
        "fetch_json",
        lambda url, timeout_seconds: empty_search_payload if "rural+development" in url else search_payload,
    )
    monkeypatch.setattr(browser_source.http, "fetch_text", lambda url, timeout_seconds: detail_html)
    monkeypatch.setattr(
        browser_source,
        "load_sync_playwright",
        lambda: (_ for _ in ()).throw(AssertionError("GIZ catalog discovery must not launch Playwright")),
    )

    coverage = discover_jobs.discover_browser(
        source,
        terms=["agricultural value chain", "rural development"],
        timeout_seconds=30,
    )

    assert coverage.status == "complete"
    assert coverage.listing_pages_scanned == 2
    assert coverage.result_pages_scanned == (
        "agricultural value chain=1page/1of1, rural development=1page/0of0"
    )
    assert coverage.direct_job_pages_opened == 1
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    assert coverage.limitations == []
    candidate = coverage.candidates[0]
    assert candidate.title == "Advisor (m/f/d) Agricultural Value Chains"
    assert candidate.location == "Bonn"
    assert "agricultural value-chain programmes" in candidate.description
    assert "Bookmark job ad" not in candidate.description
    assert "JavaScript is disabled" not in candidate.description


@pytest.mark.parametrize(
    "broken_payload",
    [
        pytest.param('{"error": "Service unavailable"}', id="api-error"),
        pytest.param('{"SearchResult": {"SearchResultCountAll": 0}}', id="missing-items"),
        pytest.param('{"SearchResult": {"SearchResultCountAll": 0, "SearchResultItems": {}}}', id="invalid-items"),
        pytest.param('{"SearchResult": {"SearchResultItems": []}}', id="missing-total"),
        pytest.param('{"SearchResult": {"SearchResultCountAll": 0.5, "SearchResultItems": []}}', id="invalid-total"),
        pytest.param(
            '{"SearchResult": {"SearchResultCountAll": 0, "SearchResultCount": 1, "SearchResultItems": []}}',
            id="inconsistent-counts",
        ),
        pytest.param("<html>Service unavailable</html>", id="invalid-json"),
        pytest.param(TimeoutError("request timed out"), id="timeout"),
    ],
)
def test_discover_giz_jobs_retains_successful_terms_when_one_response_is_invalid(monkeypatch, broken_payload):
    source = discover_jobs.SourceConfig(
        source="GIZ Career Opportunities",
        url="https://www.giz.de/en/career/jobs",
        discovery_mode="browser",
        last_checked="2026-11-15",
        cadence_group="every_3_runs",
        source_id="giz",
    )
    job_url = "https://jobs.giz.de/index.php?ac=jobad&id=81770"
    valid_payload = {
        "SearchResult": {
            "SearchResultCount": 1,
            "SearchResultCountAll": 1,
            "SearchResultItems": [
                {"MatchedObjectDescriptor": {"PositionTitle": "Programme Advisor", "PositionURI": job_url}}
            ],
        }
    }

    def fetch_text(url, timeout_seconds, headers=None):
        if url == job_url:
            return "<main>Programme Advisor in Bonn</main>"
        payload = json.loads(parse_qs(urlparse(url).query)["data"][0])
        term = payload["SearchCriteria"][0]["CriterionValue"][0]
        if term == "agriculture":
            if isinstance(broken_payload, Exception):
                raise broken_payload
            return broken_payload
        assert term == "programme"
        return json.dumps(valid_payload)

    monkeypatch.setattr(browser_source.http, "fetch_text", fetch_text)

    coverage = discover_jobs.discover_source(source, ["agriculture", "programme"], 5)

    assert [candidate.url for candidate in coverage.candidates] == [job_url]
    assert coverage.candidates[0].matched_terms == ["programme"]
    artifact = {"sources": [discover_jobs.coverage_to_dict(coverage)]}
    assert complete_source_ids(artifact, {"giz"}) == set()
    assert coverage.status == "partial"
    assert any("agriculture" in limitation for limitation in coverage.limitations)


@pytest.mark.parametrize(
    ("last_page_ids", "last_page_total", "expected_status"),
    [
        pytest.param([81780], 11, "complete", id="all-vacancies"),
        pytest.param([], 11, "partial", id="empty-last-page"),
        pytest.param([81770], 11, "partial", id="duplicate-on-last-page"),
        pytest.param([], None, "partial", id="missing-total-on-last-page"),
        pytest.param([], 10, "partial", id="lower-total-on-last-page"),
    ],
)
def test_discover_giz_jobs_reconciles_pagination_with_unique_vacancies(
    monkeypatch, last_page_ids, last_page_total, expected_status
):
    source = discover_jobs.SourceConfig(
        source="GIZ Career Opportunities",
        url="https://www.giz.de/en/career/jobs",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    first_page_ids = list(range(81770, 81780))
    pages = {1: (first_page_ids, 11), 11: (last_page_ids, last_page_total)}
    offsets = []
    job_url_prefix = "https://jobs.giz.de/index.php?ac=jobad&id="

    def fetch_search_page(url, timeout_seconds):
        payload = json.loads(parse_qs(urlparse(url).query)["data"][0])
        offset = payload["SearchParameters"]["FirstItem"]
        offsets.append(offset)
        job_ids, total = pages[offset]
        result = {
            "SearchResultCount": len(job_ids),
            "SearchResultItems": [
                {
                    "MatchedObjectDescriptor": {
                        "ID": str(job_id),
                        "PositionTitle": f"Programme Advisor {job_id}",
                        "PositionURI": f"{job_url_prefix}{job_id}",
                    }
                }
                for job_id in job_ids
            ],
        }
        if total is not None:
            result["SearchResultCountAll"] = total
        return {"SearchResult": result}

    monkeypatch.setattr(browser_source.http, "fetch_json", fetch_search_page)
    monkeypatch.setattr(browser_source.http, "fetch_text", lambda *_: "<main>Programme Advisor in Bonn</main>")

    coverage = discover_jobs.discover_browser(source, ["programme"], 5)

    expected_ids = [*first_page_ids, 81780] if expected_status == "complete" else first_page_ids
    assert offsets == [1, 11]
    assert coverage.listing_pages_scanned == 2
    assert coverage.status == expected_status
    assert coverage.enumerated_jobs == len(expected_ids)
    assert {candidate.url for candidate in coverage.candidates} == {
        f"{job_url_prefix}{job_id}" for job_id in expected_ids
    }
    assert bool(coverage.limitations) == (expected_status == "partial")


def test_extract_meta_detail_sections_reads_role_details_from_detail_text():
    detail_text = """
    Privacy Engineer
    Menlo Park, CA
    Responsibilities
    Play a key role in driving code and architecture reviews.
    Conduct technical reviews for new features and identify privacy concerns.
    Minimum Qualifications
    2+ years in privacy or security engineering domains.
    Experience coding in Python or C++.
    Preferred Qualifications
    Experience with large-scale privacy reviews.
    Equal Employment Opportunity
    Meta is proud to be an Equal Employment Opportunity employer.
    """

    sections = discover_jobs.extract_meta_detail_sections(detail_text)

    assert sections["tasks"] == (
        "Play a key role in driving code and architecture reviews. "
        "Conduct technical reviews for new features and identify privacy concerns."
    )
    assert sections["qualifications"] == (
        "2+ years in privacy or security engineering domains. "
        "Experience coding in Python or C++.; Experience with large-scale privacy reviews."
    )


def test_apply_meta_detail_text_appends_notes_and_is_idempotent():
    candidate = discover_jobs.Candidate(
        employer="Meta",
        title="Privacy Engineer",
        url="https://www.metacareers.com/profile/job_details/1418722910003578",
        source_url="https://www.metacareers.com/jobs",
        location="Menlo Park, CA",
        matched_terms=["privacy"],
        notes="Meta browser search q='privacy' page=1",
    )
    detail_text = """
    Responsibilities
    Lead privacy incident triage and mitigation across products.
    Minimum Qualifications
    2+ years in privacy or security engineering.
    """

    updated = discover_jobs.apply_meta_detail_text(candidate, detail_text, ["privacy", "security"])
    duplicate_update = discover_jobs.apply_meta_detail_text(candidate, detail_text, ["privacy", "security"])

    assert updated is True
    assert duplicate_update is False
    assert candidate.matched_terms == ["privacy", "security"]
    assert candidate.notes == (
        "Meta browser search q='privacy' page=1; "
        "Tasks: Lead privacy incident triage and mitigation across products.; "
        "Qualifications: 2+ years in privacy or security engineering."
    )


def test_enrich_meta_candidates_opens_detail_pages_and_enriches_notes():
    candidate = discover_jobs.Candidate(
        employer="Meta",
        title="Privacy Engineer",
        url="https://www.metacareers.com/profile/job_details/1418722910003578",
        source_url="https://www.metacareers.com/jobs",
        location="Menlo Park, CA",
        matched_terms=["privacy"],
        notes="Meta browser search q='privacy' page=1",
    )
    page = FakeEnrichmentPage(
        {
            candidate.url: (
                "Privacy Engineer Responsibilities\n"
                "Lead privacy incident triage and mitigation across products.\n"
                "Minimum Qualifications\n"
                "2+ years in privacy or security engineering.\n"
            )
        }
    )

    result = discover_jobs.enrich_meta_candidates(
        page,
        {candidate.url: candidate},
        ["privacy", "security"],
        timeout_ms=5000,
    )

    assert page.context.new_page_calls == 1
    assert result.direct_job_pages_opened == 1
    assert result.limitations == []
    assert candidate.matched_terms == ["privacy", "security"]
    assert "Tasks: Lead privacy incident triage and mitigation across products." in candidate.notes
    assert "Qualifications: 2+ years in privacy or security engineering." in candidate.notes
    assert asdict(candidate)["description"] == (
        "Responsibilities: Lead privacy incident triage and mitigation across products. "
        "Qualifications: 2+ years in privacy or security engineering."
    )


def test_meta_qualification_only_description_survives_truncation():
    candidate = discover_jobs.Candidate(
        employer="Meta", title="Research Engineer",
        url="https://www.metacareers.com/profile/job_details/1000000001",
        source_url="https://www.metacareers.com/jobs",
    )
    longer_than_notes = "Experience designing reliable protocols for distributed services. " * 6
    qualification = "Knowledge of reproducible systems benchmarking."
    detail_body = longer_than_notes + qualification + " Experience with programming in C++." * 120

    assert discover_jobs.apply_meta_detail_text(candidate, f"Minimum Qualifications\n{detail_body}", [])
    serialized = asdict(candidate)
    assert len(serialized["description"]) <= JD_DESCRIPTION_CHAR_BUDGET
    assert serialized["description_truncated"]
    assert qualification in serialized["description"]
    assert qualification not in serialized["notes"]
