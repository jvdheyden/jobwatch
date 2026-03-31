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
