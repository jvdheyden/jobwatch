from __future__ import annotations

import sys
from types import ModuleType

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
        assert selector == "a.search-results__item"
        return FakeLocator(self._links)


def test_extract_asml_jobs_extracts_and_filters_visible_result_cards():
    page = FakePage(
        [
            FakeLink(
                "https://www.asml.com/en/careers/find-your-job/cryptography-engineer-j00330001",
                "NEW\nCryptography Engineer\nVeldhoven, Netherlands\nSecurity",
            ),
            FakeLink(
                "https://www.asml.com/en/careers/find-your-job/service-business-manager-sales-j00334655",
                "Service Business Manager Sales\nVeldhoven, Netherlands\nSales",
            ),
        ]
    )
    source = discover_jobs.SourceConfig(
        source="ASML",
        url="https://www.asml.com/en/careers/find-your-job",
        discovery_mode="asml_browser",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    result = discover_jobs.extract_asml_jobs(
        page,
        source,
        terms=["cryptography", "privacy", "security"],
        page_num=1,
    )

    assert result.visible_results == 2
    assert len(result.raw_ids) == 2
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.title == "Cryptography Engineer"
    assert candidate.location == "Veldhoven, Netherlands"
    assert candidate.url == "https://www.asml.com/en/careers/find-your-job/cryptography-engineer-j00330001"
    assert candidate.matched_terms == ["cryptography", "security"]
    assert candidate.notes == "ASML browser enumeration page=1; team=Security"


class _RaisingChromium:
    def launch(self, headless: bool = True):
        del headless
        raise RuntimeError(
            "BrowserType.launch: Executable doesn't exist at /tmp/chromium/chrome\n"
            "Looks like Playwright was just installed or updated.\n"
            "Please run the following command to download new browsers:\n"
            "playwright install"
        )


class _PlaywrightContext:
    def __enter__(self):
        return type("FakePlaywright", (), {"chromium": _RaisingChromium()})()

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


def test_discover_trailofbits_browser_reports_missing_browser_binaries_as_partial(monkeypatch):
    playwright_module = ModuleType("playwright")
    playwright_module.__path__ = []  # type: ignore[attr-defined]
    sync_api_module = ModuleType("playwright.sync_api")
    sync_api_module.sync_playwright = lambda: _PlaywrightContext()
    playwright_module.sync_api = sync_api_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", playwright_module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api_module)

    source = discover_jobs.SourceConfig(
        source="Trail of Bits",
        url="https://trailofbits.com/careers/",
        discovery_mode="trailofbits_browser",
        last_checked=None,
        cadence_group="every_run",
    )

    result = discover_jobs.discover_source(source, ["cryptography"], timeout_seconds=20)

    assert result.status == "partial"
    assert result.limitations == [
        "Playwright browser binaries are not installed; run ./.venv/bin/python -m playwright install chromium"
    ]
