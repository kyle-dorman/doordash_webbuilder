"""Generate a restaurant menu that can be browsed directly from disk."""

import argparse
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from jinja2 import Environment, PackageLoader, StrictUndefined
from webbuilder_shared.cart import (
    CART_STATUS,
    add_button,
    cart_scripts,
    clock,
    phone,
    review_markup,
    write_cart_assets,
)
from webbuilder_shared.feed import load_store

from .feed import featured_items


def generate(feed: Path, store_id: str, output: Path) -> Path:
    """Write the selected store's storefront and return its HTML path."""
    store = load_store(feed, store_id)
    output = output.expanduser()

    templates = Environment(
        loader=PackageLoader("webbuilder_static", "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    templates.filters.update(clock=clock, phone=phone)
    featured = featured_items(store)
    templates.globals.update(
        add_button=add_button,
        cart_scripts=cart_scripts(store, reference=True),
        cart_status=CART_STATUS,
        review_markup=review_markup,
    )
    pages = ("review.html", "menu.html", "visit.html", "index.html")
    assets = output / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    resources = files("webbuilder_static").joinpath("templates")
    with TemporaryDirectory(dir=output) as staging:
        stage = Path(staging)
        for page in pages:
            html = templates.get_template(page).render(store=store, page=page, featured=featured)
            (stage / page).write_text(html, encoding="utf-8")
        write_cart_assets(stage, reference=True)
        (stage / "assets/cart.js").replace(assets / "cart.js")
        for filename in ("storefront.css", "menu.js"):
            (stage / filename).write_bytes(resources.joinpath(filename).read_bytes())
            (stage / filename).replace(assets / filename)
        # Publish the landing page after its linked pages and assets.
        for page in pages:
            (stage / page).replace(output / page)
    return output / "index.html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", type=Path, required=True, help="Path to the restaurant JSON feed")
    parser.add_argument("--store-id", required=True, help="Store ID in the feed")
    parser.add_argument("--output", type=Path, required=True, help="Storefront output directory")
    args = parser.parse_args()
    try:
        index = generate(args.feed, args.store_id, args.output)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    print(index.resolve())


if __name__ == "__main__":
    main()
