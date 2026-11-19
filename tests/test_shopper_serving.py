import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from webbuilder_mock_backend.server import MenuItem, OrderHandler
from webbuilder_shopper.serving import serve_attempt
from webbuilder_site_server.server import StorefrontHandler


def test_attempt_observes_real_mock_and_isolates_submissions(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("Welcome", encoding="utf-8")
    catalog = {"thai": {"tea": MenuItem("Tea", 450)}}
    with serve_attempt(tmp_path, catalog) as first, serve_attempt(tmp_path, catalog) as second:
        first.check_mock()
        second.check_mock()
        with urlopen(first.url, timeout=5) as homepage:
            assert homepage.read() == b"Welcome"
        initial_submissions = first.submissions
        assert initial_submissions == ()

        def order(quantity: int) -> Request:
            body = {"store_id": "thai", "items": [{"item_id": "tea", "quantity": quantity}]}
            return Request(
                first.url + "orders",
                json.dumps(body).encode(),
                {"Content-Type": "application/json"},
            )

        with pytest.raises(HTTPError) as rejection:
            urlopen(order(0), timeout=5)
        with rejection.value as response:
            assert response.status == 400
        with urlopen(order(2), timeout=5) as accepted:
            confirmation = json.load(accepted)
            assert confirmation["subtotal_cents"] == 900
        assert first.submissions == (None, confirmation)
        assert second.submissions == ()
    first.check_mock()
    second.check_mock()


def _unavailable_checkout(handler: OrderHandler) -> None:
    handler.reply(503, {"error": "Unavailable"})


def test_failed_checkout_service_marks_run_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.html").touch()

    monkeypatch.setattr(OrderHandler, "do_POST", _unavailable_checkout)
    with pytest.raises(OSError, match="mock checkout was unavailable"):
        with serve_attempt(tmp_path, {}) as attempt:
            request = Request(attempt.url + "orders", b"{}", {"Content-Type": "application/json"})
            with pytest.raises(HTTPError) as response:
                urlopen(request, timeout=5)
            with response.value as error_response:
                assert error_response.status == 503
            with pytest.raises(OSError, match="mock checkout was unavailable"):
                attempt.check_mock()
    with pytest.raises(OSError, match="mock checkout was unavailable"):
        attempt.check_mock()


@pytest.mark.parametrize("mock_fails", [False, True], ids=["accepted", "unavailable"])
def test_teardown_finishes_in_flight_checkout_before_stopping_mock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_fails: bool
) -> None:
    (tmp_path / "index.html").touch()
    catalog = {"thai": {"tea": MenuItem("Tea", 450)}}
    received, closing = Event(), Event()
    forward_order = StorefrontHandler.do_POST
    close_server = ThreadingHTTPServer.server_close

    def delayed_checkout(handler: StorefrontHandler) -> None:
        received.set()
        assert closing.wait(timeout=5)
        forward_order(handler)

    def signal_close(server: ThreadingHTTPServer) -> None:
        closing.set()
        close_server(server)

    if mock_fails:
        monkeypatch.setattr(OrderHandler, "do_POST", _unavailable_checkout)

    monkeypatch.setattr(StorefrontHandler, "do_POST", delayed_checkout)
    monkeypatch.setattr(ThreadingHTTPServer, "server_close", signal_close)

    def post(url: str) -> dict[str, object]:
        body = {"store_id": "thai", "items": [{"item_id": "tea", "quantity": 2}]}
        request = Request(
            url + "orders", json.dumps(body).encode(), {"Content-Type": "application/json"}
        )
        with urlopen(request, timeout=5) as response:
            confirmation: dict[str, object] = json.load(response)
            return confirmation

    expected_exit = (
        pytest.raises(OSError, match="mock checkout was unavailable")
        if mock_fails
        else nullcontext()
    )
    with ThreadPoolExecutor(max_workers=1) as client:
        with expected_exit, serve_attempt(tmp_path, catalog) as attempt:
            order = client.submit(post, attempt.url)
            assert received.wait(timeout=5)
            at_checkpoint = attempt.submissions
            assert at_checkpoint == ()
            assert attempt.checkpoint_submission_count == 1
        submissions_at_exit = attempt.submissions
        if mock_fails:
            assert submissions_at_exit == (None,)
            with pytest.raises(HTTPError) as response:
                order.result()
            with response.value as error_response:
                assert error_response.status == 503
        else:
            assert submissions_at_exit == (order.result(),)
