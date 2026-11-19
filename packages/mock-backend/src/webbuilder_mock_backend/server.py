"""Confirm simulated restaurant orders using prices from the local feed."""

import argparse
import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# JSON numbers up to this value can represent every integer exactly in the storefront.
MAX_SAFE_INTEGER = 2**53 - 1


@dataclass(frozen=True)
class MenuItem:
    name: str
    price_cents: int


type Catalog = dict[str, dict[str, MenuItem]]


def load_catalog(feed: Path) -> Catalog:
    with feed.expanduser().open(encoding="utf-8") as source:
        stores = json.load(source)["restaurants"]
    catalog: Catalog = {}
    for store in stores:
        menu = {}
        for section in store["menu_book"]["item_lists"]:
            for entry in section["items"]:
                cents = entry["price"]["unit_amount"]
                if type(cents) is not int or cents < 0:
                    raise ValueError(f"Invalid feed price for item {entry['id']!r}")
                menu[entry["id"]] = MenuItem(entry["name"], cents)
        catalog[store["store_id"]] = menu
    return catalog


def confirm_order(order: object, catalog: Catalog) -> dict[str, object]:
    if not isinstance(order, dict):
        raise ValueError("Send an order containing a store ID and a list of items.")
    store_id = order.get("store_id")
    if not isinstance(store_id, str) or store_id not in catalog:
        raise ValueError("Unknown store ID.")
    selections = order.get("items")
    if not isinstance(selections, list) or not selections:
        raise ValueError("Select at least one menu item.")

    menu = catalog[store_id]
    confirmed = []
    selected_ids = set()
    subtotal = 0
    for selection in selections:
        if not isinstance(selection, dict):
            raise ValueError("Each selection must contain an item ID and a quantity.")
        item_id = selection.get("item_id")
        if not isinstance(item_id, str) or item_id not in menu:
            raise ValueError(f"Item {item_id!r} is not on this restaurant's menu.")
        if item_id in selected_ids:
            raise ValueError(f"Send a single quantity for item {item_id!r}.")
        quantity = selection.get("quantity")
        if type(quantity) is not int or quantity < 1:
            raise ValueError(f"Choose a positive whole-number quantity for {menu[item_id].name}.")
        if quantity > MAX_SAFE_INTEGER:
            raise ValueError(f"Choose a smaller quantity for {menu[item_id].name}.")
        selected_ids.add(item_id)
        item = menu[item_id]
        amount = item.price_cents * quantity
        subtotal += amount
        if subtotal > MAX_SAFE_INTEGER:
            raise ValueError("Reduce the quantity to keep the order total within range.")
        confirmed.append(
            {
                "item_id": item_id,
                "name": item.name,
                "quantity": quantity,
                "unit_price_cents": item.price_cents,
                "line_total_cents": amount,
            }
        )
    return {"store_id": store_id, "items": confirmed, "subtotal_cents": subtotal}


class OrderServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], catalog: Catalog) -> None:
        self.catalog = catalog
        super().__init__(address, OrderHandler)


class OrderHandler(BaseHTTPRequestHandler):
    server: OrderServer

    def reply(self, status: int, data: dict[str, object]) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/orders":
            self.reply(404, {"error": "Unknown endpoint."})
            return
        if self.headers.get_content_type() != "application/json":
            self.reply(415, {"error": "Submit the order as application/json."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0:
                raise ValueError("Missing order body.")
            if size > 64 * 1024:
                self.reply(413, {"error": "Order exceeds 64 KiB."})
                return
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError("The order body was incomplete.")
            order = json.loads(body)
            confirmation = confirm_order(order, self.server.catalog)
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
            self.reply(400, {"error": "The order must be valid JSON."})
            return
        except ValueError as error:
            self.reply(400, {"error": str(error)})
            return
        self.reply(200, confirmation)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--feed",
        type=Path,
        default=Path("~/data/webbuilder/restaurants_feed.json"),
        help="Restaurant JSON feed (default: %(default)s)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Local address (default: %(default)s)")
    parser.add_argument("--port", type=int, default=8001, help="Local port (default: %(default)s)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        catalog = load_catalog(args.feed)
        with OrderServer((args.host, args.port), catalog) as server:
            print(f"Serving mock checkout at http://{args.host}:{server.server_port}/", flush=True)
            server.serve_forever()
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
