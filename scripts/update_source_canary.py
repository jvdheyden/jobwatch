#!/usr/bin/env python3
"""Refresh a source-quality canary for a configured track source."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from source_config import (
    SourceConfigError,
    load_sources_config,
    load_source_state,
    mutate_source_state,
    slugify_source_id,
)


from source_evidence import (
    EvidenceError, EVIDENCE_MAX_BYTES, canary_id, check_posting_availability, matches_posting,
    stored_canaries, register_canaries, normalize_canaries, normalize_references, merge_references,
)
from setup_contracts import normalize_track_slug, read_json_limited
from probe_career_source import probe

ROOT = Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))


def source_slug(source: str) -> str:
    return slugify_source_id(source)


def default_discovery_output(root: Path, track: str, source: str, today: str) -> Path:
    return root / "artifacts" / "evals" / track / source_slug(source) / f"{today}.canary_discovery.json"


def find_source(config: dict[str, Any], source_query: str) -> dict[str, Any]:
    wanted = source_query.lower()
    for source in config["sources"]:
        if source["name"].lower() == wanted or source["id"].lower() == wanted:
            return source
    raise SourceConfigError(f"source {source_query!r} not found in track {config['track']!r}")


def load_candidates(path: Path, source_name: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    for source_payload in payload.get("sources", []):
        if str(source_payload.get("source", "")).lower() == source_name.lower():
            candidates = source_payload.get("candidates", [])
            if isinstance(candidates, list):
                return [item for item in candidates if isinstance(item, dict)]
    return []


def candidate_score(candidate: dict[str, Any], source_url: str) -> tuple[int, str, str]:
    title = str(candidate.get("title") or "").strip()
    url = str(candidate.get("url") or "").strip()
    lowered_url = url.lower()
    score = 0
    if title:
        score += 2
    if url and url != source_url:
        score += 2
    if any(marker in lowered_url for marker in ("/job", "jobs/", "jobid", "requisition", "posting", "apply")):
        score += 2
    if str(candidate.get("notes") or "").strip():
        score += 1
    return (-score, title.lower(), url)


def pick_canary(candidates: list[dict[str, Any]], source_url: str) -> dict[str, str] | None:
    usable = [
        candidate
        for candidate in candidates
        if str(candidate.get("title") or "").strip() and str(candidate.get("url") or "").strip()
    ]
    if not usable:
        return None
    selected = sorted(usable, key=lambda item: candidate_score(item, source_url))[0]
    return {
        "title": str(selected.get("title") or "").strip(),
        "url": str(selected.get("url") or "").strip(),
    }


def append_canary_history(integration: dict[str, Any], old_canary: Any, today: str, reason: str) -> None:
    if not isinstance(old_canary, dict):
        return
    title = str(old_canary.get("title") or "").strip()
    url = str(old_canary.get("url") or "").strip()
    if not title and not url:
        return
    history = integration.get("canary_history")
    if not isinstance(history, list):
        history = []
    archived = dict(old_canary)
    archived["replaced_at"] = today
    archived["reason"] = reason
    history.append(archived)
    integration["canary_history"] = history[-100:]


def run_discovery(root: Path, track: str, source_name: str, today: str, output: Path) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(root / "scripts" / "discover_jobs.py"),
        "--track",
        track,
        "--source",
        source_name,
        "--today",
        today,
        "--output",
        str(output),
        "--pretty",
    ]
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(command, text=True, capture_output=True, cwd=root, env=env, timeout=120)


def _context(root: Path, track: str, source_query: str):
    directory = root / 'tracks' / normalize_track_slug(track)
    config = load_sources_config(directory / 'sources.json', track)
    return directory, config, find_source(config, source_query)


def register_evidence(*, root: Path, track: str, source_query: str, payload: dict) -> dict:
    if set(payload) - {'canaries', 'reference_jobs'}:
        raise EvidenceError('registration accepts only canaries and reference_jobs')
    directory, config, source = _context(root, track, source_query)
    canaries = normalize_canaries(payload.get('canaries', []))
    references = normalize_references(payload.get('reference_jobs', []))
    from source_evidence import load_references
    known_references = {r['id']: r for r in [*load_references(directory / 'reference_jobs.json', track), *references]}
    for reference in references:
        if reference['source_id'] not in {None, source['id']}:
            raise EvidenceError('reference source does not match registration target')
    for canary in canaries:
        if canary['source_id'] != source['id']:
            raise EvidenceError('canary source does not match registration target')
        if canary['reference_job_id']:
            reference = known_references.get(canary['reference_job_id'])
            if not reference or reference['source_id'] != source['id'] or not matches_posting(reference, canary):
                raise EvidenceError('canary does not match an associated reference')
    def mutate(state):
        entry = state.setdefault(source['id'], {'last_checked': None})
        register_canaries(entry.setdefault('integration', {}), canaries, source['id'])
    mutate(load_source_state(directory / 'source_state.json', track))
    if references:
        merge_references(directory / 'reference_jobs.json', track, references)
    mutate_source_state(directory / 'source_state.json', track, [s['id'] for s in config['sources']], mutate)
    return {'status': 'registered', 'source': source['name'], 'canary_ids': [c['id'] for c in canaries]}


def _apply_observations(integration: dict, original: list[dict], observations: dict, today: str) -> list[dict]:
    retained = []
    checks = integration.setdefault('canary_checks', {})
    for canary in original:
        observation = observations.get(canary['id'])
        if not observation:
            retained.append(canary)
            continue
        checks[canary['id']] = observation
        if observation['availability'] == 'expired':
            archived = dict(canary, **observation)
            append_canary_history(integration, archived, today, 'confirmed_expiration')
        elif observation['availability'] == 'live':
            retained.append(dict(canary, **observation))
        else:
            retained.append(canary)  # Inconclusive checks never erase prior evidence.
    return retained


def review_canary(*, root: Path, track: str, source_query: str, evidence_id: str, observation: dict, today: str) -> dict:
    directory, config, source = _context(root, track, source_query)
    def mutate(state):
        entry = state.setdefault(source['id'], {'last_checked': None})
        integration = entry.setdefault('integration', {})
        current = stored_canaries(integration, source['id'])
        canary = next((c for c in current if c['id'] == evidence_id), None)
        if canary is None:
            raise EvidenceError('unknown canary id')
        reviewed = normalize_canaries([dict(canary, **observation, checked_on=today, expires_on='')])[0]
        integration['canaries'] = _apply_observations(integration, current, {evidence_id: reviewed}, today)
        integration['status'] = 'pending'
        integration['verification'] = 'pending'
        integration.pop('last_attempted', None)
    mutate_source_state(directory / 'source_state.json', track, [s['id'] for s in config['sources']], mutate)
    return {'status': 'reviewed', 'canary_id': evidence_id, 'availability': observation['availability']}


def refresh_canary(*, root: Path, track: str, source_query: str, today: str,
                   discovery_output: Path | None = None) -> tuple[bool, dict[str, Any]]:
    directory, config, source = _context(root, track, source_query)
    source_id, source_name = source['id'], source['name']
    state_path = directory / 'source_state.json'
    original = stored_canaries(load_source_state(state_path, track).get(source_id, {}).get('integration', {}), source_id)
    output = discovery_output or default_discovery_output(root, track, source_name, today)
    discovery = run_discovery(root, track, source_name, today, output)
    if discovery.returncode != 0:
        return False, {'status': 'discovery_failed', 'source': source_name, 'output': str(output), 'stderr': discovery.stderr.strip()}
    artifact = json.loads(output.read_text())
    coverage = next((s for s in artifact.get('sources', []) if s.get('source') == source_name), {})
    if coverage.get('status') != 'complete':
        return False, {'status': 'incomplete_discovery', 'source': source_name, 'output': str(output), 'limitations': coverage.get('limitations', [])}
    candidates = load_candidates(output, source_name)
    observations = {}
    missing_live = []
    for canary in original:
        present = any(matches_posting(c, canary) for c in candidates)
        if not present or canary.get('availability') != 'live' or not canary.get('expires_on') or canary['expires_on'] < today:
            observations[canary['id']] = check_posting_availability(canary, today=today)
            if observations[canary['id']]['availability'] == 'live' and not present and canary.get('scope') == 'in_scope':
                missing_live.append(canary['id'])
    # Rotation requires independently confirmed closure of every prior active
    # posting. A live/unknown missing canary cannot be silently replaced.
    may_acquire = not original or all(observations.get(c['id'], {}).get('availability') == 'expired' for c in original)
    selected = None
    if may_acquire:
        report = probe(source['url'], source_name=source_name, terms=config['track_terms'])
        for suggestion in report['candidate_canaries'][:3]:
            observation = check_posting_availability(suggestion, today=today)
            if observation['availability'] == 'live':
                selected = dict(suggestion, **observation, provenance='independent_probe')
                break
        if selected is None:
            suggestion = pick_canary(candidates, source['url'])
            if suggestion:
                selected = dict(suggestion, provenance='discovery_output', availability='unknown', checked_on='',
                                expires_on='', evidence_url=source['url'], evidence_note='Regression suggestion selected from discovery; independent availability and scope review required.')
        if selected:
            selected = normalize_canaries([dict(selected, id=canary_id(selected['url']), source_id=source_id, scope='unknown')])[0]
    def mutate(state):
        entry = state.setdefault(source_id, {'last_checked': None})
        integration = entry.setdefault('integration', {})
        if stored_canaries(integration, source_id) != original:
            raise EvidenceError('canaries changed during refresh; retry with current evidence')
        retained = _apply_observations(integration, original, observations, today)
        if selected:
            retained.append(selected)
        integration['canaries'] = normalize_canaries(retained)
        integration['status'] = 'pending'
        integration['verification'] = 'failed' if missing_live else 'inconclusive' if any(o['availability'] == 'unknown' for o in observations.values()) else 'pending'
        integration.pop('last_attempted', None)
    # A completely failed acquisition with no prior evidence has nothing to save.
    if original or selected:
        mutate_source_state(state_path, track, [s['id'] for s in config['sources']], mutate)
    status = ('missing_live' if missing_live else 'inconclusive' if any(o['availability'] == 'unknown' for o in observations.values())
              else 'suggested' if selected else 'retained' if original and not may_acquire else 'missing')
    return status in {'suggested', 'retained'}, {'status': status, 'source': source_name, 'output': str(output),
        'canary': selected, 'checks': observations, 'missing_live_ids': missing_live, 'candidates_seen': len(candidates)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--track', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--today', default=date.today().isoformat())
    parser.add_argument('--output', help='Discovery output path for refresh')
    parser.add_argument('--pretty', action='store_true')
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument('--register', help='Bounded JSON object with canaries and/or reference_jobs')
    operation.add_argument('--review-canary', help='Existing canary ID to review, or retire after confirmed expiration')
    parser.add_argument('--availability', choices=['live', 'expired', 'unknown'])
    parser.add_argument('--scope', choices=['in_scope', 'out_of_scope', 'unknown'])
    parser.add_argument('--evidence-url')
    parser.add_argument('--evidence-note')
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        date.fromisoformat(args.today)
        if args.register:
            payload = register_evidence(root=ROOT, track=args.track, source_query=args.source,
                payload=read_json_limited(Path(args.register), EVIDENCE_MAX_BYTES, 'evidence'))
            ok = True
        elif args.review_canary:
            if not args.availability or not args.evidence_url or not args.evidence_note:
                raise EvidenceError('review requires availability, evidence-url and evidence-note')
            observation = {'availability': args.availability, 'evidence_url': args.evidence_url, 'evidence_note': args.evidence_note}
            if args.scope:
                observation['scope'] = args.scope
            payload = review_canary(root=ROOT, track=args.track, source_query=args.source, evidence_id=args.review_canary,
                                    observation=observation, today=args.today)
            ok = True
        else:
            ok, payload = refresh_canary(root=ROOT, track=args.track, source_query=args.source, today=args.today,
                                        discovery_output=Path(args.output) if args.output else None)
        print(json.dumps(payload, indent=2 if args.pretty else None))
        return 0 if ok else 1
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(2, f'update_source_canary.py: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
