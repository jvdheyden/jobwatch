from __future__ import annotations

import json

import send_run_failure_alert


def test_render_failure_alert_flags_expired_login_and_quotes_agent_error(tmp_path):
    log_path = tmp_path / "music_audio_pm-2026-10-09.log"
    result_event = {
        "type": "result",
        "is_error": True,
        "api_error_status": 401,
        "result": "Failed to authenticate. API Error: 401 OAuth access token has expired.",
    }
    log_path.write_text(
        "\n".join(
            [
                "[2026-10-09 11:28:45] Claude phase started",
                '{"type":"system","subtype":"init"}',
                json.dumps(result_event, separators=(",", ":")),
                "/scripts/run_track.sh: line 305: 48737 Terminated: 15          sleep 7200",
                "[2026-10-09 11:28:52] Claude exited with status 1",
            ]
        )
        + "\n"
    )

    rendered = send_run_failure_alert.render_failure_alert("music_audio_pm", "2026-10-09", 1, log_path)

    assert rendered.subject == "Music Audio PM run failed (2026-10-09)"
    assert "failed with exit status 1" in rendered.body
    assert "claude auth login" in rendered.body
    assert "Failed to authenticate. API Error: 401 OAuth access token has expired." in rendered.body
    assert "[2026-10-09 11:28:52] Claude exited with status 1" in rendered.body
    assert "Terminated: 15" not in rendered.body
    assert f"Full log: {log_path}" in rendered.body


def test_render_failure_alert_omits_auth_hint_for_other_failures(tmp_path):
    log_path = tmp_path / "demo-2030-01-15.log"
    log_path.write_text("[2030-01-15 09:00:00] Codex phase timed out after 7200s\n")

    rendered = send_run_failure_alert.render_failure_alert("demo", "2030-01-15", 124, log_path)

    assert "failed with exit status 124" in rendered.body
    assert "claude auth login" not in rendered.body
    assert "Agent error:" not in rendered.body
    assert "Codex phase timed out after 7200s" in rendered.body


def test_render_failure_alert_tolerates_missing_log(tmp_path):
    rendered = send_run_failure_alert.render_failure_alert("demo", "2030-01-15", 2, tmp_path / "missing.log")

    assert "failed with exit status 2" in rendered.body


def test_render_failure_alert_reads_only_the_failed_attempt_and_reports_partial_delivery(tmp_path):
    log_path = tmp_path / "demo-2030-01-15.log"
    earlier_attempt = (
        "[2030-01-15 09:00:00] Starting demo daily run\n"
        '{"type":"result","is_error":true,"api_error_status":401,"result":"OAuth access token has expired"}\n'
        "[2030-01-15 09:00:05] Claude exited with status 1\n"
    )
    retry = (
        "[2030-01-15 10:00:00] Starting demo daily run\n"
        "[2030-01-15 10:05:00] Delivery phase finished successfully: email\n"
        "[2030-01-15 10:05:01] Delivery phase failed: telegram status 3\n"
    )
    log_path.write_text(earlier_attempt + retry)

    rendered = send_run_failure_alert.render_failure_alert(
        "demo", "2030-01-15", 3, log_path, log_offset=len(earlier_attempt.encode())
    )

    assert rendered.body.startswith(
        "The demo run for 2030-01-15 failed with exit status 3. "
        "The digest was delivered by email, but telegram delivery failed.\n"
    )
    assert "no digest was delivered" not in rendered.body
    assert "claude auth login" not in rendered.body
    assert "Agent error:" not in rendered.body
    assert "09:00:05" not in rendered.body
    assert "[2030-01-15 10:05:01] Delivery phase failed: telegram status 3" in rendered.body


def test_render_failure_alert_reports_no_delivery_when_none_succeeded(tmp_path):
    log_path = tmp_path / "demo-2030-01-15.log"
    log_path.write_text("[2030-01-15 10:05:00] Delivery phase failed: email status 17\n")

    rendered = send_run_failure_alert.render_failure_alert("demo", "2030-01-15", 17, log_path)

    assert rendered.body.startswith("The demo run for 2030-01-15 failed with exit status 17, so no digest was delivered.\n")
