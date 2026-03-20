#!/bin/bash
set -euo pipefail

TODAY_STAMP="$(date +%F)"
DIGEST="/Users/jvdh/Documents/job-agent/tracks/core_crypto/digests/$TODAY_STAMP.md"
GRAPH_DIR="/Users/jvdh/Documents/logseq"
JOURNAL_DIR="$GRAPH_DIR/journals"
PAGES_DIR="$GRAPH_DIR/pages"

TODAY="$(date +%Y_%m_%d)"
STAMP="$(date +%Y-%m-%d)"
JOURNAL_FILE="$JOURNAL_DIR/$TODAY.md"
PAGE_NAME="Job Digest $STAMP"
PAGE_FILE="$PAGES_DIR/$PAGE_NAME.md"

if [[ ! -f "$DIGEST" ]]; then
  exit 0
fi

{
  echo "[[job digest]]"
  echo
  cat "$DIGEST"
} > "$PAGE_FILE"

if ! grep -Fqx -- "- New [[${PAGE_NAME}]]" "$JOURNAL_FILE" 2>/dev/null; then
  {
    echo
    echo "- New [[${PAGE_NAME}]]"
  } >> "$JOURNAL_FILE"
fi
