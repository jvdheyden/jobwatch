from __future__ import annotations

from email.message import EmailMessage
import json
import sys

import pytest

import send_digest_email
from digest_email import DigestEmailError, RenderedDigestEmail


def test_load_smtp_config_reads_required_env_and_defaults_port():
    config = send_digest_email.load_smtp_config(
        {
            "JOB_AGENT_SMTP_HOST": "smtp.example.com",
            "JOB_AGENT_SMTP_FROM": "jobs@example.com",
            "JOB_AGENT_SMTP_TO": "one@example.com, two@example.com",
            "JOB_AGENT_SMTP_USERNAME": "user",
            "JOB_AGENT_SMTP_PASSWORD": "secret",
        }
    )

    assert config.host == "smtp.example.com"
    assert config.port == 587
    assert config.sender == "jobs@example.com"
    assert config.recipients == ("one@example.com", "two@example.com")
    assert config.username == "user"
    assert config.password == "secret"
    assert config.tls_mode == "starttls"


def test_load_smtp_config_allows_no_auth_for_local_servers():
    config = send_digest_email.load_smtp_config(
        {
            "JOB_AGENT_SMTP_HOST": "localhost",
            "JOB_AGENT_SMTP_FROM": "jobs@example.com",
            "JOB_AGENT_SMTP_TO": "me@example.com",
            "JOB_AGENT_SMTP_TLS": "none",
        }
    )

    assert config.port == 25
    assert config.username is None
    assert config.password is None
    assert config.tls_mode == "none"


def test_load_smtp_config_rejects_partial_auth():
    with pytest.raises(DigestEmailError, match="requires JOB_AGENT_SMTP_PASSWORD or JOB_AGENT_SMTP_PASSWORD_CMD"):
        send_digest_email.load_smtp_config(
            {
                "JOB_AGENT_SMTP_HOST": "smtp.example.com",
                "JOB_AGENT_SMTP_FROM": "jobs@example.com",
                "JOB_AGENT_SMTP_TO": "me@example.com",
                "JOB_AGENT_SMTP_USERNAME": "user",
            }
        )


def test_load_smtp_config_resolves_password_command(monkeypatch):
    calls: list[str] = []

    class Completed:
        returncode = 0
        stdout = "secret with space \n"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        assert kwargs["shell"] is True
        assert kwargs["capture_output"] is True
        return Completed()

    monkeypatch.setattr(send_digest_email.subprocess, "run", fake_run)

    config = send_digest_email.load_smtp_config(
        {
            "JOB_AGENT_SMTP_HOST": "smtp.example.com",
            "JOB_AGENT_SMTP_FROM": "jobs@example.com",
            "JOB_AGENT_SMTP_TO": "me@example.com",
            "JOB_AGENT_SMTP_USERNAME": "user",
            "JOB_AGENT_SMTP_PASSWORD_CMD": "pass show email/jobwatch-smtp",
        }
    )

    assert calls == ["pass show email/jobwatch-smtp"]
    assert config.password == "secret with space "


def test_load_smtp_config_rejects_empty_password_command(monkeypatch):
    class Completed:
        returncode = 0
        stdout = "\n"
        stderr = ""

    monkeypatch.setattr(send_digest_email.subprocess, "run", lambda *_args, **_kwargs: Completed())

    with pytest.raises(DigestEmailError, match="empty password"):
        send_digest_email.load_smtp_config(
            {
                "JOB_AGENT_SMTP_HOST": "smtp.example.com",
                "JOB_AGENT_SMTP_FROM": "jobs@example.com",
                "JOB_AGENT_SMTP_TO": "me@example.com",
                "JOB_AGENT_SMTP_USERNAME": "user",
                "JOB_AGENT_SMTP_PASSWORD_CMD": "printf '\\n'",
            }
        )


def test_dry_run_does_not_load_smtp_or_execute_password_command(tmp_path, monkeypatch, load_json_fixture, capsys):
    root = tmp_path
    digest_dir = root / "artifacts" / "digests" / "core_crypto"
    digest_dir.mkdir(parents=True)
    (digest_dir / "2026-03-29.json").write_text(
        json.dumps(load_json_fixture("digests/core_crypto_minimal.json")) + "\n"
    )
    monkeypatch.setenv("JOB_AGENT_ROOT", str(root))
    monkeypatch.setenv("JOB_AGENT_SMTP_PASSWORD_CMD", "exit 99")
    monkeypatch.setattr(
        sys,
        "argv",
        ["send_digest_email.py", "--track", "core_crypto", "--date", "2026-03-29", "--dry-run"],
    )
    monkeypatch.setattr(
        send_digest_email,
        "load_smtp_config",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not load smtp config")),
    )

    assert send_digest_email.main() == 0
    assert "Subject:" in capsys.readouterr().out


def test_build_email_message_adds_ranked_attachment():
    rendered = RenderedDigestEmail(
        subject="Digest",
        body="Body\n",
        attachment_filename="ranked-overview-demo.md",
        attachment_text="# Ranked\n",
    )

    message = send_digest_email.build_email_message(rendered, sender="jobs@example.com", recipients=("me@example.com",))
    attachments = list(message.iter_attachments())

    assert message["Subject"] == "Digest"
    assert message["From"] == "jobs@example.com"
    assert message["To"] == "me@example.com"
    assert message.get_body(preferencelist=("plain",)).get_content() == "Body\n"
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "ranked-overview-demo.md"
    assert attachments[0].get_content() == "# Ranked\n"


def test_send_email_message_uses_starttls_login_and_recipients(monkeypatch):
    events: list[tuple] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int) -> None:
            events.append(("connect", host, port))

        def __enter__(self):
            events.append(("enter",))
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            events.append(("exit", exc_type))

        def starttls(self, *, context) -> None:
            events.append(("starttls", context is not None))

        def login(self, username: str, password: str) -> None:
            events.append(("login", username, password))

        def send_message(self, message: EmailMessage, *, from_addr: str, to_addrs: list[str]) -> None:
            events.append(("send_message", message["Subject"], from_addr, tuple(to_addrs)))

    monkeypatch.setattr(send_digest_email.smtplib, "SMTP", FakeSMTP)
    config = send_digest_email.SMTPConfig(
        host="smtp.example.com",
        port=587,
        sender="jobs@example.com",
        recipients=("one@example.com", "two@example.com"),
        username="user",
        password="secret",
        tls_mode="starttls",
    )
    message = EmailMessage()
    message["Subject"] = "Digest"
    message.set_content("Body\n")

    send_digest_email.send_email_message(config, message)

    assert events == [
        ("connect", "smtp.example.com", 587),
        ("enter",),
        ("starttls", True),
        ("login", "user", "secret"),
        ("send_message", "Digest", "jobs@example.com", ("one@example.com", "two@example.com")),
        ("exit", None),
    ]
