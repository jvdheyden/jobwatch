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
    -p|--output-format|--approval-mode|--skip-trust)
      # Ignore Gemini-specific flags in fake runner
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

if [[ -z "$ROOT" || -z "$TRACK" || -z "$TODAY" ]]; then
  echo "fake_gemini.sh requires JOB_AGENT_ROOT, JOB_AGENT_TRACK, and JOB_AGENT_TODAY" >&2
  exit 2
fi

# Drain prompt from stdin
cat >/dev/null

# The rest is identical to fake_codex.sh as the business logic of the dummy
# runner (extracting a candidate from discovery and rendering the digest)
# is what we are testing in the e2e workflow.
python3 - "$ROOT" "$TRACK" "$TODAY" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
track = sys.argv[2]
today = sys.argv[3]
artifact_path = root / "artifacts" / "discovery" / track / f"{today}.json"
structured_digest_path = root / "artifacts" / "digests" / track / f"{today}.json"

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

structured_digest_path.parent.mkdir(parents=True, exist_ok=True)
structured_digest_path.write_text(
    json.dumps(
        {
            "schema_version": 1,
            "track": track,
            "date": today,
            "runs": [
                {
                    "kind": "initial",
                    "generated_at": f"{today}T09:00:00+01:00",
                    "executive_summary": "One deterministic fixture role was surfaced to validate the generic runner via Gemini.",
                    "recommended_actions": [
                        "Inspect the rendered markdown output.",
                        "Confirm the overview and Logseq sync use track-derived names.",
                    ],
                    "top_matches": [
                        {
                            "company": company,
                            "title": title,
                            "listing_url": url,
                            "location": location,
                            "source": "Local Test Board",
                            "fit_score": fit_score,
                            "recommendation": "watch",
                            "why_match": [
                                "The title contains cryptography-specific language.",
                                "The fixture is meant to validate the end-to-end workflow.",
                            ],
                            "concerns": [
                                "This is synthetic test data, not a real hiring signal."
                            ],
                        }
                    ],
                    "other_new_roles": [],
                    "filtered_roles": [],
                    "source_notes": [
                        {
                            "source": "Local Test Board",
                            "discovery_mode": "html",
                            "status": "complete",
                            "listing_pages_scanned": 1,
                            "search_terms_tried": ["cryptography"],
                            "result_pages_summary": "local_filter=1",
                            "direct_job_pages_opened": 0,
                            "limitations": [],
                            "note": f"Discovery artifact enumerated {len(candidates)} candidate(s).",
                        }
                    ],
                    "notes_for_next_run": [
                        "Keep this track unscheduled; it is only an integration fixture."
                    ],
                    "discovery_artifacts": [str(artifact_path.relative_to(root))],
                }
            ],
        },
        indent=2,
    )
    + "\n"
)

subprocess.run(
    ["python3", str(root / "scripts" / "render_digest.py"), "--track", track, "--date", today],
    check=True,
    cwd=root,
)

subprocess.run(
    ["python3", str(root / "scripts" / "update_ranked_overview.py"), "--track", track],
    check=True,
    cwd=root,
)
PY
