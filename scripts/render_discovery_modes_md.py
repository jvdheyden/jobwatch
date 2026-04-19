#!/usr/bin/env python3
"""Render registry-backed discovery-mode documentation."""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path

from discover.registry import load_registry


ROOT = Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))
DEFAULT_OUTPUT = ROOT / "docs" / "discovery_modes.md"


MODE_DETAILS = {
    "ashby_api": {
        "url_shape": "`https://jobs.ashbyhq.com/<organization>`",
        "filters": "none",
        "limitations": "Uses Ashby public GraphQL job-board data exposed by the hosted jobs page.",
    },
    "ashby_html": {
        "url_shape": "`https://jobs.ashbyhq.com/<organization>`",
        "filters": "none",
        "limitations": "Compatibility alias for the Ashby provider.",
    },
    "asml_browser": {
        "url_shape": "`https://www.asml.com/en/careers/find-your-job`",
        "filters": "none",
        "limitations": "Requires Playwright and installed Chromium browser binaries.",
    },
    "auswaertiges_amt_json": {
        "url_shape": "Auswaertiges Amt careers page exposing an `/ajax/json-filterlist/...` endpoint.",
        "filters": "none",
        "limitations": "Depends on the page retaining its embedded JSON-filter endpoint.",
    },
    "automattic_browser": {
        "url_shape": "`https://automattic.com/work-with-us/`",
        "filters": "none",
        "limitations": "Requires Playwright and extracts visible job-card links only.",
    },
    "bnd_career_search": {
        "url_shape": "BND advanced career-search form URL.",
        "filters": "encode BND native filters in the source URL",
        "limitations": "Parses native result cards from the rendered HTML response.",
    },
    "bosch_autocomplete": {
        "url_shape": "Bosch careers jobs page.",
        "filters": "none",
        "limitations": "Uses the public autocomplete/search endpoint discovered for Bosch careers.",
    },
    "browser": {
        "url_shape": "Generic browser strategy keyed by source name; currently Google, Meta, and Bosch strategies are implemented.",
        "filters": "`location` and `degree` for Google sources",
        "limitations": "Requires Playwright and installed Chromium browser binaries.",
    },
    "bundeswehr_jobsuche": {
        "url_shape": "Bundeswehr jobsuche portal URL.",
        "filters": "none",
        "limitations": "Combines portal fallback and SAP OData-style discovery where available.",
    },
    "coinbase_browser": {
        "url_shape": "`https://www.coinbase.com/careers`",
        "filters": "none",
        "limitations": "Currently reports partial coverage when Cloudflare or unsupported listing extraction blocks deterministic enumeration.",
    },
    "cybernetica_teamdash": {
        "url_shape": "Cybernetica careers page with `cyber.teamdash.com/p/job/` links.",
        "filters": "none",
        "limitations": "Only direct Teamdash job links visible in the careers-page HTML are enumerated.",
    },
    "eightfold_api": {
        "url_shape": "Eightfold-hosted careers URL such as Microsoft careers.",
        "filters": "none",
        "limitations": "Provider contains host-specific domain mapping for supported Eightfold boards.",
    },
    "enbw_phenom": {
        "url_shape": "`https://careers.enbw.com/en_US/careers`",
        "filters": "none",
        "limitations": "Parses embedded Phenom search payloads from localized search-result pages.",
    },
    "getro_api": {
        "url_shape": "Getro collection jobs URL.",
        "filters": "none",
        "limitations": "Uses Getro collection API pagination and provider-side post-filtering.",
    },
    "greenhouse_api": {
        "url_shape": "`https://job-boards.greenhouse.io/<board>`",
        "filters": "none",
        "limitations": "Uses the Greenhouse public job-board API shape.",
    },
    "hackernews_jobs": {
        "url_shape": "`https://news.ycombinator.com/jobs`",
        "filters": "none",
        "limitations": "Enumerates Hacker News jobs pages and external links visible in listing HTML.",
    },
    "hackernews_whoishiring_api": {
        "url_shape": "`https://news.ycombinator.com/user?id=whoishiring`",
        "filters": "none",
        "limitations": "Parses the active Who Is Hiring thread and infers employer/title fields from post text.",
    },
    "helsing_browser": {
        "url_shape": "`https://helsing.ai/jobs`",
        "filters": "none",
        "limitations": "Requires Playwright and extracts visible job cards from the jobs page.",
    },
    "html": {
        "url_shape": "Any official static careers/listings page with direct job links.",
        "filters": "none",
        "limitations": "Best-effort static link extraction; does not execute JavaScript.",
    },
    "iacr_jobs": {
        "url_shape": "`https://www.iacr.org/jobs/`",
        "filters": "none",
        "limitations": "Parses IACR posting blocks from the jobs page.",
    },
    "ibm_api": {
        "url_shape": "`https://www.ibm.com/careers/search`",
        "filters": "none",
        "limitations": "Uses IBM careers search API with title-scoped query terms.",
    },
    "icims_html": {
        "url_shape": "Official iCIMS or employer careers page exposing static job links.",
        "filters": "none",
        "limitations": "Static HTML fallback only; blocked iCIMS pages may return failed or partial coverage.",
    },
    "infineon_api": {
        "url_shape": "`https://jobs.infineon.com/careers`",
        "filters": "none",
        "limitations": "Infineon-specific Eightfold provider wrapper.",
    },
    "leastauthority_careers": {
        "url_shape": "Least Authority careers page.",
        "filters": "none",
        "limitations": "Coverage marker provider; may emit no candidates when no current listing links are exposed.",
    },
    "lever_json": {
        "url_shape": "`https://jobs.lever.co/<organization>`",
        "filters": "none",
        "limitations": "Uses Lever public postings JSON.",
    },
    "neclab_jobs": {
        "url_shape": "NEC Laboratories Europe jobs page.",
        "filters": "none",
        "limitations": "Static page provider for visible job links.",
    },
    "partisia_site": {
        "url_shape": "Partisia careers/company site URLs.",
        "filters": "none",
        "limitations": "Coverage marker provider for pages that may not expose current job links.",
    },
    "pcd_team": {
        "url_shape": "`https://pcd.team/jd`",
        "filters": "none",
        "limitations": "Static PCD Team provider with detail-section extraction.",
    },
    "personio_page": {
        "url_shape": "`https://<organization>.jobs.personio.de/`",
        "filters": "none",
        "limitations": "Extracts Personio jobs from embedded page payloads.",
    },
    "qedit_inline": {
        "url_shape": "QEDIT careers page.",
        "filters": "none",
        "limitations": "Static inline careers-page provider.",
    },
    "qusecure_careers": {
        "url_shape": "QuSecure careers page.",
        "filters": "none",
        "limitations": "Coverage marker provider for pages without direct current listing links.",
    },
    "recruitee_inline": {
        "url_shape": "Recruitee-hosted careers page exposing embedded app config.",
        "filters": "none",
        "limitations": "Depends on the page retaining Recruitee embedded data attributes.",
    },
    "rheinmetall_html": {
        "url_shape": "Rheinmetall current jobs page, including encoded native filters in the source URL.",
        "filters": "encode Rheinmetall native filters in the source URL",
        "limitations": "Parses Rheinmetall result-card HTML and pagination.",
    },
    "secunet_jobboard": {
        "url_shape": "secunet careers or `https://jobs.secunet.com/` page with `*-j<id>.html` job links.",
        "filters": "none",
        "limitations": "Only links matching the secunet job-detail URL pattern are enumerated.",
    },
    "service_bund_links": {
        "url_shape": "Official employer page exposing `service.bund.de/.../IMPORTE/Stellenangebote/...` links.",
        "filters": "none",
        "limitations": "Enumerates direct service.bund job-detail links from the source page.",
    },
    "service_bund_search": {
        "url_shape": "`https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html...`",
        "filters": "encode service.bund native filters in the source URL",
        "limitations": "Parses service.bund search results and next-page tokens.",
    },
    "thales_browser": {
        "url_shape": "`https://careers.thalesgroup.com/global/en/search-results`",
        "filters": "none",
        "limitations": "Requires Playwright; HTML provider is preferred when embedded payloads are available.",
    },
    "thales_html": {
        "url_shape": "`https://careers.thalesgroup.com/global/en/search-results`",
        "filters": "none",
        "limitations": "Parses embedded Phenom-style search payloads and Thales job links.",
    },
    "trailofbits_browser": {
        "url_shape": "`https://trailofbits.com/careers/`",
        "filters": "none",
        "limitations": "Requires Playwright and extracts visible Workable application links.",
    },
    "verfassungsschutz_rss": {
        "url_shape": "Verfassungsschutz jobs source; provider reads the official jobs RSS feed.",
        "filters": "none",
        "limitations": "Uses RSS plus detail-page enrichment where reachable.",
    },
    "workable_api": {
        "url_shape": "`https://apply.workable.com/<board>/`",
        "filters": "none",
        "limitations": "Uses Workable public board endpoints.",
    },
    "workday_api": {
        "url_shape": "`https://<tenant>.wd<region>.myworkdayjobs.com/<site>`",
        "filters": "none",
        "limitations": "Supports standard Workday candidate API search; source URL must expose a compatible Workday host.",
    },
    "yc_jobs_board": {
        "url_shape": "`https://www.ycombinator.com/jobs/role/<role>`",
        "filters": "none",
        "limitations": "Parses the YC jobs Next.js payload for the configured role board.",
    },
}


def _markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def render_discovery_modes_markdown() -> str:
    registry = load_registry()
    missing_details = sorted(set(registry) - set(MODE_DETAILS))
    if missing_details:
        raise RuntimeError("Missing discovery-mode docs for: " + ", ".join(missing_details))

    lines = [
        "# Discovery Modes",
        "",
        "> Generated read-only summary. Do not edit this file directly.",
        "> Run `./.venv/bin/python scripts/render_discovery_modes_md.py` after changing provider registry entries.",
        "",
        "Discovery source support lives behind `discovery_mode` provider adapters registered under `scripts/discover/sources/`.",
        "New source support should usually add or extend one of these provider modules rather than editing `scripts/discover_jobs.py`.",
        "",
        "## Modes",
        "",
    ]

    for mode, adapter in sorted(registry.items()):
        module = adapter.discover.__module__
        function = adapter.discover.__name__
        requirements = ", ".join(f"`{requirement}`" for requirement in adapter.requires) or "none"
        fixture_path = ROOT / "tests" / "fixtures" / "sources" / mode
        fixtures = f"`tests/fixtures/sources/{mode}/`" if fixture_path.exists() else "none"
        details = MODE_DETAILS[mode]
        lines.extend(
            [
                f"### `{_markdown_cell(mode)}`",
                "",
                f"- Provider: `{_markdown_cell(module)}` / `{_markdown_cell(function)}`",
                f"- Emits candidates: {'yes' if adapter.emits_candidates else 'no'}",
                f"- URL/source shape: {details['url_shape']}",
                f"- Supported filters/options: {details['filters']}",
                f"- Contract fixtures: {fixtures}",
                f"- Requirements: {requirements}",
                f"- Known limitations: {details['limitations']}",
                "",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Markdown output path")
    parser.add_argument("--check", action="store_true", help="Fail if the output file is stale")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_path = Path(args.output)
    rendered = render_discovery_modes_markdown()
    if args.check:
        current = output_path.read_text() if output_path.exists() else ""
        if current == rendered:
            return 0
        diff = "\n".join(
            difflib.unified_diff(
                current.splitlines(),
                rendered.splitlines(),
                fromfile=str(output_path),
                tofile="generated",
                lineterm="",
            )
        )
        print(f"Discovery mode docs are out of date. Run: ./.venv/bin/python scripts/render_discovery_modes_md.py\n{diff}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
