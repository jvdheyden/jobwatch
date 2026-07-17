"""HTTP helpers for deterministic discovery providers."""

from __future__ import annotations

import gzip
import http.client
import json
import socket
import ssl
import time
from typing import Any
from urllib.request import HTTPSHandler, Request, build_opener, urlopen


# Some public career pages reject obviously scripted user agents with a 403.
# Use a stable browser-like agent so deterministic HTML discovery still works.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def _create_ipv4_connection(
    address: tuple[str, int],
    timeout: float | object = socket._GLOBAL_DEFAULT_TIMEOUT,
    source_address: tuple[str, int] | None = None,
) -> socket.socket:
    host, port = address
    last_error: OSError | None = None
    for family, socktype, proto, _, socket_address in socket.getaddrinfo(
        host,
        port,
        socket.AF_INET,
        socket.SOCK_STREAM,
    ):
        sock: socket.socket | None = None
        try:
            sock = socket.socket(family, socktype, proto)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(socket_address)
            return sock
        except OSError as exc:
            last_error = exc
            if sock is not None:
                sock.close()
    if last_error is not None:
        raise last_error
    raise OSError(f"getaddrinfo returned no IPv4 addresses for {host}")


class _IPv4HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._create_connection = _create_ipv4_connection


class _IPv4HTTPSHandler(HTTPSHandler):
    def https_open(self, request: Request) -> Any:
        return self.do_open(
            _IPv4HTTPSConnection,
            request,
            context=self._context,
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


def fetch_text_ipv4(url: str, timeout_seconds: int) -> str:
    """Fetch HTTPS content over IPv4 for hosts whose IPv6 edge rejects automation."""
    last_error: Exception | None = None
    opener = build_opener(_IPv4HTTPSHandler())
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with opener.open(request, timeout=timeout_seconds) as response:
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
