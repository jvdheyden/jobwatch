"""HTTP helpers for deterministic discovery providers."""

from __future__ import annotations

import gzip
import json
import ssl
import time
from typing import Any
from urllib.request import Request, urlopen


# Some public career pages reject obviously scripted user agents with a 403.
# Use a stable browser-like agent so deterministic HTML discovery still works.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def fetch_text(url: str, timeout_seconds: int) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            context = ssl.create_default_context()
            with urlopen(request, timeout=timeout_seconds, context=context) as response:
                content_type = response.headers.get_content_charset() or "utf-8"
                body = response.read()
                content_encoding = (response.headers.get("Content-Encoding") or "").lower()
                if "gzip" in content_encoding:
                    body = gzip.decompress(body)
                return body.decode(content_type, errors="replace")
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def fetch_json(url: str, timeout_seconds: int) -> Any:
    return json.loads(fetch_text(url, timeout_seconds))


def post_json(url: str, payload: Any, timeout_seconds: int, headers: dict[str, str] | None = None) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request_headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"}
            if headers:
                request_headers.update(headers)
            request = Request(url, data=json.dumps(payload).encode(), headers=request_headers)
            context = ssl.create_default_context()
            with urlopen(request, timeout=timeout_seconds, context=context) as response:
                content_type = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(content_type, errors="replace"))
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error
