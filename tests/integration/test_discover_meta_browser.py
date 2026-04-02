from __future__ import annotations

import discover_jobs


class FakeLink:
    def __init__(self, href: str, text: str) -> None:
        self._href = href
        self._text = text

    def get_attribute(self, name: str) -> str:
        assert name == "href"
        return self._href

    def inner_text(self) -> str:
        return self._text


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
                "Responsibilities\n"
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
