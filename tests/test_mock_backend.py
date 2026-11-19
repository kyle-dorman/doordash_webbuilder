import json
from collections.abc import Iterator
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from webbuilder_mock_backend.server import OrderServer, load_catalog


@pytest.fixture(scope="module")
def endpoint(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    rolls = {"id": "r", "name": "Spring rolls", "price": {"unit_amount": 850}}
    rice = {"id": "s", "name": "Rice", "price": {"unit_amount": 250}}
    curry = {"id": "c", "name": "Curry Chicken", "price": {"unit_amount": 1495}}
    fork = {"id": "f", "name": "Fork", "price": {"unit_amount": 0}}
    stores = [
        {"store_id": "thai", "menu_book": {"item_lists": [{"items": [rolls]}, {"items": [rice]}]}},
        {"store_id": "roti", "menu_book": {"item_lists": [{"items": [curry, fork]}]}},
    ]
    path = tmp_path_factory.mktemp("mock") / "feed.json"
    path.write_text(json.dumps({"restaurants": stores}), encoding="utf-8")
    with OrderServer(("127.0.0.1", 0), load_catalog(path)) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/orders"
        finally:
            server.shutdown()
            thread.join()


def post_order(endpoint: str, payload: object) -> tuple[int, dict[str, object]]:
    request = Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        assert response.headers.get_content_type() == "application/json"
        return response.status, json.load(response)


def test_confirmed_items_and_subtotal_use_store_feed_prices(endpoint: str) -> None:
    payload = {
        "store_id": "thai",
        "items": [
            {"item_id": "r", "quantity": 2, "name": "Other", "unit_price_cents": 1},
            {"item_id": "s", "quantity": 1},
        ],
        "subtotal_cents": 1,
    }
    assert post_order(endpoint, payload) == (
        200,
        {
            "store_id": "thai",
            "items": [
                {
                    "item_id": "r",
                    "name": "Spring rolls",
                    "quantity": 2,
                    "unit_price_cents": 850,
                    "line_total_cents": 1700,
                },
                {
                    "item_id": "s",
                    "name": "Rice",
                    "quantity": 1,
                    "unit_price_cents": 250,
                    "line_total_cents": 250,
                },
            ],
            "subtotal_cents": 1950,
        },
    )
    status, order = post_order(
        endpoint, {"store_id": "roti", "items": [{"item_id": "f", "quantity": 2}]}
    )
    assert status == 200
    assert order["subtotal_cents"] == 0


@pytest.mark.parametrize(
    "selection",
    [
        {"item_id": "c", "quantity": 1},
        {"item_id": "s", "quantity": 0},
        {"item_id": "s", "quantity": -1},
        {"item_id": "s", "quantity": 1.5},
        {"item_id": "s", "quantity": True},
        {"item_id": "s", "quantity": "2"},
        {"item_id": "r", "quantity": 2},
    ],
)
def test_invalid_selection_rejects_the_entire_order(endpoint: str, selection: object) -> None:
    payload = {"store_id": "thai", "items": [{"item_id": "r", "quantity": 1}, selection]}
    status, body = post_order(endpoint, payload)
    assert status == 400
    assert set(body) == {"error"}
    assert body["error"]


@pytest.mark.parametrize(
    "payload",
    [
        {"store_id": "missing", "items": [{"item_id": "r", "quantity": 1}]},
        {"store_id": "thai", "items": []},
    ],
)
def test_unknown_store_and_empty_orders_are_rejected(endpoint: str, payload: object) -> None:
    status, body = post_order(endpoint, payload)
    assert status == 400
    assert set(body) == {"error"}


@pytest.mark.parametrize(
    "store_id, items",
    [
        ("roti", [{"item_id": "f", "quantity": 2**53}]),
        (
            "thai",
            [
                {"item_id": "s", "quantity": (2**53 - 1) // 250},
                {"item_id": "r", "quantity": 1},
            ],
        ),
    ],
)
def test_confirmation_numbers_must_be_exact_in_the_browser(
    endpoint: str, store_id: str, items: list[dict[str, object]]
) -> None:
    status, body = post_order(endpoint, {"store_id": store_id, "items": items})
    assert status == 400
    assert set(body) == {"error"}
