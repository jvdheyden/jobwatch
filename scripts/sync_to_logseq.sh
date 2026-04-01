#!/bin/bash
set -euo pipefail

TRACK=""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --track)
      TRACK="${2:?missing value for --track}"
      shift 2
      ;;
    *)
      echo "Usage: $0 --track <slug>" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$TRACK" ]]; then
  echo "Usage: $0 --track <slug>" >&2
  exit 2
fi

ROOT="${JOB_AGENT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
TODAY_STAMP="${JOB_AGENT_TODAY:-$(date +%F)}"
DIGEST="$ROOT/tracks/$TRACK/digests/$TODAY_STAMP.md"
RANKED_OVERVIEW="$ROOT/tracks/$TRACK/ranked_overview.md"
GRAPH_DIR="${LOGSEQ_GRAPH_DIR:-/Users/jvdh/Documents/logseq}"
JOURNAL_DIR="$GRAPH_DIR/journals"
PAGES_DIR="$GRAPH_DIR/pages"

track_display_name() {
  python3 - "$1" <<'PY'
import re
import sys
track = sys.argv[1]
print(" ".join(part.capitalize() for part in re.split(r"[_-]+", track) if part))
PY
}

TRACK_DISPLAY_NAME="$(track_display_name "$TRACK")"
TODAY="${JOB_AGENT_JOURNAL_DATE:-$(date +%Y_%m_%d)}"
STAMP="$TODAY_STAMP"
JOURNAL_FILE="$JOURNAL_DIR/$TODAY.md"
PAGE_NAME="$TRACK_DISPLAY_NAME Job Digest $STAMP"
PAGE_FILE="$PAGES_DIR/$PAGE_NAME.md"
RANKED_OVERVIEW_PAGE_FILE="$PAGES_DIR/$TRACK_DISPLAY_NAME Ranked Overview.md"

mkdir -p "$JOURNAL_DIR" "$PAGES_DIR"

if [[ -f "$RANKED_OVERVIEW" ]]; then
  cp "$RANKED_OVERVIEW" "$RANKED_OVERVIEW_PAGE_FILE"
fi

if [[ ! -f "$DIGEST" ]]; then
  exit 0
fi

{
  cat "$DIGEST"
} > "$PAGE_FILE"

if ! grep -Fqx -- "- New [[${PAGE_NAME}]]" "$JOURNAL_FILE" 2>/dev/null; then
  {
    echo "- New [[${PAGE_NAME}]]"
  } >> "$JOURNAL_FILE"
fi
