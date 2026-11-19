"""HTML fragments and browser behavior shared by storefront renderers."""

import re
from datetime import time
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined
from markupsafe import Markup

from .feed import Item, Store

_templates = Environment(
    loader=PackageLoader("webbuilder_shared", "templates"),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
CART_STATUS = Markup('<p class="visually-hidden" role="status" data-cart-status></p>')


def clock(value: str) -> str:
    parsed = time.fromisoformat(value)
    return f"{parsed.hour % 12 or 12}:{parsed.minute:02d} {'AM' if parsed.hour < 12 else 'PM'}"


def phone(value: str) -> str:
    return re.sub(r"^(?:\+1)?(\d{3})(\d{3})(\d{4})$", r"(\1) \2-\3", value)


def add_button(item: Item) -> Markup:
    """Render the shared, item-bound control inside the builder's menu layout."""
    return Markup(_templates.get_template("add_button.html").render(item=item))


def cart_scripts(store: Store, *, reference: bool = False) -> Markup:
    """Serialize the complete catalog with HTML-safe JSON and load the cart."""
    catalog: dict[str, object] = {
        "store_id": store.store_id,
        "items": [
            {
                "item_id": item.item_id,
                "name": item.name,
                "price_cents": item.price_cents,
                "currency": item.currency,
            }
            for section in store.sections
            for item in section.items
        ],
    }
    if not reference:
        catalog["store_name"] = store.name
    return Markup(_templates.get_template("scripts.html").render(cart_catalog=catalog))


def cart_support(store: Store) -> Markup:
    """Place once on each agent-designed page, including its review page."""
    return CART_STATUS + "\n" + cart_scripts(store)


def review_markup(menu_href: str, *, embedded_status: bool = False) -> Markup:
    """Render the cart and receipt with the builder's return-to-menu link."""
    return Markup(
        _templates.get_template("review.html").render(
            menu_href=menu_href, embedded_status=embedded_status, cart_status=CART_STATUS
        )
    )


def write_cart_assets(output: Path, *, reference: bool = False) -> None:
    """Write the common client, retaining the reference build's original title lookup."""
    restaurant_title = (
        '${document.querySelector(".wordmark").textContent.trim()}'
        if reference
        else "${catalog.store_name}"
    )
    script = _templates.get_template("cart.js").render(restaurant_title=restaurant_title)
    assets = output / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "cart.js").write_text(script + "\n", encoding="utf-8")
