#!/usr/bin/env python3
"""Prepare scheduled review input and record acknowledged candidate versions."""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

from digest_json import ROOT, digest_artifact_path, normalize_digest_payload
from source_config import file_lock, read_json_payload, write_json_atomic
from source_evidence import identity_url


SCHEMA_VERSION = 1
EVIDENCE_FIELDS = ("employer", "title", "location", "remote", "description")


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_fingerprint(path: Path) -> str | None:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def criteria_fingerprint(root: Path, track: str) -> str:
    paths = (
        f"tracks/{track}/AGENTS.md",
        f"tracks/{track}/prefs.md",
        f"tracks/{track}/reference_jobs.json",
        "profile/prefs_global.md",
        "profile/cv.md",
        ".agents/skills/find-jobs/SKILL.md",
        ".agents/skills/rank-jobs/SKILL.md",
    )
    return fingerprint({name: file_fingerprint(root / name) for name in paths})


def evidence_fingerprint(candidate: dict) -> str:
    evidence = [" ".join((candidate.get(key) or "").split()) for key in EVIDENCE_FIELDS]
    return fingerprint([*evidence, candidate.get("description_truncated", False)])


def normalized_posting_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https", "file"} and (parsed.hostname or parsed.scheme == "file"):
            return identity_url(value)
    except ValueError:
        pass
    return ""


def stable_candidate_id(source: dict, candidate: dict) -> str | None:
    if candidate.get("identity_ambiguous"):
        return None
    scope = source["source_id"]
    board = normalized_posting_url(source.get("source_url") or "")
    posting_id = candidate.get("posting_id")
    if type(posting_id) in (str, int) and str(posting_id).strip():
        identity = [scope, "native", source.get("discovery_mode"), board, str(posting_id).strip()]
        return "c_" + fingerprint(identity)[:32]

    for key in ("url", "alternate_url"):
        url = normalized_posting_url(candidate.get(key) or "")
        if not url:
            continue
        parsed = urlsplit(url)
        # A board or homepage link without a separate posting identity can be
        # reused for entirely different vacancies, even across separate scans.
        if url == board or (not parsed.query and (parsed.path == "/" or url == board.partition("?")[0])):
            continue
        return "c_" + fingerprint([scope, "url", url])[:32]
    return None


def history_path(root: Path, track: str) -> Path:
    return root / "tracks" / track / "candidate_review_history.json"


def load_history(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "candidates": {}}
    history = read_json_payload(path)
    if history.get("schema_version") != SCHEMA_VERSION or not isinstance(history.get("candidates"), dict):
        raise ValueError(f"Invalid candidate review history at {path}")
    return history


def review_paths(root: Path, track: str, run_id: str) -> tuple[Path, Path]:
    directory = root / "artifacts" / "reviews" / track
    return directory / f"{run_id}.json", directory / f"{run_id}.receipt.json"


def project_source(source: dict, history: dict, criteria: str, run_id: str) -> dict:
    candidates = source["candidates"]
    identities = [stable_candidate_id(source, candidate) for candidate in candidates]
    occurrences = Counter(identities)
    queued = []
    counts = {"queued": 0, "skipped": 0, "deferred": 0}
    for index, (candidate, candidate_id) in enumerate(zip(candidates, identities), start=1):
        if candidate_id is None or occurrences[candidate_id] > 1:
            candidate_id = f"run-{run_id}-{source['source_id']}-{index}"
        previous = history.get(candidate_id, {})
        status = previous.get("status")
        if (status in {"reviewed", "deferred"} and previous.get("criteria") == criteria
                and previous.get("evidence") == evidence_fingerprint(candidate)):
            counts["deferred" if status == "deferred" else "skipped"] += 1
            continue
        queued.append({**candidate, "candidate_id": candidate_id})
    counts["queued"] = len(queued)
    return {**source, "candidates": queued, "review_counts": counts}


def prepare(root: Path, track: str, date: str, discovery_path: Path, *, after: Path | None = None) -> tuple[str, str]:
    if after is not None and discovery_path.stat().st_mtime_ns <= after.stat().st_mtime_ns:
        raise ValueError("Discovery artifact predates the scheduled attempt")
    snapshot = read_json_payload(discovery_path)
    if (snapshot.get("schema_version") != 1 or snapshot.get("mode") != "discover"
            or snapshot.get("track") != track or snapshot.get("today") != date
            or not isinstance(snapshot.get("sources"), list)):
        raise ValueError("Discovery artifact does not match the scheduled track and date")

    source_ids = set()
    for source in snapshot["sources"]:
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in source_ids:
            raise ValueError("Discovery artifact needs unique source IDs")
        source_ids.add(source_id)
        if not isinstance(source.get("candidates"), list):
            raise ValueError(f"Discovery artifact is missing candidates for {source_id}")

    run_id = uuid4().hex
    prepared_at_ns = time.time_ns()
    history = load_history(history_path(root, track))["candidates"]
    criteria = criteria_fingerprint(root, track)
    sources = [project_source(source, history, criteria, run_id) for source in snapshot["sources"]]
    totals = {key: sum(source["review_counts"][key] for source in sources)
              for key in ("queued", "skipped", "deferred")}
    artifact = {
        **snapshot,
        "mode": "candidate_review",
        "run_id": run_id,
        "prepared_at_ns": prepared_at_ns,
        "criteria_fingerprint": criteria,
        "previous_digest_fingerprint": file_fingerprint(digest_artifact_path(track, date, root)),
        "review_counts": totals,
        "sources": sources,
    }
    review_path, _ = review_paths(root, track, run_id)
    write_json_atomic(review_path, artifact)
    print(f"Candidate review counts: {totals}", file=sys.stderr)
    return run_id, sha256(review_path.read_bytes()).hexdigest()


def receipt_ids(batch: dict, field: str, available: dict) -> set[str]:
    ids = batch.get(field, [])
    if not isinstance(ids, list) or any(not isinstance(cid, str) or cid not in available for cid in ids):
        raise ValueError(f"Invalid or unknown candidate ID in {field}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate candidate ID in {field}")
    return set(ids)


def acknowledged_candidates(review: dict, receipt: dict) -> dict:
    if receipt.get("run_id") != review["run_id"]:
        raise ValueError("Receipt run ID does not match the review artifact")
    if set(receipt) != {"run_id", "digest_unchanged", "batches"} or type(receipt["digest_unchanged"]) is not bool:
        raise ValueError("Invalid candidate review receipt fields")
    if not isinstance(receipt["batches"], list):
        raise ValueError("Receipt batches must be a list")

    sources = {source["source_id"]: source for source in review["sources"]}
    acknowledged = {}
    for batch in receipt["batches"]:
        if (not isinstance(batch, dict) or not isinstance(batch.get("source_id"), str)
                or type(batch.get("complete")) is not bool
                or set(batch) - {"source_id", "complete", "reviewed", "deferred"}):
            raise ValueError("Invalid candidate review batch fields")
        source = sources.pop(batch["source_id"], None)
        if source is None:
            raise ValueError("Unknown or duplicate source in the review receipt")
        available = {candidate["candidate_id"]: candidate for candidate in source["candidates"]}
        deferred = receipt_ids(batch, "deferred", available)
        if batch["complete"]:
            if "reviewed" in batch:
                raise ValueError("Complete batches must omit the reviewed list")
            reviewed = available.keys() - deferred
        else:
            reviewed = receipt_ids(batch, "reviewed", available)
            if deferred & reviewed:
                raise ValueError("A candidate cannot be both reviewed and deferred")

        for ids, status in ((reviewed, "reviewed"), (deferred, "deferred")):
            for cid in sorted(ids):
                if cid.startswith("c_"):
                    acknowledged[cid] = {
                        "criteria": review["criteria_fingerprint"],
                        "evidence": evidence_fingerprint(available[cid]),
                        "status": status,
                        "prepared_at_ns": review["prepared_at_ns"],
                    }
    return acknowledged


def record_history(path: Path, updates: dict) -> None:
    if not updates:
        return
    with file_lock(path):
        history = load_history(path)
        candidates = history["candidates"]
        # A late acknowledgment cannot overwrite work from a newer input.
        newer = {cid: entry for cid, entry in updates.items()
                 if entry["prepared_at_ns"] > candidates.get(cid, {}).get("prepared_at_ns", 0)}
        if newer:
            candidates.update(newer)
            write_json_atomic(path, history)


def commit(root: Path, track: str, date: str, run_id: str, expected_fingerprint: str) -> None:
    review_path, receipt_path = review_paths(root, track, run_id)
    review_bytes = review_path.read_bytes()
    if sha256(review_bytes).hexdigest() != expected_fingerprint:
        raise ValueError("Review artifact changed after preparation")
    review = json.loads(review_bytes)
    receipt = read_json_payload(receipt_path)
    updates = acknowledged_candidates(review, receipt)
    if updates and review["criteria_fingerprint"] != criteria_fingerprint(root, track):
        raise ValueError("Review criteria changed during the scheduled attempt")

    digest_path = digest_artifact_path(track, date, root)
    draft_path = review_path.with_suffix(".digest.json")
    with file_lock(digest_path):
        current = file_fingerprint(digest_path)
        previous = review["previous_digest_fingerprint"]
        if receipt["digest_unchanged"]:
            if current is None or current != previous or draft_path.exists():
                raise ValueError("Receipt requires an unchanged existing digest and no draft")
            digest = read_json_payload(digest_path)
        else:
            digest = read_json_payload(draft_path)
            if current != previous and (current is None or digest != read_json_payload(digest_path)):
                raise ValueError("Daily digest changed during the scheduled attempt")

        normalize_digest_payload(digest, expected_track=track, expected_date=date)
        if not receipt["digest_unchanged"] and current == previous:
            if current is not None:
                existing_runs = read_json_payload(digest_path).get("runs")
                draft_runs = digest["runs"]
                if not existing_runs or draft_runs[:-1] != existing_runs or draft_runs[-1]["kind"] != "update":
                    raise ValueError("Same-day draft must preserve all existing runs and append one update")
            write_json_atomic(digest_path, digest)
        record_history(history_path(root, track), updates)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--track", required=True)
    parser.add_argument("--date", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--discovery", type=Path, required=True)
    prepare_parser.add_argument("--after", type=Path)
    commit_parser = commands.add_parser("commit")
    commit_parser.add_argument("--run-id", required=True)
    commit_parser.add_argument("--fingerprint", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(*prepare(args.root, args.track, args.date, args.discovery, after=args.after))
        else:
            commit(args.root, args.track, args.date, args.run_id, args.fingerprint)
    except (OSError, ValueError, AttributeError, TypeError, KeyError) as exc:
        print(f"candidate_reviews.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
