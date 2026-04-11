#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENTS_SKILLS_DIR="$ROOT/.agents/skills"
CLAUDE_SKILLS_DIR="$ROOT/.claude/skills"
CHECK_ONLY=0

if [[ $# -gt 1 ]]; then
  echo "Usage: bash scripts/sync_claude_skills.sh [--check]" >&2
  exit 2
fi

if [[ $# -eq 1 ]]; then
  if [[ "$1" == "--check" ]]; then
    CHECK_ONLY=1
  else
    echo "Usage: bash scripts/sync_claude_skills.sh [--check]" >&2
    exit 2
  fi
fi

errors=()
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

expected_skill_file() {
  local skill="$1"
  local source_file="$2"
  local output_file="$3"

  {
    printf '<!-- GENERATED FILE: source of truth is .agents/skills/%s/SKILL.md -->\n' "$skill"
    printf '<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->\n\n'
    cat "$source_file"
  } >"$output_file"
}

for source_file in "$AGENTS_SKILLS_DIR"/*/SKILL.md; do
  [[ -e "$source_file" ]] || continue
  skill="$(basename "$(dirname "$source_file")")"
  destination_dir="$CLAUDE_SKILLS_DIR/$skill"
  destination_file="$destination_dir/SKILL.md"
  expected_file="$tmp_dir/$skill.SKILL.md"

  expected_skill_file "$skill" "$source_file" "$expected_file"

  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    if [[ ! -f "$destination_file" ]]; then
      errors+=("missing mirror: .claude/skills/$skill/SKILL.md")
    elif ! cmp -s "$expected_file" "$destination_file"; then
      errors+=("stale mirror: .claude/skills/$skill/SKILL.md")
    fi
  else
    mkdir -p "$destination_dir"
    if [[ ! -f "$destination_file" ]] || ! cmp -s "$expected_file" "$destination_file"; then
      cp "$expected_file" "$destination_file"
      echo "synced .claude/skills/$skill/SKILL.md"
    fi
  fi
done

if [[ -d "$CLAUDE_SKILLS_DIR" ]]; then
  for mirror_dir in "$CLAUDE_SKILLS_DIR"/*; do
    [[ -d "$mirror_dir" ]] || continue
    skill="$(basename "$mirror_dir")"
    if [[ ! -f "$AGENTS_SKILLS_DIR/$skill/SKILL.md" ]]; then
      errors+=("stale mirror directory: .claude/skills/$skill")
    fi
  done
fi

if [[ ${#errors[@]} -gt 0 ]]; then
  echo "Claude skill mirrors are out of sync:" >&2
  for error in "${errors[@]}"; do
    echo "- $error" >&2
  done
  echo "Run: bash scripts/sync_claude_skills.sh" >&2
  exit 1
fi

echo "Claude skill mirrors are up to date."
