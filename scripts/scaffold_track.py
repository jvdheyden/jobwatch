#!/usr/bin/env python3
"""Create one new track deterministically from a validated setup artifact."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from discover.track_filters import normalize_track_match_rules_payload
from setup_contracts import SetupContractError, load_setup, normalize_track_slug
from source_config import (
    load_sources_config,
    normalize_sources_payload,
    render_sources_markdown,
    source_state_payload,
)
from update_ranked_overview import write_ranked_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Validated setup.json")
    parser.add_argument("--root", help=argparse.SUPPRESS)
    return parser


def _bullets(items: list[str], *, empty: str = "none specified yet") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def _render_templates(root: Path, setup: dict[str, Any]) -> dict[str, str]:
    track = setup["track"]
    selected = setup["selected_sources"]
    slug = track["slug"]
    sources_payload = normalize_sources_payload(
        {
            "schema_version": 1,
            "track": slug,
            "track_terms": selected["track_terms"],
            "sources": selected["sources"],
        },
        slug,
    )
    match_rules_payload = {
        "schema_version": 1,
        "track": slug,
        "rules": selected["match_rules"],
    }
    if selected["match_rules"]:
        normalize_track_match_rules_payload(match_rules_payload, slug)
    state_payload = source_state_payload(slug, [source["id"] for source in sources_payload["sources"]], {})

    prefs_template = (root / "shared" / "templates" / "track_prefs.md").read_text()
    prefs = (
        prefs_template.replace("{track_display_name}", track["display_name"])
        .replace("{goals_or_role_types}", _bullets(track["goals_or_role_types"]))
        .replace("{keep_only_keywords}", _bullets(track["keep_only_keywords"]))
        .replace("{constraints_or_red_flags}", _bullets(track["constraints_or_red_flags"]))
        .replace("{geography_or_remote_preferences}", _bullets(track["geography_or_remote_preferences"]))
    )
    agents_template = (root / "shared" / "templates" / "track_AGENTS.md").read_text()
    agents = (
        agents_template.replace("{track_display_name}", track["display_name"])
        .replace("{track_slug}", slug)
        .replace("{user_name}", setup["profile"]["user_name"])
        .replace("{fit_language}", track["fit_language"])
    )
    for placeholder in (
        "{track_display_name}",
        "{goals_or_role_types}",
        "{keep_only_keywords}",
        "{constraints_or_red_flags}",
        "{geography_or_remote_preferences}",
        "{track_slug}",
        "{user_name}",
        "{fit_language}",
    ):
        if placeholder in prefs or placeholder in agents:
            raise SetupContractError(f"unreplaced scaffold placeholder: {placeholder}")
    rendered = {
        "prefs.md": prefs,
        "sources.json": json.dumps(sources_payload, indent=2, ensure_ascii=False) + "\n",
        "source_state.json": json.dumps(state_payload, indent=2, ensure_ascii=False) + "\n",
        "sources.md": render_sources_markdown(sources_payload),
        "AGENTS.md": agents,
        "CLAUDE.md": "@AGENTS.md\n",
        "GEMINI.md": "@AGENTS.md\n",
        "seen_jobs.json": json.dumps(
            {"schema_version": 1, "track": slug, "jobs": []}, indent=2, ensure_ascii=False
        )
        + "\n",
    }
    if selected["match_rules"]:
        rendered["match_rules.json"] = json.dumps(match_rules_payload, indent=2, ensure_ascii=False) + "\n"
    return rendered


def scaffold_track(setup_path: Path, *, root: Path) -> dict[str, Any]:
    setup = load_setup(setup_path)
    slug = normalize_track_slug(setup["track"]["slug"])
    if not setup["selected_sources"]["sources"]:
        raise SetupContractError("setup selected_sources.sources must contain at least one confirmed source")
    tracks_root = root / "tracks"
    final_dir = tracks_root / slug
    ranked_state = root / "shared" / "ranked_jobs" / f"{slug}.json"
    if final_dir.exists():
        raise SetupContractError(f"refusing to overwrite existing track: {final_dir}")
    if ranked_state.exists():
        raise SetupContractError(f"refusing to overwrite existing ranked state: {ranked_state}")
    rendered = _render_templates(root, setup)
    tracks_root.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{slug}.staging-", dir=tracks_root))
    committed = False
    try:
        for relative, content in rendered.items():
            (staging_dir / relative).write_text(content)
        (staging_dir / "digests").mkdir()
        load_sources_config(staging_dir / "sources.json", slug)
        if (staging_dir / "match_rules.json").exists():
            normalize_track_match_rules_payload(
                json.loads((staging_dir / "match_rules.json").read_text()), slug, field="staged match_rules.json"
            )
        if final_dir.exists() or ranked_state.exists():
            raise SetupContractError("track or ranked state appeared while scaffolding; refusing to overwrite it")
        staging_dir.rename(final_dir)
        committed = True
    finally:
        if not committed and staging_dir.exists():
            shutil.rmtree(staging_dir)

    recovery = f"./.venv/bin/python scripts/update_ranked_overview.py --track {slug}"
    try:
        if ranked_state.exists():
            raise SetupContractError(f"ranked state appeared after track commit: {ranked_state}")
        state_path, overview_path, _ = write_ranked_outputs(slug, root=root)
    except Exception as exc:
        return {
            "status": "incomplete",
            "track": slug,
            "track_path": str(final_dir),
            "incomplete_output": str(ranked_state),
            "error": str(exc),
            "recovery_command": recovery,
        }
    return {
        "status": "created",
        "track": slug,
        "track_path": str(final_dir),
        "ranked_state_path": str(state_path),
        "ranked_overview_path": str(overview_path),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root or os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1])).resolve()
    try:
        result = scaffold_track(Path(args.input), root=root)
    except (OSError, SetupContractError, ValueError) as exc:
        print(f"scaffold_track.py: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0 if result["status"] == "created" else 1


if __name__ == "__main__":
    raise SystemExit(main())
