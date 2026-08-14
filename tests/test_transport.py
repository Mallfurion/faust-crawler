from __future__ import annotations

from email.message import Message
from io import BytesIO
import unittest
from urllib.error import HTTPError, URLError

from faust_monitor.transport import HttpTransport, TransportError


class FakeResponse:
    def __init__(self, body=b"ok", *, url="https://example.test/", status=200):
        self._body = body
        self._url = url
        self.status = status
        self.headers = Message()
        self.headers.add_header("Content-Type", "application/json; charset=utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._body

    def geturl(self):
        return self._url

    def getcode(self):
        return self.status


class SequenceOpener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.timeouts = []

    def __call__(self, request, *, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def http_error(status):
    return HTTPError(
        "https://example.test/",
        status,
        "error",
        Message(),
        BytesIO(b"error"),
    )


def transport(opener, sleeps, *, retry_limit=3, backoff=1.0):
    return HttpTransport(
        timeout_seconds=7,
        retry_limit=retry_limit,
        backoff_seconds=backoff,
        user_agent="test-agent",
        opener=opener,
        sleeper=sleeps.append,
    )


class TransportTests(unittest.TestCase):
    def test_transient_network_failure_retries_with_backoff(self):
        opener = SequenceOpener(URLError("temporary"), FakeResponse())
        sleeps = []

        response = transport(opener, sleeps).request("https://example.test/")

        self.assertEqual(response.status, 200)
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(opener.timeouts, [7, 7])

    def test_transient_http_errors_use_bounded_exponential_backoff(self):
        opener = SequenceOpener(http_error(503), http_error(429), FakeResponse())
        sleeps = []

        transport(opener, sleeps, retry_limit=2, backoff=0.5).request(
            "https://example.test/"
        )

        self.assertEqual(sleeps, [0.5, 1.0])
        self.assertEqual(len(opener.requests), 3)

    def test_permanent_http_failure_is_not_retried(self):
        opener = SequenceOpener(http_error(404))
        sleeps = []

        with self.assertRaises(TransportError) as caught:
            transport(opener, sleeps).request("https://example.test/")

        self.assertFalse(caught.exception.retryable)
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(sleeps, [])

    def test_timeout_exhaustion_is_retryable_but_bounded(self):
        opener = SequenceOpener(TimeoutError(), TimeoutError(), TimeoutError())
        sleeps = []

        with self.assertRaises(TransportError) as caught:
            transport(opener, sleeps, retry_limit=2).request("https://example.test/")

        self.assertTrue(caught.exception.retryable)
        self.assertEqual(len(opener.requests), 3)
        self.assertEqual(sleeps, [1.0, 2.0])

    def test_form_post_encodes_map_request_and_parses_json(self):
        opener = SequenceOpener(FakeResponse(b'{"sectors": []}'))
        sleeps = []

        payload = transport(opener, sleeps).post_form_json(
            "https://example.test/tickets", {"do": "getmapdata"}
        )

        request = opener.requests[0]
        self.assertEqual(payload, {"sectors": []})
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.data, b"do=getmapdata")
        self.assertEqual(
            request.get_header("Content-type"),
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(request.get_header("User-agent"), "test-agent")

    def test_invalid_json_is_a_permanent_transport_error(self):
        opener = SequenceOpener(FakeResponse(b"not-json"))
        sleeps = []

        with self.assertRaises(TransportError) as caught:
            transport(opener, sleeps).post_form_json(
                "https://example.test/tickets", {"do": "getmapdata"}
            )

        self.assertFalse(caught.exception.retryable)


if __name__ == "__main__":
    unittest.main()

