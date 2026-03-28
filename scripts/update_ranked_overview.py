#!/usr/bin/env python3
"""Rebuild the persistent ranked overview for a track from digests and seen jobs."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIGEST_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
ROLE_HEADER_RE = re.compile(r"^(#{3,4})\s+(.+?)\s*$")
LINK_RE = re.compile(r"^\s*-?\s*Link:\s*(\S+)\s*$", flags=re.MULTILINE)
FIT_SCORE_RE = re.compile(r"^\s*-?\s*Fit score:\s*([0-9]+(?:\.[0-9]+)?)\s*/10\s*$", flags=re.MULTILINE)
LOCATION_RE = re.compile(r"^\s*-?\s*Location:\s*(.+?)\s*$", flags=re.MULTILINE)


@dataclass
class RankedJob:
    job_key: str
    company: str
    title: str
    url: str
    fit_score: float | None
    date_seen: str
    date_seen_page: str
    last_seen: str
    times_seen: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", default="core_crypto", help="Track name under tracks/")
    return parser


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def track_display_name(track: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[_-]+", track) if part)


def normalize_url(url: str) -> str:
    return url.rstrip("/")


def make_job_key(company: str, title: str, location: str) -> str:
    _ = location
    return " | ".join(
        [
            normalize_text(company),
            normalize_text(title),
        ]
    )


def digest_page_name(track: str, stamp: str) -> str:
    if track == "core_crypto":
        return f"Job Digest {stamp}"
    return f"{track_display_name(track)} Job Digest {stamp}"


def parse_role_blocks(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    blocks: list[tuple[str, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in lines:
        header_match = ROLE_HEADER_RE.match(line)
        if header_match:
            if current_heading is not None:
                blocks.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = header_match.group(2).strip()
            current_lines = []
            continue
        if current_heading is not None:
            current_lines.append(line)

    if current_heading is not None:
        blocks.append((current_heading, "\n".join(current_lines).strip()))
    return blocks


def clean_heading(value: str) -> str:
    return re.sub(r"^\d+\.\s*", "", value.strip())


def parse_ranked_roles_from_digest(path: Path) -> list[dict[str, object]]:
    text = path.read_text()
    roles: list[dict[str, object]] = []

    for heading, block in parse_role_blocks(text):
        heading = clean_heading(heading)
        if " — " not in heading:
            continue

        link_match = LINK_RE.search(block)
        score_match = FIT_SCORE_RE.search(block)
        if not link_match or not score_match:
            continue

        title, company = heading.rsplit(" — ", 1)
        location_match = LOCATION_RE.search(block)
        location = location_match.group(1).strip() if location_match else "unknown"

        roles.append(
            {
                "title": title.strip(),
                "company": company.strip(),
                "url": normalize_url(link_match.group(1).strip()),
                "fit_score": float(score_match.group(1)),
                "location": location,
            }
        )
    return roles


def parse_seen_jobs(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    rows: list[dict[str, str]] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(" | ", 4)]
        if len(parts) != 5:
            continue
        rows.append(
            {
                "date_seen": parts[0],
                "company": parts[1],
                "title": parts[2],
                "location": parts[3],
                "url": normalize_url(parts[4]),
            }
        )
    return rows


def role_sort_key(role: RankedJob) -> tuple[float, str, str, str]:
    score = role.fit_score if role.fit_score is not None else -1.0
    return (-score, role.date_seen, role.company.lower(), role.title.lower())


def render_markdown(track: str, jobs: list[RankedJob], state_path: Path) -> str:
    lines = [
        f"# Ranked Overview — {track_display_name(track)}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')}",
        f"Source of truth: `{state_path.relative_to(ROOT)}`",
        f"Total jobs: {len(jobs)}",
        f"Tags: [[job digest {track}]]",
        "",
        "| Fit score | Company | Title | Listing URL | Date seen |",
        "| --- | --- | --- | --- | --- |",
    ]

    for job in jobs:
        score = f"{job.fit_score:g}" if job.fit_score is not None else "—"
        listing = f"[link]({job.url})" if job.url else "—"
        date_seen = f"[[{job.date_seen_page}]]"
        lines.append(f"| {score} | {job.company} | {job.title} | {listing} | {date_seen} |")

    lines.append("")
    return "\n".join(lines)


def rebuild_track_state(track: str) -> tuple[Path, Path, list[RankedJob]]:
    digests_dir = ROOT / "tracks" / track / "digests"
    seen_jobs_path = ROOT / "shared" / "seen_jobs.md"
    state_path = ROOT / "shared" / "ranked_jobs" / f"{track}.json"
    markdown_path = ROOT / "tracks" / track / "ranked_overview.md"

    digest_paths = sorted(path for path in digests_dir.iterdir() if DIGEST_FILE_RE.match(path.name))
    records: dict[str, dict[str, object]] = {}

    for digest_path in digest_paths:
        digest_date = digest_path.stem
        for role in parse_ranked_roles_from_digest(digest_path):
            job_key = make_job_key(role["company"], role["title"], role["location"])
            record = records.get(job_key)
            if record is None:
                record = {
                    "job_key": job_key,
                    "company": role["company"],
                    "title": role["title"],
                    "url": role["url"],
                    "fit_score": role["fit_score"],
                    "date_seen": digest_date,
                    "date_seen_page": digest_page_name(track, digest_date),
                    "last_seen": digest_date,
                    "seen_dates": {digest_date},
                }
                records[job_key] = record
                continue

            seen_dates = record["seen_dates"]
            assert isinstance(seen_dates, set)
            seen_dates.add(digest_date)
            record["last_seen"] = max(str(record["last_seen"]), digest_date)
            existing_score = record["fit_score"]
            if existing_score is None or float(role["fit_score"]) > float(existing_score):
                record["fit_score"] = role["fit_score"]
            if not record["url"] and role["url"]:
                record["url"] = role["url"]

    # `shared/seen_jobs.md` is a legacy global file with no track metadata.
    # Backfilling it into non-core tracks pollutes their ranked overviews.
    if track == "core_crypto":
        for seen in parse_seen_jobs(seen_jobs_path):
            job_key = make_job_key(seen["company"], seen["title"], seen["location"])
            record = records.get(job_key)
            if record is None:
                records[job_key] = {
                    "job_key": job_key,
                    "company": seen["company"],
                    "title": seen["title"],
                    "url": seen["url"],
                    "fit_score": None,
                    "date_seen": seen["date_seen"],
                    "date_seen_page": digest_page_name(track, seen["date_seen"]),
                    "last_seen": seen["date_seen"],
                    "seen_dates": {seen["date_seen"]},
                }
                continue

            seen_dates = record["seen_dates"]
            assert isinstance(seen_dates, set)
            seen_dates.add(seen["date_seen"])
            if seen["date_seen"] < str(record["date_seen"]):
                record["date_seen"] = seen["date_seen"]
                record["date_seen_page"] = digest_page_name(track, seen["date_seen"])
            record["last_seen"] = max(str(record["last_seen"]), seen["date_seen"])
            if not record["url"] and seen["url"]:
                record["url"] = seen["url"]

    jobs: list[RankedJob] = []
    for record in records.values():
        seen_dates = record.pop("seen_dates")
        assert isinstance(seen_dates, set)
        jobs.append(
            RankedJob(
                job_key=str(record["job_key"]),
                company=str(record["company"]),
                title=str(record["title"]),
                url=str(record["url"]),
                fit_score=float(record["fit_score"]) if record["fit_score"] is not None else None,
                date_seen=str(record["date_seen"]),
                date_seen_page=str(record["date_seen_page"]),
                last_seen=str(record["last_seen"]),
                times_seen=len(seen_dates),
            )
        )

    jobs.sort(key=role_sort_key)
    return state_path, markdown_path, jobs


def main() -> int:
    args = build_parser().parse_args()
    state_path, markdown_path, jobs = rebuild_track_state(args.track)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    state_payload = {
        "track": args.track,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "jobs": [asdict(job) for job in jobs],
    }
    state_path.write_text(json.dumps(state_payload, indent=2, ensure_ascii=False) + "\n")
    markdown_path.write_text(render_markdown(args.track, jobs, state_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
