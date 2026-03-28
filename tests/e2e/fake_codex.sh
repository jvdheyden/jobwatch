#!/bin/bash
set -euo pipefail

ROOT="${JOB_AGENT_ROOT:-}"
TRACK="${JOB_AGENT_TRACK:-}"
TODAY="${JOB_AGENT_TODAY:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -C)
      ROOT="${2:?missing value for -C}"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

if [[ -z "$ROOT" || -z "$TRACK" || -z "$TODAY" ]]; then
  echo "fake_codex.sh requires JOB_AGENT_ROOT, JOB_AGENT_TRACK, and JOB_AGENT_TODAY" >&2
  exit 2
fi

cat >/dev/null

python3 - "$ROOT" "$TRACK" "$TODAY" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
track = sys.argv[2]
today = sys.argv[3]
artifact_path = root / "artifacts" / "discovery" / track / f"{today}.json"
digest_path = root / "tracks" / track / "digests" / f"{today}.md"

payload = json.loads(artifact_path.read_text())
candidates = [
    candidate
    for source in payload.get("sources", [])
    for candidate in source.get("candidates", [])
]
if not candidates:
    raise SystemExit(f"no candidates in {artifact_path}")

candidate = candidates[0]
title = candidate.get("title", "unknown")
company = candidate.get("employer", "unknown")
url = candidate.get("url", "")
location = candidate.get("location", "unknown")
fit_score = 8.4 if "crypt" in title.lower() else 6.0

digest_path.parent.mkdir(parents=True, exist_ok=True)
digest_path.write_text(
    "\n".join(
        [
            f"# {track.replace('_', ' ').title()} Digest",
            "",
            "## Strong matches",
            "",
            f"### {title} — {company}",
            f"- Link: {url}",
            f"- Fit score: {fit_score}/10",
            f"- Location: {location}",
            "- Reason: Local fixture role used to validate the generic runner.",
            "",
            "## Coverage",
            "",
            f"- Discovery artifact: `{artifact_path.relative_to(root)}`",
            f"- Enumerated candidates: {len(candidates)}",
            "",
        ]
    )
    + "\n"
)

subprocess.run(
    ["python3", str(root / "scripts" / "update_ranked_overview.py"), "--track", track],
    check=True,
    cwd=root,
)
PY
