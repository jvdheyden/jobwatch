from __future__ import annotations

import json

import discover_jobs


class FakeScriptLocator:
    def __init__(self, scripts: list[str]) -> None:
        self._scripts = scripts

    def all_inner_texts(self) -> list[str]:
        return self._scripts


class FakeGooglePage:
    def __init__(self, payload: list[object]) -> None:
        self._scripts = [
            "AF_initDataCallback({"
            "key: 'ds:1', "
            f"data:{json.dumps(payload)}, "
            "sideChannel: {}"
            "});"
        ]

    def locator(self, selector: str) -> FakeScriptLocator:
        assert selector == "script"
        return FakeScriptLocator(self._scripts)


def test_extract_google_jobs_preserves_concise_payload_details():
    source = discover_jobs.SourceConfig(
        source="Google",
        url="https://www.google.com/about/careers/applications/jobs/results",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    responsibilities = (
        "Lead applied cryptography architecture for privacy-preserving products. "
        "Coordinate design reviews for secure distributed systems. "
        "Own implementation roadmaps for trusted systems. "
        "Own implementation roadmaps for trusted systems. "
        "Own implementation roadmaps for trusted systems. "
        "UNTRUNCATED RESPONSIBILITY TAIL"
    )
    payload = [
        [
            [
                "123456",
                "Security Engineer, Privacy Infrastructure",
                "https://careers.google.com/jobs/results/123456-security-engineer/",
                ["Responsibilities", responsibilities],
                ["Minimum qualifications", "Experience with security engineering and applied cryptography."],
                None,
                None,
                "Google",
                None,
                [["Munich, Germany"], ["Zurich, Switzerland"]],
                ["Summary", "Protect users by building privacy-preserving security systems."],
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                ["Working location", "Hybrid role in Munich or Zurich."],
            ]
        ]
    ]

    result = discover_jobs.extract_google_jobs(
        FakeGooglePage(payload),
        source,
        term="cryptography",
        terms=["cryptography", "privacy", "security"],
        page_num=1,
    )

    assert result.visible_results == 1
    assert result.raw_ids == ["123456"]
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.title == "Security Engineer, Privacy Infrastructure"
    assert candidate.matched_terms == ["cryptography", "privacy", "security"]
    assert "Google browser search q='cryptography'" in candidate.notes
    assert "Summary: Protect users by building privacy-preserving security systems." in candidate.notes
    assert "Tasks: Lead applied cryptography architecture" in candidate.notes
    assert "Qualifications: Experience with security engineering and applied cryptography." in candidate.notes
    assert "UNTRUNCATED RESPONSIBILITY TAIL" not in candidate.notes
