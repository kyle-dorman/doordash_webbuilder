import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from shutil import which
from subprocess import PIPE, Popen
from sys import executable
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pytest


@contextmanager
def serve(name: str, *args: str, cwd: Path) -> Iterator[tuple[Popen[str], str]]:
    command = which(name, path=str(Path(executable).parent))
    assert command is not None
    with (
        Popen([command, "--port", "0", *args], cwd=cwd, stdout=PIPE, text=True) as server,
        ThreadPoolExecutor(max_workers=1) as reader,
    ):
        try:
            assert server.stdout is not None
            banner = reader.submit(server.stdout.readline).result(timeout=10)
            base_url = banner.strip().split()[-1]
            assert base_url.startswith("http://127.0.0.1:")
            yield server, base_url
        finally:
            server.terminate()


def test_serve_storefront_serves_pages_and_assets_from_selected_directory(tmp_path: Path) -> None:
    files = {
        "index.html": b'<a href="menu.html">Menu</a>',
        "menu.html": b'<link rel="stylesheet" href="assets/storefront.css">',
        "assets/storefront.css": b"body { color: navy; }",
    }
    storefront = tmp_path / "storefront"
    (storefront / "assets").mkdir(parents=True)
    for name, content in files.items():
        (storefront / name).write_bytes(content)

    with serve("serve-storefront", "--directory", "storefront", cwd=tmp_path) as (_, base_url):
        for name, content in files.items():
            path = "" if name == "index.html" else name
            with urlopen(base_url + path, timeout=5) as response:
                assert response.read() == content


def test_storefront_forwards_order_and_handles_unavailable_mock(tmp_path: Path) -> None:
    item = {"id": "side", "name": "Rice", "price": {"unit_amount": 250}}
    store = {"store_id": "thai", "menu_book": {"item_lists": [{"items": [item]}]}}
    (tmp_path / "feed.json").write_text(json.dumps({"restaurants": [store]}), encoding="utf-8")
    (tmp_path / "index.html").touch()
    with (
        serve("serve-mock-backend", "--feed", "feed.json", cwd=tmp_path) as (mock, mock_url),
        serve(
            "serve-storefront",
            "--directory",
            ".",
            "--mock-port",
            str(urlsplit(mock_url).port),
            cwd=tmp_path,
        ) as (_, base_url),
    ):

        def order(quantity: int) -> Request:
            body = {"store_id": "thai", "items": [{"item_id": "side", "quantity": quantity}]}
            return Request(
                base_url + "orders", json.dumps(body).encode(), {"Content-Type": "application/json"}
            )

        with urlopen(order(2), timeout=5) as response:
            assert response.status == 200
            assert json.load(response)["subtotal_cents"] == 500

        with pytest.raises(HTTPError) as invalid:
            urlopen(order(0), timeout=5)
        assert invalid.value.code == 400
        assert json.load(invalid.value)["error"]

        mock.terminate()
        mock.wait(timeout=5)
        with pytest.raises(HTTPError) as unavailable:
            urlopen(order(2), timeout=5)
        assert unavailable.value.code == 502
        assert json.load(unavailable.value)["error"]
