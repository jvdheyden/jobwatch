import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path to import telegram_chat_id
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import telegram_chat_id


def test_main_fails_if_token_missing(capsys, monkeypatch) -> None:
    monkeypatch.delenv("JOB_AGENT_TELEGRAM_BOT_TOKEN", raising=False)
    
    with patch("telegram_chat_id.apply_runtime_env", autospec=True) as mock_apply:
        code = telegram_chat_id.main()
        
        assert code == 1
        mock_apply.assert_called_once_with(load_secrets=True)
        stderr = capsys.readouterr().err
        assert "JOB_AGENT_TELEGRAM_BOT_TOKEN not found in environment" in stderr


def test_main_uses_existing_token_if_present_after_env_load(capsys, monkeypatch) -> None:
    monkeypatch.setenv("JOB_AGENT_TELEGRAM_BOT_TOKEN", "fake_token")
    
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "ok": True,
        "result": [
            {
                "message": {
                    "chat": {"id": 12345, "username": "test_user", "type": "private"}
                }
            }
        ]
    }).encode("utf-8")

    with patch("telegram_chat_id.apply_runtime_env") as mock_apply:
        with patch("telegram_chat_id.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_response
            
            code = telegram_chat_id.main()
            
            assert code == 0
            mock_apply.assert_called_once_with(load_secrets=True)
            stdout = capsys.readouterr().out
            assert "12345" in stdout
            assert "test_user" in stdout

def test_main_handles_api_error(capsys, monkeypatch) -> None:
    monkeypatch.setenv("JOB_AGENT_TELEGRAM_BOT_TOKEN", "fake_token")
    
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "ok": False,
        "description": "Unauthorized"
    }).encode("utf-8")

    with patch("telegram_chat_id.apply_runtime_env"):
        with patch("telegram_chat_id.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_response
            code = telegram_chat_id.main()
            
            assert code == 1
            stderr = capsys.readouterr().err
            assert "Telegram API error: Unauthorized" in stderr
