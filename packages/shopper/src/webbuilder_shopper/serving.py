"""Serve an existing build with a fresh, observable mock for a single shopper attempt."""

from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from functools import partial
from http.client import HTTPConnection, HTTPException
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread

from webbuilder_mock_backend.server import Catalog, OrderHandler, OrderServer
from webbuilder_site_server.server import StorefrontHandler

type Submission = dict[str, object] | None


@dataclass(frozen=True)
class Attempt:
    url: str
    _submissions: list[Submission]
    _lock: Lock
    _mock_port: int
    _mock_failed: Event
    _closed: Event

    @property
    def submissions(self) -> tuple[Submission, ...]:
        """One entry per POST /orders at the mock. Only accepted orders have a confirmation."""
        with self._lock:
            return tuple(self._submissions)

    def check_mock(self) -> None:
        """Check the private mock during an attempt or its recorded status after teardown."""
        if not self._closed.is_set() and not self._mock_failed.is_set():
            try:
                with closing(HTTPConnection("127.0.0.1", self._mock_port, timeout=2)) as mock:
                    mock.request("HEAD", "/health")
                    if mock.getresponse().status != 204:
                        self._mock_failed.set()
            except (HTTPException, OSError):
                self._mock_failed.set()
        if self._mock_failed.is_set():
            raise OSError("The mock checkout was unavailable during this attempt.")


class _QuietStorefrontHandler(StorefrontHandler):
    timeout = 5  # Bound idle browser connections while the server drains.

    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def _running(server: ThreadingHTTPServer) -> Iterator[ThreadingHTTPServer]:
    with server:
        # server_close waits for outstanding request handlers, including forwarded POSTs.
        server.daemon_threads = False
        thread = Thread(target=partial(server.serve_forever, poll_interval=0.05))
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


@contextmanager
def serve_attempt(directory: Path, catalog: Catalog) -> Iterator[Attempt]:
    directory = directory.expanduser().resolve()
    if not (directory / "index.html").is_file():
        raise FileNotFoundError(f"No storefront index.html in {directory}")

    submissions: list[Submission] = []
    lock = Lock()
    mock_failed = Event()
    closed = Event()

    class ObservedOrderHandler(OrderHandler):
        timeout = 5

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_HEAD(self) -> None:
            self.send_response(204 if self.path == "/health" else 404)
            self.end_headers()

        def do_POST(self) -> None:
            if self.path == "/orders":
                with lock:
                    self.submission_index = len(submissions)
                    submissions.append(None)
            super().do_POST()

        def reply(self, status: int, data: dict[str, object]) -> None:
            if self.path == "/orders" and status == 200:
                with lock:
                    submissions[self.submission_index] = data
            super().reply(status, data)

    class ObservedStorefrontHandler(_QuietStorefrontHandler):
        def send_json(self, status: int, body: bytes) -> None:
            if self.path == "/orders" and status >= 500:
                mock_failed.set()
            super().send_json(status, body)

    address = ("127.0.0.1", 0)
    with _running(OrderServer(address, catalog, ObservedOrderHandler)) as mock:
        handler = partial(
            ObservedStorefrontHandler, directory=directory, mock_port=mock.server_port
        )
        with _running(ThreadingHTTPServer(address, handler)) as site:
            attempt = Attempt(
                f"http://127.0.0.1:{site.server_port}/",
                submissions,
                lock,
                mock.server_port,
                mock_failed,
                closed,
            )
            try:
                yield attempt
            finally:
                try:
                    attempt.check_mock()
                finally:
                    closed.set()
