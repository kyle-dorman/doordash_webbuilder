"""Read the restaurant and menu fields used by storefront builders."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Item:
    item_id: str
    name: str
    description: str | None
    image_url: str | None
    price_cents: int
    currency: str
    display_price: str


@dataclass(frozen=True)
class Section:
    name: str
    items: tuple[Item, ...]


@dataclass(frozen=True)
class DayHours:
    day: str
    intervals: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Store:
    store_id: str
    name: str
    cuisine: str
    street: str
    city: str
    state: str
    zip_code: str
    country: str
    phone: str
    timezone: str
    header_image: str | None
    cover_image: str | None
    hours: tuple[DayHours, ...]
    sections: tuple[Section, ...]
    tags: tuple[str, ...] = ()


def load_store(feed_path: Path, store_id: str) -> Store:
    """Select a store and its location by ID, retaining the original menu order."""
    with feed_path.expanduser().open(encoding="utf-8") as source:
        restaurants = json.load(source)["restaurants"]
    store = next((s for s in restaurants if s["store_id"] == store_id), None)
    if store is None:
        raise ValueError(f"Store {store_id!r} was not found in {feed_path}")

    header = store["store_header"]["data"]
    locations = store["business_profile"]["locations"]
    location = next((loc for loc in locations if loc["store_id"] == store_id), None)
    if location is None:
        raise ValueError(f"Store {store_id!r} has no matching location in {feed_path}")
    address = location["address"]
    hours = tuple(
        DayHours(
            day=record["day"],
            intervals=tuple((span["open"], span["close"]) for span in record["intervals"]),
        )
        for record in location["open_hours"]
    )
    sections = []
    for section in store["menu_book"]["item_lists"]:
        items = []
        for entry in section["items"]:
            price = entry["price"]
            items.append(
                Item(
                    item_id=entry["id"],
                    name=entry["name"],
                    description=entry.get("description"),
                    image_url=entry.get("image_url"),
                    price_cents=price["unit_amount"],
                    currency=price["currency"],
                    display_price=price["display_string"],
                )
            )
        sections.append(Section(name=section["name"], items=tuple(items)))

    return Store(
        store_id=store_id,
        name=header["name"],
        cuisine=header["cuisine_type"],
        street=address["street"],
        city=address["city"],
        state=address["state"],
        zip_code=address["zip_code"],
        country=address["country"],
        phone=location["phone"],
        timezone=location["timezone"],
        header_image=header.get("header_image"),
        cover_image=header.get("cover_image"),
        hours=hours,
        sections=tuple(sections),
        tags=tuple(header.get("tags") or ()),
    )
