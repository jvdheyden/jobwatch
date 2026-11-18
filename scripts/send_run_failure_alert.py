#!/usr/bin/env python3
"""Email an alert when a track run fails before its digest is delivered."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import os
import re
import sys

from digest_email import DigestEmailError, RenderedDigestEmail
from digest_json import track_display_name
from runtime_env import RuntimeEnvError, apply_runtime_env
from send_digest_email import build_email_message, load_smtp_config, send_email_message


LOG_TAIL_LINES = 15
AUTH_FAILURE_MARKERS = (
    "OAuth access token has expired",
    '"error":"authentication_failed"',
    '"api_error_status":401',
)
DELIVERED_RE = re.compile(r"\] Delivery phase finished successfully: (\S+)$")
DELIVERY_FAILED_RE = re.compile(r"\] Delivery phase failed: (\S+) status")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track name under tracks/")
    parser.add_argument("--date", default=date.today().isoformat(), help="Run date in YYYY-MM-DD format")
    parser.add_argument("--status", type=int, required=True, help="Exit status of the failed run")
    parser.add_argument("--log-file", required=True, help="Path to the run log")
    parser.add_argument(
        "--log-offset",
        type=int,
        default=0,
        help="Byte offset where the failed attempt starts in the run log, which collects every attempt of the day",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the rendered email instead of sending it")
    return parser


def read_attempt_log(log_path: Path, offset: int) -> str:
    """Return the log written by the failed attempt only, not earlier retries."""
    try:
        with log_path.open("rb") as handle:
            data = handle.read()
    except OSError:
        return ""
    if 0 < offset <= len(data):
        data = data[offset:]
    return data.decode(errors="replace")


def render_failure_alert(
    track: str, run_date: str, status: int, log_path: Path, log_offset: int = 0
) -> RenderedDigestEmail:
    log_text = read_attempt_log(log_path, log_offset)
    log_lines = log_text.splitlines()

    # Delivery targets run in order, so earlier ones may have succeeded.
    delivered = [match.group(1) for line in log_lines if (match := DELIVERED_RE.search(line))]
    failed = [match.group(1) for line in log_lines if (match := DELIVERY_FAILED_RE.search(line))]
    summary = f"The {track} run for {run_date} failed with exit status {status}"
    if delivered:
        summary += f". The digest was delivered by {', '.join(delivered)}"
        summary += f", but {', '.join(failed)} delivery failed." if failed else "."
    else:
        summary += ", so no digest was delivered."
    lines = [summary, ""]
    if any(marker in log_text for marker in AUTH_FAILURE_MARKERS):
        lines += [
            "Likely cause: the agent CLI could not authenticate (HTTP 401).",
            "Re-authenticate (for Claude: `claude auth login`), then rerun:",
            f"  bash scripts/run_track.sh --track {track} --delivery email",
            "",
        ]
    agent_error = _last_agent_error(log_lines)
    if agent_error:
        lines += ["Agent error:", f"  {agent_error}", ""]
    runner_lines = [line for line in log_lines if line.startswith("[")][-LOG_TAIL_LINES:]
    if runner_lines:
        lines += ["Last runner log lines:", *runner_lines, ""]
    lines.append(f"Full log: {log_path}")

    return RenderedDigestEmail(
        subject=f"{track_display_name(track)} run failed ({run_date})",
        body="\n".join(lines) + "\n",
    )


def _last_agent_error(log_lines: list[str]) -> str | None:
    for line in reversed(log_lines):
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result" and event.get("is_error"):
            result = event.get("result")
            return str(result) if result else None
    return None


def main() -> int:
    args = build_parser().parse_args()
    try:
        apply_runtime_env(load_secrets=not args.dry_run)
    except RuntimeEnvError as exc:
        print(f"send_run_failure_alert.py: {exc}", file=sys.stderr)
        return 1

    rendered = render_failure_alert(args.track, args.date, args.status, Path(args.log_file), args.log_offset)
    if args.dry_run:
        print(f"Subject: {rendered.subject}")
        print()
        print(rendered.body, end="")
        return 0

    try:
        config = load_smtp_config(os.environ)
        message = build_email_message(
            rendered,
            sender=config.sender,
            recipients=config.recipients,
            cc_recipients=config.cc_recipients,
        )
        send_email_message(config, message)
    except DigestEmailError as exc:
        print(f"send_run_failure_alert.py: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"send_run_failure_alert.py: SMTP send failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
