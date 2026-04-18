#!/usr/bin/env python3
"""Send a JSON-backed daily job digest email over SMTP."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
import os
from pathlib import Path
import smtplib
import ssl
import sys

from digest_json import digest_artifact_path
from digest_email import (
    DEFAULT_RANKED_LIMIT,
    DigestEmailError,
    RenderedDigestEmail,
    load_json_payload,
    render_digest_email,
)


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    sender: str
    recipients: tuple[str, ...]
    username: str | None
    password: str | None
    tls_mode: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track name under tracks/")
    parser.add_argument("--date", default=date.today().isoformat(), help="Digest date in YYYY-MM-DD format")
    parser.add_argument("--input", dest="digest_input", help="Optional explicit digest JSON input path")
    parser.add_argument("--ranked-input", dest="ranked_input", help="Optional explicit ranked overview JSON input path")
    parser.add_argument("--ranked-limit", type=int, default=DEFAULT_RANKED_LIMIT, help="Number of ranked overview jobs to include in the email body")
    parser.add_argument("--dry-run", action="store_true", help="Print the rendered email instead of sending it")
    return parser


def main() -> int:
    args = build_parser().parse_args()
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
    except DigestEmailError as exc:
        print(f"send_digest_email.py: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Subject: {rendered.subject}")
        print()
        print(rendered.body, end="")
        if rendered.attachment_filename:
            print()
            print(f"Attachment: {rendered.attachment_filename}")
        return 0

    try:
        config = load_smtp_config(os.environ)
        message = build_email_message(rendered, sender=config.sender, recipients=config.recipients)
        send_email_message(config, message)
    except DigestEmailError as exc:
        print(f"send_digest_email.py: {exc}", file=sys.stderr)
        return 1

    return 0


def load_smtp_config(env: Mapping[str, str]) -> SMTPConfig:
    tls_mode = env.get("JOB_AGENT_SMTP_TLS", "starttls").strip().lower()
    if tls_mode not in {"starttls", "ssl", "none"}:
        raise DigestEmailError("JOB_AGENT_SMTP_TLS must be one of: starttls, ssl, none")

    host = _required_env(env, "JOB_AGENT_SMTP_HOST")
    port_text = env.get("JOB_AGENT_SMTP_PORT", "").strip()
    port = _parse_port(port_text) if port_text else _default_port(tls_mode)
    sender = _required_env(env, "JOB_AGENT_SMTP_FROM")
    recipients = _parse_recipients(_required_env(env, "JOB_AGENT_SMTP_TO"))
    username = _optional_env(env, "JOB_AGENT_SMTP_USERNAME")
    password = _optional_env(env, "JOB_AGENT_SMTP_PASSWORD")

    if bool(username) != bool(password):
        raise DigestEmailError("JOB_AGENT_SMTP_USERNAME and JOB_AGENT_SMTP_PASSWORD must be set together")

    return SMTPConfig(
        host=host,
        port=port,
        sender=sender,
        recipients=recipients,
        username=username,
        password=password,
        tls_mode=tls_mode,
    )


def build_email_message(rendered: RenderedDigestEmail, *, sender: str, recipients: tuple[str, ...]) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = rendered.subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(rendered.body)

    if rendered.attachment_filename and rendered.attachment_text is not None:
        message.add_attachment(
            rendered.attachment_text,
            subtype="markdown",
            filename=rendered.attachment_filename,
        )

    return message


def send_email_message(config: SMTPConfig, message: EmailMessage) -> None:
    if config.tls_mode == "ssl":
        smtp_class = smtplib.SMTP_SSL
    else:
        smtp_class = smtplib.SMTP

    with smtp_class(config.host, config.port) as smtp:
        if config.tls_mode == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        if config.username and config.password:
            smtp.login(config.username, config.password)
        smtp.send_message(message, from_addr=config.sender, to_addrs=list(config.recipients))


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise DigestEmailError(f"{name} is required")
    return value


def _optional_env(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise DigestEmailError("JOB_AGENT_SMTP_PORT must be an integer") from exc
    if not (1 <= port <= 65535):
        raise DigestEmailError("JOB_AGENT_SMTP_PORT must be between 1 and 65535")
    return port


def _parse_recipients(value: str) -> tuple[str, ...]:
    recipients = tuple(item.strip() for item in value.split(",") if item.strip())
    if not recipients:
        raise DigestEmailError("JOB_AGENT_SMTP_TO must contain at least one recipient")
    return recipients


def _default_port(tls_mode: str) -> int:
    if tls_mode == "ssl":
        return 465
    if tls_mode == "none":
        return 25
    return 587


if __name__ == "__main__":
    raise SystemExit(main())
