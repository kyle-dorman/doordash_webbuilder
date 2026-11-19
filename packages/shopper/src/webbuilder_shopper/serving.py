"""Serve an existing build with a fresh, observable mock for a single shopper attempt."""

from collections.abc import Iterator
from contextlib import closing, contextmanager
from functools import partial
from http.client import HTTPConnection, HTTPException
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread

from webbuilder_mock_backend.server import Catalog, OrderHandler, OrderServer
from webbuilder_site_server.server import StorefrontHandler

type Submission = dict[str, object] | None


class Attempt:
    def __init__(self, url: str, mock_port: int) -> None:
        self.url = url
        self._mock_port: int | None = mock_port
        self._submissions: list[Submission] = []
        self._lock = Lock()
        self._mock_failed = Event()
        self._checkout_requests = 0

    @property
    def checkpoint_submission_count(self) -> int:
        """Include checkouts received by the site, even while forwarding to the mock."""
        with self._lock:
            return max(self._checkout_requests, len(self._submissions))

    @property
    def submissions(self) -> tuple[Submission, ...]:
        """One entry per POST /orders at the mock. Only accepted orders have a confirmation."""
        with self._lock:
            return tuple(self._submissions)

    def check_mock(self) -> None:
        """Check the private mock during an attempt or its recorded status after teardown."""
        if self._mock_port is not None and not self._mock_failed.is_set():
            try:
                with closing(HTTPConnection("127.0.0.1", self._mock_port, timeout=2)) as mock:
                    mock.request("HEAD", "/health")
                    if mock.getresponse().status != 204:
                        self._mock_failed.set()
            except (HTTPException, OSError):
                self._mock_failed.set()
        if self._mock_failed.is_set():
            raise OSError("The mock checkout was unavailable during this attempt.")


@contextmanager
def _running(server: ThreadingHTTPServer) -> Iterator[None]:
    # Wait for request handlers, including forwarded checkouts, before returning.
    server.daemon_threads = False
    with server:
        thread = Thread(target=partial(server.serve_forever, poll_interval=0.05))
        thread.start()
        try:
            yield
        finally:
            server.shutdown()
            thread.join()


@contextmanager
def serve_attempt(directory: Path, catalog: Catalog) -> Iterator[Attempt]:
    directory = directory.expanduser().resolve()
    if not (directory / "index.html").is_file():
        raise FileNotFoundError(f"No storefront index.html in {directory}")

    class ObservedOrderHandler(OrderHandler):
        timeout = 5

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_HEAD(self) -> None:
            self.send_response(204 if self.path == "/health" else 404)
            self.end_headers()

        def do_POST(self) -> None:
            if self.path == "/orders":
                with attempt._lock:
                    self.submission_index = len(attempt._submissions)
                    attempt._submissions.append(None)
            super().do_POST()

        def reply(self, status: int, data: dict[str, object]) -> None:
            if self.path == "/orders" and status == 200:
                with attempt._lock:
                    attempt._submissions[self.submission_index] = data
            super().reply(status, data)

    class ObservedStorefrontHandler(StorefrontHandler):
        timeout = 5  # Bound idle browser connections while the site drains.

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            if self.path == "/orders":
                with attempt._lock:
                    attempt._checkout_requests += 1
            super().do_POST()

        def send_json(self, status: int, body: bytes) -> None:
            if self.path == "/orders" and status >= 500:
                attempt._mock_failed.set()
            super().send_json(status, body)

    address = ("127.0.0.1", 0)
    mock = OrderServer(address, catalog, ObservedOrderHandler)
    with _running(mock):
        handler = partial(
            ObservedStorefrontHandler, directory=directory, mock_port=mock.server_port
        )
        site = ThreadingHTTPServer(address, handler)
        attempt = Attempt(f"http://127.0.0.1:{site.server_port}/", mock.server_port)
        try:
            with _running(site):
                yield attempt
        finally:
            # The site has finished forwarding all orders. The mock is still live.
            try:
                attempt.check_mock()
            finally:
                attempt._mock_port = None
