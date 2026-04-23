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
import subprocess
import sys

from digest_json import digest_artifact_path
from digest_email import (
    DEFAULT_RANKED_LIMIT,
    DigestEmailError,
    RenderedDigestEmail,
    load_json_payload,
    render_digest_email,
)
from runtime_env import RuntimeEnvError, apply_runtime_env


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    sender: str
    recipients: tuple[str, ...]
    username: str | None
    password: str | None
    tls_mode: str


@dataclass(frozen=True)
class SMTPProviderPreset:
    host: str | None = None
    port: int | None = None
    tls_mode: str | None = None
    default_username_from_account: bool = False
    require_auth: bool = False


SMTP_PROVIDER_PRESETS: dict[str, SMTPProviderPreset] = {
    "gmail": SMTPProviderPreset(
        host="smtp.gmail.com",
        port=587,
        tls_mode="starttls",
        default_username_from_account=True,
    ),
    "fastmail": SMTPProviderPreset(
        host="smtp.fastmail.com",
        port=587,
        tls_mode="starttls",
        default_username_from_account=True,
    ),
    "hotmail": SMTPProviderPreset(
        host="smtp-mail.outlook.com",
        port=587,
        tls_mode="starttls",
        default_username_from_account=True,
    ),
    "proton": SMTPProviderPreset(
        host="smtp.protonmail.ch",
        port=587,
        tls_mode="starttls",
        default_username_from_account=True,
        require_auth=True,
    ),
}

SMTP_PROVIDER_ALIASES = {
    "custom": None,
    "googlemail": "gmail",
    "hotmail.com": "hotmail",
    "live": "hotmail",
    "live.com": "hotmail",
    "msn": "hotmail",
    "outlook": "hotmail",
    "outlook.com": "hotmail",
    "protonmail": "proton",
    "proton-business": "proton",
    "proton_business": "proton",
}


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
    try:
        apply_runtime_env(load_secrets=not args.dry_run)
    except RuntimeEnvError as exc:
        print(f"send_digest_email.py: {exc}", file=sys.stderr)
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


def load_smtp_config(env: Mapping[str, str], *, execute_password_cmd: bool = True) -> SMTPConfig:
    provider_key = _normalize_email_provider(_optional_env(env, "JOB_AGENT_EMAIL_PROVIDER"))
    preset = SMTP_PROVIDER_PRESETS.get(provider_key) if provider_key else None
    account = _optional_env(env, "JOB_AGENT_EMAIL_ACCOUNT")
    password = _optional_env(env, "JOB_AGENT_SMTP_PASSWORD")
    password_cmd = _optional_env(env, "JOB_AGENT_SMTP_PASSWORD_CMD")
    tls_mode = (_optional_env(env, "JOB_AGENT_SMTP_TLS") or (preset.tls_mode if preset and preset.tls_mode else "starttls")).lower()
    if tls_mode not in {"starttls", "ssl", "none"}:
        raise DigestEmailError("JOB_AGENT_SMTP_TLS must be one of: starttls, ssl, none")

    host = _optional_env(env, "JOB_AGENT_SMTP_HOST") or (preset.host if preset else None)
    if not host:
        raise DigestEmailError("JOB_AGENT_SMTP_HOST is required")
    port_text = env.get("JOB_AGENT_SMTP_PORT", "").strip()
    if port_text:
        port = _parse_port(port_text)
    elif preset and preset.port is not None:
        port = preset.port
    else:
        port = _default_port(tls_mode)

    username = _optional_env(env, "JOB_AGENT_SMTP_USERNAME")
    if not username and account and preset and preset.default_username_from_account:
        username = account
    elif not username and account and not preset and (password or password_cmd):
        username = account
    if preset and preset.require_auth and not username:
        raise DigestEmailError(
            f"JOB_AGENT_EMAIL_PROVIDER={provider_key} requires JOB_AGENT_EMAIL_ACCOUNT or JOB_AGENT_SMTP_USERNAME and SMTP token auth"
        )
    sender = _optional_env(env, "JOB_AGENT_SMTP_FROM") or account
    if not sender:
        raise DigestEmailError("JOB_AGENT_SMTP_FROM is required")
    recipients = _parse_recipients(_required_env(env, "JOB_AGENT_SMTP_TO"))
    secrets_loaded = _runtime_secrets_loaded(env)

    if password and not secrets_loaded:
        raise DigestEmailError(
            "JOB_AGENT_SMTP_PASSWORD must come from JOB_AGENT_SECRETS_FILE; plaintext repo-local SMTP passwords are no longer supported"
        )

    if username and not password:
        if password_cmd:
            if not execute_password_cmd:
                raise DigestEmailError("JOB_AGENT_SMTP_PASSWORD_CMD cannot be resolved in this mode")
            password = _password_from_command(password_cmd)
        else:
            raise DigestEmailError(
                "JOB_AGENT_SMTP_USERNAME requires JOB_AGENT_SMTP_PASSWORD_CMD or JOB_AGENT_SECRETS_FILE-backed JOB_AGENT_SMTP_PASSWORD"
            )
    elif not username and (password or password_cmd):
        raise DigestEmailError(
            "JOB_AGENT_SMTP_PASSWORD and JOB_AGENT_SMTP_PASSWORD_CMD require JOB_AGENT_SMTP_USERNAME"
        )

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


def _normalize_email_provider(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    canonical = SMTP_PROVIDER_ALIASES.get(normalized, normalized)
    if canonical is None:
        return None
    if canonical not in SMTP_PROVIDER_PRESETS:
        supported = ", ".join(sorted(set(SMTP_PROVIDER_PRESETS) | {key for key, item in SMTP_PROVIDER_ALIASES.items() if item}))
        raise DigestEmailError(f"JOB_AGENT_EMAIL_PROVIDER must be one of: {supported}, custom")
    return canonical


def _password_from_command(command: str) -> str:
    try:
        completed = subprocess.run(
            command,
            shell=True,
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError as exc:
        raise DigestEmailError(f"JOB_AGENT_SMTP_PASSWORD_CMD failed to start: {exc}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        raise DigestEmailError(
            f"JOB_AGENT_SMTP_PASSWORD_CMD exited with status {completed.returncode}{detail}"
        )
    password = completed.stdout.rstrip("\n")
    if not password:
        raise DigestEmailError("JOB_AGENT_SMTP_PASSWORD_CMD produced an empty password")
    return password


def _runtime_secrets_loaded(env: Mapping[str, str]) -> bool:
    value = env.get("JOB_AGENT_RUNTIME_SECRETS_FILE_LOADED", "").strip().lower()
    return value not in {"", "0", "false", "no"}


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
