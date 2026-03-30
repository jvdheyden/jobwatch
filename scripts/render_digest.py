#!/usr/bin/env python3
"""Render a markdown digest from a structured daily digest artifact."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import shutil
import sys

from digest_json import (
    ROOT,
    DigestValidationError,
    digest_artifact_path,
    digest_latest_artifact_path,
    load_digest_payload,
    render_digest_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", default="core_crypto", help="Track name under tracks/")
    parser.add_argument("--date", default=date.today().isoformat(), help="Digest date in YYYY-MM-DD format")
    parser.add_argument("--input", dest="input_path", help="Optional explicit input JSON path")
    parser.add_argument("--output", dest="output_path", help="Optional explicit markdown output path")
    parser.add_argument("--latest-output", dest="latest_output_path", help="Optional explicit latest JSON copy path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input_path) if args.input_path else digest_artifact_path(args.track, args.date)
    output_path = Path(args.output_path) if args.output_path else ROOT / "tracks" / args.track / "digests" / f"{args.date}.md"
    latest_output_path = Path(args.latest_output_path) if args.latest_output_path else digest_latest_artifact_path(args.track)

    try:
        payload = load_digest_payload(input_path, expected_track=args.track, expected_date=args.date)
    except (OSError, DigestValidationError) as exc:
        print(f"render_digest.py: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    latest_output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_digest_markdown(payload))
    shutil.copyfile(input_path, latest_output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
