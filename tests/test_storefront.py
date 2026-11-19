import json
from collections import defaultdict
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import pytest
from webbuilder_agent.feed import Section, featured_items, load_store
from webbuilder_agent.storefront import generate

HEADER_URL = "https://cdn.doordash.com/media/store/header/test.jpg"
COVER_URL = "https://cdn.doordash.com/media/restaurant/cover/rice%20spice.png"
ITEM_URL = "https://img.cdn4dd.com/photos/rice.jpg?width=640&height=400"


class Page(HTMLParser):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.elements: defaultdict[str, list[dict[str, str | None]]] = defaultdict(list)
        self.text: list[str] = []
        self.link_text: defaultdict[str, list[str]] = defaultdict(list)
        self.open_href: str | None = None
        self.section_ids: list[str | None] = []
        self.menu_destinations: list[str | None] = []
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        self.elements[tag].append(attributes)
        if tag == "a":
            self.open_href = attributes.get("href")
        if tag == "section":
            self.section_ids.append(attributes.get("id"))
        if tag == "article" and "data-item-id" in attributes:
            self.menu_destinations.append(self.section_ids[-1] if self.section_ids else None)

    def handle_endtag(self, tag: str) -> None:
        if tag == "section":
            self.section_ids.pop()
        if tag == "a":
            self.open_href = None

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self.open_href:
            self.link_text[self.open_href].append(data.strip().casefold())


def write_sample_feed(tmp_path: Path, with_photos: bool) -> Path:
    address = {
        "street": "1 Main St",
        "city": "Portland",
        "state": "OR",
        "zip_code": "97205",
        "country": "US",
    }
    hours = [
        {
            "day": "Monday",
            "intervals": [
                {"open": "08:10", "close": "09:25"},
                {"open": "10:37", "close": "11:48"},
            ],
        }
    ]
    location = {
        "store_id": "123",
        "address": address,
        "phone": "+15035550101",
        "timezone": "US/Pacific",
        "open_hours": hours,
    }
    header = {
        "name": "Rice & <Spice>",
        "cuisine_type": "Thai",
        "address": address,
        "tags": ["thai"],
        "price_range": "$",
        "header_image": HEADER_URL if with_photos else None,
        "cover_image": COVER_URL if with_photos else None,
    }
    free_item = {
        "id": "200",
        "name": "Rice <small>",
        "price": {"unit_amount": 0, "currency": "USD", "display_string": "$0.00"},
        "description": None,
        "image_url": None,
    }
    regular_item = {
        **free_item,
        "id": "100",
        "price": {"unit_amount": 250, "currency": "USD", "display_string": "$2.50"},
        "description": "Choose mild & sweet or <hot>.",
        "image_url": ITEM_URL if with_photos else None,
    }
    store = {
        "store_id": "123",
        "store_header": {"data": header},
        "business_profile": {"locations": [location]},
        "menu_book": {
            "item_lists": [
                {"name": "Sides & Snacks", "items": [free_item]},
                {"name": "Bento", "items": [regular_item]},
            ]
        },
    }
    feed = tmp_path / "feed.json"
    feed.write_text(json.dumps({"restaurants": [store]}), encoding="utf-8")
    return feed


@pytest.mark.parametrize("with_photos", [False, True], ids=["text-only", "cdn-photos"])
def test_storefront_keeps_menu_data_hours_and_photo_urls(tmp_path: Path, with_photos: bool) -> None:
    feed = write_sample_feed(tmp_path, with_photos)
    output = tmp_path / "storefront"
    with patch("socket.getaddrinfo", side_effect=AssertionError("Unexpected network lookup")):
        index = generate(feed, "123", output)
    assert index == output / "index.html"
    home = Page(index)
    menu = Page(output / "menu.html")
    visit = Page(output / "visit.html")
    assert "menu" in home.link_text["menu.html"]
    assert "order now" in " ".join(home.link_text["menu.html"])
    assert any(a["href"] == "visit.html" for a in home.elements["a"])
    item_links = {href for href in home.link_text if href.startswith("menu.html#item-")}
    assert item_links == ({"menu.html#item-100"} if with_photos else set())
    elements = menu.elements
    assert elements["body"][0]["data-store-id"] == "123"
    assert [
        (item["id"], item["data-item-id"], item["data-currency"], item["data-price-cents"])
        for item in elements["article"]
        if "data-item-id" in item
    ] == [("item-200", "200", "USD", "0"), ("item-100", "100", "USD", "250")]
    destinations = {
        href[1:]
        for anchor in elements["a"]
        if (href := anchor.get("href")) and href.startswith("#")
    }
    assert len(set(menu.menu_destinations)) == 2
    assert all(section in destinations for section in menu.menu_destinations)
    text = " ".join(menu.text)
    for source_text in [
        "Sides & Snacks",
        "Bento",
        "Choose mild & sweet or <hot>.",
        "$0.00",
        "$2.50",
    ]:
        assert source_text in text
    assert text.count("Rice <small>") >= 2
    assert "Rice & <Spice>" in " ".join(home.text)
    visit_text = " ".join(visit.text)
    for detail in ["1 Main St", "Portland", "97205", "Monday", "8:10", "9:25", "10:37", "11:48"]:
        assert detail in visit_text
    phone = "".join(visit.link_text["tel:+15035550101"])
    assert "5035550101" in "".join(char for char in phone if char.isdigit())
    expected_photos = {HEADER_URL, COVER_URL, ITEM_URL} if with_photos else set()
    pages = (home, menu, visit)
    assert {img["src"] for page in pages for img in page.elements["img"]} == expected_photos
    assert not (output / "assets" / "photos").exists()
    assert not any(path.suffix in {".jpg", ".png", ".webp", ".avif"} for path in output.rglob("*"))
    for page in pages:
        styles = [
            link.get("href") for link in page.elements["link"] if link.get("rel") == "stylesheet"
        ]
        assert styles and all(href and (output / href).is_file() for href in styles)


def test_featured_items_prioritize_tags_then_feed_order_among_photographed_dishes(
    tmp_path: Path,
) -> None:
    store = load_store(write_sample_feed(tmp_path, with_photos=True), "123")
    sample = store.sections[1].items[0]
    items = (replace(sample, item_id="0", name="Crispy Noodles", image_url=None),) + tuple(
        replace(sample, item_id=str(i), name=name, image_url=f"https://img.cdn4dd.com/{i}.jpg")
        for i, name in enumerate(["Soup", "Salad", "Steamed Noodles", "Pudding"], start=1)
    )
    store = replace(store, tags=("noodles",), sections=(Section("Menu", items),))
    assert [item.name for item in featured_items(store)] == ["Steamed Noodles", "Soup", "Salad"]
