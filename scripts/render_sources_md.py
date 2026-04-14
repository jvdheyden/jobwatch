#!/usr/bin/env python3
"""Render the read-only Markdown summary for a track source config."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from source_config import SourceConfigError, load_sources_config, render_sources_markdown


ROOT = Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track directory name under tracks/")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    track_dir = ROOT / "tracks" / args.track
    try:
        config = load_sources_config(track_dir / "sources.json", args.track)
    except SourceConfigError as exc:
        print(f"render_sources_md.py: {exc}", file=sys.stderr)
        return 2

    output_path = track_dir / "sources.md"
    output_path.write_text(render_sources_markdown(config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
