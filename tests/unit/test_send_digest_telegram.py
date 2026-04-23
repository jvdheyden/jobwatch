from __future__ import annotations

import json
from io import BytesIO
import sys
from urllib import error

import pytest

import send_digest_telegram


def test_load_telegram_config_reads_required_env_and_defaults_api_base():
    config = send_digest_telegram.load_telegram_config(
        {
            "JOB_AGENT_TELEGRAM_CHAT_ID": "@jobwatch_alerts",
            "JOB_AGENT_TELEGRAM_BOT_TOKEN": "secret-token",
            "JOB_AGENT_RUNTIME_SECRETS_FILE_LOADED": "1",
        }
    )

    assert config.api_base == "https://api.telegram.org"
    assert config.chat_id == "@jobwatch_alerts"
    assert config.bot_token == "secret-token"


def test_load_telegram_config_rejects_plaintext_token_without_secrets_marker():
    with pytest.raises(send_digest_telegram.DigestTelegramError, match="must come from JOB_AGENT_SECRETS_FILE"):
        send_digest_telegram.load_telegram_config(
            {
                "JOB_AGENT_TELEGRAM_CHAT_ID": "123456789",
                "JOB_AGENT_TELEGRAM_BOT_TOKEN": "secret-token",
            }
        )


def test_load_telegram_config_resolves_token_command(monkeypatch):
    calls: list[str] = []

    class Completed:
        returncode = 0
        stdout = "bot-token\n"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        assert kwargs["shell"] is True
        assert kwargs["capture_output"] is True
        return Completed()

    monkeypatch.setattr(send_digest_telegram.subprocess, "run", fake_run)

    config = send_digest_telegram.load_telegram_config(
        {
            "JOB_AGENT_TELEGRAM_CHAT_ID": "123456789",
            "JOB_AGENT_TELEGRAM_BOT_TOKEN_CMD": "pass show chat/jobwatch-telegram",
        }
    )

    assert calls == ["pass show chat/jobwatch-telegram"]
    assert config.bot_token == "bot-token"


def test_render_telegram_messages_splits_long_output():
    subject = "Digest"
    body = "\n".join(f"Line {index}: {'x' * 24}" for index in range(1, 9))

    messages = send_digest_telegram.render_telegram_messages(subject, body, limit=80)

    assert len(messages) > 1
    assert messages[0].startswith("(part 1/")
    assert all(len(message) <= 80 for message in messages)


def test_dry_run_does_not_load_telegram_config_or_execute_token_command(tmp_path, monkeypatch, load_json_fixture, capsys):
    root = tmp_path
    digest_dir = root / "artifacts" / "digests" / "core_crypto"
    digest_dir.mkdir(parents=True)
    (digest_dir / "2026-03-29.json").write_text(
        json.dumps(load_json_fixture("digests/core_crypto_minimal.json")) + "\n"
    )
    ranked_dir = root / "shared" / "ranked_jobs"
    ranked_dir.mkdir(parents=True)
    (ranked_dir / "core_crypto.json").write_text(
        json.dumps({"track": "core_crypto", "generated_at": "2026-03-29T09:00:00Z", "jobs": []}) + "\n"
    )
    monkeypatch.setenv("JOB_AGENT_ROOT", str(root))
    monkeypatch.setenv("JOB_AGENT_TELEGRAM_BOT_TOKEN_CMD", "exit 99")
    monkeypatch.setattr(
        sys,
        "argv",
        ["send_digest_telegram.py", "--track", "core_crypto", "--date", "2026-03-29", "--dry-run"],
    )
    monkeypatch.setattr(
        send_digest_telegram,
        "load_telegram_config",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not load telegram config")),
    )

    assert send_digest_telegram.main() == 0
    output = capsys.readouterr().out
    assert "Message 1/1:" in output
    assert "Executive summary" in output


def test_send_telegram_messages_posts_each_chunk(monkeypatch):
    calls: list[tuple[str, int, dict[str, object]]] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true, "result": {"message_id": 1}}'

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, timeout, json.loads(req.data.decode("utf-8"))))
        return FakeResponse()

    monkeypatch.setattr(send_digest_telegram.request, "urlopen", fake_urlopen)

    config = send_digest_telegram.TelegramConfig(
        api_base="https://api.telegram.org",
        bot_token="bot-token",
        chat_id="@jobwatch_alerts",
    )

    send_digest_telegram.send_telegram_messages(config, ["first chunk", "second chunk"])

    assert calls == [
        (
            "https://api.telegram.org/botbot-token/sendMessage",
            30,
            {"chat_id": "@jobwatch_alerts", "disable_web_page_preview": True, "text": "first chunk"},
        ),
        (
            "https://api.telegram.org/botbot-token/sendMessage",
            30,
            {"chat_id": "@jobwatch_alerts", "disable_web_page_preview": True, "text": "second chunk"},
        ),
    ]


def test_send_telegram_message_surfaces_api_description(monkeypatch):
    config = send_digest_telegram.TelegramConfig(
        api_base="https://api.telegram.org",
        bot_token="bot-token",
        chat_id="@jobwatch_alerts",
    )

    def fake_urlopen(_req, timeout):
        raise error.HTTPError(
            url="https://api.telegram.org/botbot-token/sendMessage",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=BytesIO(b'{"ok": false, "description": "chat not found"}'),
        )

    monkeypatch.setattr(send_digest_telegram.request, "urlopen", fake_urlopen)

    with pytest.raises(send_digest_telegram.DigestTelegramError, match="Telegram API returned HTTP 400: chat not found"):
        send_digest_telegram.send_telegram_message(config, "hello")
