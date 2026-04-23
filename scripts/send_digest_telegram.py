#!/usr/bin/env python3
"""Send a JSON-backed daily job digest to Telegram."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib import error, request

from digest_email import DEFAULT_RANKED_LIMIT, DigestEmailError, load_json_payload, render_digest_email
from digest_json import digest_artifact_path
from runtime_env import RuntimeEnvError, apply_runtime_env


DEFAULT_TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_MESSAGE_LIMIT = 3900


class DigestTelegramError(ValueError):
    """Raised when Telegram digest delivery fails."""


@dataclass(frozen=True)
class TelegramConfig:
    api_base: str
    bot_token: str
    chat_id: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track name under tracks/")
    parser.add_argument("--date", default=date.today().isoformat(), help="Digest date in YYYY-MM-DD format")
    parser.add_argument("--input", dest="digest_input", help="Optional explicit digest JSON input path")
    parser.add_argument("--ranked-input", dest="ranked_input", help="Optional explicit ranked overview JSON input path")
    parser.add_argument(
        "--ranked-limit",
        type=int,
        default=DEFAULT_RANKED_LIMIT,
        help="Number of ranked overview jobs to include in the Telegram body",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the rendered Telegram messages instead of sending them")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        apply_runtime_env(load_secrets=not args.dry_run)
    except RuntimeEnvError as exc:
        print(f"send_digest_telegram.py: {exc}", file=sys.stderr)
        return 1

    root = Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))
    digest_path = Path(args.digest_input) if args.digest_input else digest_artifact_path(args.track, args.date, root=root)
    ranked_path = Path(args.ranked_input) if args.ranked_input else root / "shared" / "ranked_jobs" / f"{args.track}.json"

    try:
        digest_payload = load_json_payload(digest_path)
        ranked_payload = load_json_payload(ranked_path) if ranked_path.exists() else None
        rendered = render_digest_email(
            digest_payload,
            ranked_payload,
            ranked_limit=args.ranked_limit,
            as_of=date.fromisoformat(args.date),
        )
        messages = render_telegram_messages(rendered.subject, rendered.body)
    except (DigestEmailError, DigestTelegramError) as exc:
        print(f"send_digest_telegram.py: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        for index, message in enumerate(messages, start=1):
            if index > 1:
                print()
            print(f"Message {index}/{len(messages)}:")
            print(message)
        return 0

    try:
        config = load_telegram_config(os.environ)
        send_telegram_messages(config, messages)
    except DigestTelegramError as exc:
        print(f"send_digest_telegram.py: {exc}", file=sys.stderr)
        return 1

    return 0


def load_telegram_config(env: Mapping[str, str], *, execute_token_cmd: bool = True) -> TelegramConfig:
    chat_id = _required_env(env, "JOB_AGENT_TELEGRAM_CHAT_ID")
    api_base = (_optional_env(env, "JOB_AGENT_TELEGRAM_API_BASE") or DEFAULT_TELEGRAM_API_BASE).rstrip("/")
    token = _optional_env(env, "JOB_AGENT_TELEGRAM_BOT_TOKEN")
    token_cmd = _optional_env(env, "JOB_AGENT_TELEGRAM_BOT_TOKEN_CMD")
    secrets_loaded = _runtime_secrets_loaded(env)

    if token and not secrets_loaded:
        raise DigestTelegramError(
            "JOB_AGENT_TELEGRAM_BOT_TOKEN must come from JOB_AGENT_SECRETS_FILE; plaintext repo-local Telegram bot tokens are no longer supported"
        )

    if not token:
        if token_cmd:
            if not execute_token_cmd:
                raise DigestTelegramError("JOB_AGENT_TELEGRAM_BOT_TOKEN_CMD cannot be resolved in this mode")
            token = _secret_from_command(
                command=token_cmd,
                env_var_name="JOB_AGENT_TELEGRAM_BOT_TOKEN_CMD",
            )
        else:
            raise DigestTelegramError(
                "JOB_AGENT_TELEGRAM_CHAT_ID requires JOB_AGENT_TELEGRAM_BOT_TOKEN_CMD or JOB_AGENT_SECRETS_FILE-backed JOB_AGENT_TELEGRAM_BOT_TOKEN"
            )

    return TelegramConfig(
        api_base=api_base,
        bot_token=token,
        chat_id=chat_id,
    )


def render_telegram_messages(subject: str, body: str, *, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    text = f"{subject}\n\n{body.rstrip()}"
    raw_chunks = split_telegram_text(text, limit=max(1, limit - 24))
    if len(raw_chunks) == 1:
        return raw_chunks
    chunk_count = len(raw_chunks)
    return [f"(part {index}/{chunk_count})\n\n{chunk}" for index, chunk in enumerate(raw_chunks, start=1)]


def split_telegram_text(text: str, *, limit: int) -> list[str]:
    if limit < 1:
        raise DigestTelegramError("Telegram message limit must be positive")
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for piece in _iter_text_pieces(text):
        if len(piece) > limit:
            if current:
                chunks.append(current.rstrip("\n"))
                current = ""
            chunks.extend(_split_long_piece(piece, limit=limit))
            continue
        if not current:
            current = piece
            continue
        if len(current) + len(piece) <= limit:
            current += piece
            continue
        chunks.append(current.rstrip("\n"))
        current = piece
    if current:
        chunks.append(current.rstrip("\n"))
    return [chunk for chunk in chunks if chunk]


def send_telegram_messages(config: TelegramConfig, messages: Sequence[str]) -> None:
    for message in messages:
        send_telegram_message(config, message)


def send_telegram_message(config: TelegramConfig, text: str) -> None:
    payload = {
        "chat_id": config.chat_id,
        "disable_web_page_preview": True,
        "text": text,
    }
    body = json.dumps(payload).encode("utf-8")
    endpoint = f"{config.api_base}/bot{config.bot_token}/sendMessage"
    req = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=30) as response:
            response_body = response.read()
    except error.HTTPError as exc:
        detail = _telegram_error_detail(exc.read())
        suffix = f": {detail}" if detail else ""
        raise DigestTelegramError(f"Telegram API returned HTTP {exc.code}{suffix}") from exc
    except error.URLError as exc:
        raise DigestTelegramError(f"Telegram API request failed: {exc.reason}") from exc

    try:
        decoded = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DigestTelegramError("Telegram API returned invalid JSON") from exc

    if not isinstance(decoded, dict) or decoded.get("ok") is not True:
        detail = decoded.get("description") if isinstance(decoded, dict) else None
        suffix = f": {detail}" if detail else ""
        raise DigestTelegramError(f"Telegram API rejected the message{suffix}")


def _secret_from_command(*, command: str, env_var_name: str) -> str:
    try:
        completed = subprocess.run(
            command,
            shell=True,
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError as exc:
        raise DigestTelegramError(f"{env_var_name} failed to start: {exc}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        raise DigestTelegramError(f"{env_var_name} exited with status {completed.returncode}{detail}")
    secret = completed.stdout.rstrip("\n")
    if not secret:
        raise DigestTelegramError(f"{env_var_name} produced an empty token")
    return secret


def _telegram_error_detail(raw: bytes) -> str | None:
    if not raw:
        return None
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", errors="replace").strip() or None
    if isinstance(decoded, dict):
        description = decoded.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
    return None


def _iter_text_pieces(text: str) -> list[str]:
    pieces = text.splitlines(keepends=True)
    return pieces if pieces else [text]


def _split_long_piece(piece: str, *, limit: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(piece):
        end = min(len(piece), start + limit)
        chunks.append(piece[start:end].rstrip("\n"))
        start = end
    return [chunk for chunk in chunks if chunk]


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise DigestTelegramError(f"{name} is required")
    return value


def _optional_env(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _runtime_secrets_loaded(env: Mapping[str, str]) -> bool:
    value = env.get("JOB_AGENT_RUNTIME_SECRETS_FILE_LOADED", "").strip().lower()
    return value not in {"", "0", "false", "no"}


if __name__ == "__main__":
    raise SystemExit(main())
