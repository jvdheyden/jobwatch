#!/usr/bin/env python3
"""Prepare bounded portfolio discovery and register reviewed sources without replacing a track."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from setup_contracts import (load_setup, normalize_setup, normalize_track_slug, read_json_limited,
                             write_setup, _normalize_source_record, SETUP_MAX_BYTES)
from source_config import (load_sources_config, file_lock, write_json_atomic, mutate_source_state,
                           render_sources_markdown)
from source_evidence import (EvidenceError, identity_url, load_references,
                             reference_payload, register_canaries)


def prepare(root: Path, track: str, brief: Path, output: Path) -> dict:
    track = normalize_track_slug(track)
    setup = load_setup(brief)
    if setup['track']['slug'] != track:
        raise EvidenceError('brief belongs to another track')
    directory = root / 'tracks' / track
    config = load_sources_config(directory / 'sources.json', track)
    references = {r['id']: r for r in load_references(directory / 'reference_jobs.json', track)}
    for reference in setup.get('reference_jobs', []):
        if reference['id'] in references and references[reference['id']] != reference:
            raise EvidenceError('brief conflicts with a stored reference job')
        references[reference['id']] = reference
    setup['reference_jobs'] = list(references.values())
    setup['existing_sources'] = config['sources']
    setup['selected_sources'] = {'track_terms': config['track_terms'], 'sources': [], 'match_rules': []}
    return write_setup(output, setup)


def register(root: Path, track: str, *, setup: dict | None = None, source: dict | None = None) -> dict:
    track = normalize_track_slug(track)
    directory = root / 'tracks' / track
    if setup is not None:
        setup = normalize_setup(setup)
        if setup['track']['slug'] != track:
            raise EvidenceError('selection belongs to another track')
        selected = setup['selected_sources']
        if selected['match_rules']:
            raise EvidenceError('Existing-track match-rule changes require separate explicit reconciliation')
        additions = selected['sources']
        references = setup.get('reference_jobs', [])
        canaries = setup.get('canaries', [])
    else:
        additions = [_normalize_source_record(source, 'source')]
        references, canaries = [], []
    sources_path = directory / 'sources.json'
    # Each file commits atomically under its established lock. All validation
    # precedes writes; retrying the same registration is safe after interruption.
    with file_lock(sources_path):
        config = load_sources_config(sources_path, track)
        existing = {s['id']: s for s in config['sources']}
        added = []
        for record in additions:
            record = dict(record)
            # Portfolio recommendations never replace global retrieval terms.
            # Apply new vocabulary only to the newly registered source.
            if setup and record.get('search_terms', {}).get('mode') != 'override':
                terms = list(dict.fromkeys([*setup['selected_sources']['track_terms'], *record.get('search_terms', {}).get('terms', [])]))
                if terms:
                    record['search_terms'] = {'mode': 'append', 'terms': terms}
            if record['id'] in existing:
                if record != existing[record['id']]:
                    raise EvidenceError(f"Source {record['id']} is already configured differently; reconcile explicitly")
                continue
            if any(identity_url(record['url']) == identity_url(s['url']) or record['name'].casefold() == s['name'].casefold()
                   for s in existing.values()):
                raise EvidenceError(f"Source {record['name']} duplicates a configured source")
            existing[record['id']] = record
            added.append(record['id'])
        source_ids = list(existing)
        supplied_ids = {s['id'] for s in additions}
        for reference in references:
            if reference['source_id'] and reference['source_id'] not in existing:
                raise EvidenceError('reference points to an unconfigured source')
        unselected = [c['id'] for c in canaries if c['source_id'] not in existing]
        references_path = directory / 'reference_jobs.json'
        with file_lock(references_path):
            merged = {r['id']: r for r in load_references(references_path, track)}
            for reference in references:
                old = merged.get(reference['id'])
                # Discovery can resolve an association, but cannot rewrite user calibration.
                if old and any(old[k] != reference[k] for k in ('url', 'title', 'employer', 'relevance')):
                    raise EvidenceError('selection cannot overwrite a supplied reference job')
                merged[reference['id']] = reference
            refs_payload = reference_payload(track, list(merged.values()))
            def update_state(state):
                for sid in source_ids:
                    entry = state.setdefault(sid, {'last_checked': None})
                    evidence = [c for c in canaries if c['source_id'] == sid]
                    if sid in added or evidence or sid in supplied_ids and not entry.get('integration'):
                        integration = entry.setdefault('integration', {'status': 'pending', 'verification': 'unverified'})
                        register_canaries(integration, evidence, sid)
            # Validate state mutations before committing any file.
            from source_config import load_source_state
            update_state(load_source_state(directory / 'source_state.json', track))
            config['sources'] = list(existing.values())
            write_json_atomic(sources_path, config)
            if references:
                write_json_atomic(references_path, refs_payload)
            mutate_source_state(directory / 'source_state.json', track, source_ids, update_state)
        (directory / 'sources.md').write_text(render_sources_markdown(config))
    return {'status': 'registered', 'added_source_ids': added, 'deferred_canary_ids': unselected,
            'seed_outcomes': setup.get('seed_outcomes', []) if setup else []}


def queue_verification(root: Path, track: str, source_queries: list[str] | None) -> dict:
    directory = root / "tracks" / normalize_track_slug(track)
    config = load_sources_config(directory / "sources.json", track)
    selected = []
    for query in source_queries or []:
        matches = [s["id"] for s in config["sources"] if query.casefold() in {s["id"].casefold(), s["name"].casefold()}]
        if not matches:
            raise EvidenceError(f"unknown source: {query}")
        selected.extend(matches)
    if source_queries is None:
        selected = [s["id"] for s in config["sources"]]
    def mutate(state):
        for sid in selected:
            integration = state.setdefault(sid, {"last_checked": None}).setdefault("integration", {})
            integration.update(status="pending", verification="pending")
            integration.pop("last_attempted", None)
    mutate_source_state(directory / "source_state.json", track, [s["id"] for s in config["sources"]], mutate)
    return {"status": "queued", "source_ids": selected}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    project = commands.add_parser('prepare')
    project.add_argument('--track', required=True)
    project.add_argument('--brief', required=True, help='Reviewed bounded setup-format brief')
    project.add_argument('--output', required=True)
    add = commands.add_parser('register')
    add.add_argument('--track', required=True)
    inputs = add.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--setup', help='Reviewed setup artifact after select-sources')
    inputs.add_argument('--source-file', help='One canonical source record')
    queue = commands.add_parser('queue')
    queue.add_argument('--track', required=True)
    scope = queue.add_mutually_exclusive_group(required=True)
    scope.add_argument('--source', action='append', help='Affected source name or ID; repeat to limit the review')
    scope.add_argument('--all', action='store_true', help='Queue the whole portfolio for explicit maintenance')
    args = parser.parse_args()
    root = Path(os.environ.get('JOB_AGENT_ROOT', Path(__file__).resolve().parents[1]))
    try:
        if args.command == 'prepare':
            prepare(root, args.track, Path(args.brief), Path(args.output))
            result = {'status': 'prepared', 'output': args.output}
        elif args.command == 'queue':
            result = queue_verification(root, args.track, args.source)
        else:
            result = register(root, args.track, setup=load_setup(Path(args.setup)) if args.setup else None,
                source=read_json_limited(Path(args.source_file), SETUP_MAX_BYTES, 'source') if args.source_file else None)
        print(json.dumps(result))
        return 0
    except (ValueError, OSError) as exc:
        parser.exit(2, f'curate_sources.py: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
