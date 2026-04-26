from __future__ import annotations

import socket
from unittest.mock import MagicMock

import pytest

import probe_career_source


def test_fetch_http_handles_timeout(monkeypatch):
    def mock_urlopen(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(probe_career_source, "urlopen", mock_urlopen)

    html, final_url, status, hints = probe_career_source.fetch_http("https://example.com", timeout=5)

    assert html == ""
    assert status == 0
    assert any("timeout" in h.lower() for h in hints)


def test_fetch_http_handles_socket_timeout(monkeypatch):
    def mock_urlopen(*args, **kwargs):
        raise socket.timeout("socket timed out")

    monkeypatch.setattr(probe_career_source, "urlopen", mock_urlopen)

    html, final_url, status, hints = probe_career_source.fetch_http("https://example.com", timeout=5)

    assert html == ""
    assert status == 0
    assert any("timeout" in h.lower() for h in hints)


def test_fetch_http_handles_oserror_timeout(monkeypatch):
    def mock_urlopen(*args, **kwargs):
        raise OSError("Connect call failed: timed out")

    monkeypatch.setattr(probe_career_source, "urlopen", mock_urlopen)

    html, final_url, status, hints = probe_career_source.fetch_http("https://example.com", timeout=5)

    assert html == ""
    assert status == 0
    assert any("timeout" in h.lower() for h in hints)


def test_probe_returns_diagnostic_on_timeout(monkeypatch):
    def mock_urlopen(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(probe_career_source, "urlopen", mock_urlopen)
    # Also mock fetch_playwright to avoid actually trying to run it
    monkeypatch.setattr(probe_career_source, "fetch_playwright", lambda url, timeout: ("", url, ["Playwright skipped"]))

    result = probe_career_source.probe("https://example.com")

    assert result["fetch_status"] == 0
    assert any("timeout" in h.lower() for h in result["hints"])
    assert result["playwright_needed"] is False
