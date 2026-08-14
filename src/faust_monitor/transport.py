"""Small sequential HTTP transport with bounded retries."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
import json
import ssl
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class HttpResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes

    def text(self) -> str:
        charset = "utf-8"
        get_charset = getattr(self.headers, "get_content_charset", None)
        if callable(get_charset):
            charset = get_charset() or charset
        return self.body.decode(charset, errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())


class TransportError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        url: str,
        retryable: bool,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.retryable = retryable
        self.status = status


class HttpTransport:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        retry_limit: int,
        backoff_seconds: float,
        user_agent: str,
        opener: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.retry_limit = retry_limit
        self.backoff_seconds = backoff_seconds
        self.user_agent = user_agent
        self._opener = opener or _verified_urlopen
        self._sleeper = sleeper

    def get_text(self, url: str) -> str:
        return self.request(url).text()

    def post_form_json(self, url: str, fields: Mapping[str, str]) -> Any:
        body = urlencode(fields).encode("ascii")
        response = self.request(
            url,
            method="POST",
            body=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            return response.json()
        except (json.JSONDecodeError, UnicodeError) as error:
            raise TransportError(
                f"Response from {url} was not valid JSON: {error}",
                url=url,
                retryable=False,
                status=response.status,
            ) from error

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        request_headers = {
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "User-Agent": self.user_agent,
            **dict(headers or {}),
        }
        request = Request(url, data=body, headers=request_headers, method=method)

        for attempt in range(self.retry_limit + 1):
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    status = getattr(response, "status", None) or response.getcode()
                    return HttpResponse(
                        url=response.geturl(),
                        status=status,
                        headers=response.headers,
                        body=response.read(),
                    )
            except HTTPError as error:
                retryable = error.code in TRANSIENT_HTTP_STATUSES
                transport_error = TransportError(
                    f"HTTP {error.code} for {url}",
                    url=url,
                    retryable=retryable,
                    status=error.code,
                )
            except (URLError, TimeoutError, OSError) as error:
                transport_error = TransportError(
                    f"Network error for {url}: {error}",
                    url=url,
                    retryable=True,
                )

            if not transport_error.retryable or attempt >= self.retry_limit:
                raise transport_error
            self._sleeper(self.backoff_seconds * (2**attempt))

        raise AssertionError("retry loop exited unexpectedly")


def _verified_urlopen(request: Request, *, timeout: float) -> Any:
    return urlopen(request, timeout=timeout, context=_verified_tls_context())


@lru_cache(maxsize=1)
def _verified_tls_context() -> ssl.SSLContext:
    """Build a verified context, including macOS root keychains when needed.

    Python.org builds on macOS do not always read the OS trust store. Loading the
    public system keychains preserves certificate verification without bundling a
    third-party CA package or disabling TLS checks. Other platforms use Python's
    normal verified defaults.
    """

    context = ssl.create_default_context()
    if sys.platform != "darwin":
        return context

    for keychain in (
        "/System/Library/Keychains/SystemRootCertificates.keychain",
        "/Library/Keychains/System.keychain",
    ):
        try:
            completed = subprocess.run(
                ["security", "find-certificate", "-a", "-p", keychain],
                check=True,
                capture_output=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            continue
        if completed.stdout:
            context.load_verify_locations(cadata=completed.stdout.decode("ascii"))
    return context
