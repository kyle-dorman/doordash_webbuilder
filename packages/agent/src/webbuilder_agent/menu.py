"""Check the rendered full-menu rows against the feed before submission."""

import re
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag
from webbuilder_shared.feed import Item, Store


def check_full_menu(store: Store, site: Path) -> None:
    """Raise ValueError if the reachable menu is missing or differs from the feed."""
    sections = list(_reachable_menu_sections(site))
    section_names = [section["data-menu-section"] for section in sections]
    if section_names != [section.name for section in store.sections]:
        raise ValueError("Link to every full-menu section in feed order, including repeats.")

    for section, rendered in zip(store.sections, sections, strict=True):
        if _normalize_spaces(section.name) not in _normalize_spaces(rendered.get_text(" ")):
            raise ValueError(f"Display the section name {section.name!r} in its menu section.")

        rows = rendered.select("[data-menu-item]")
        item_ids = [row["data-menu-item"] for row in rows]
        if item_ids != [item.item_id for item in section.items]:
            raise ValueError(
                f"List every item in {section.name!r} in feed order, including repeats."
            )
        for item, row in zip(section.items, rows, strict=True):
            _check_item(item, row)


def _reachable_menu_sections(site: Path) -> Iterator[Tag]:
    """Follow local links from the homepage in the order they appear."""
    pending = deque(["index.html"])
    unvisited = {page.name for page in site.glob("*.html")} - {"index.html"}
    while pending:
        name = pending.popleft()
        document = BeautifulSoup((site / name).read_text(encoding="utf-8"), "html.parser")
        for element in document.select("head, script, style, template, [hidden], [inert]"):
            element.decompose()
        yield from document.select("[data-menu-section]")

        for link in document.select("a[href]"):
            url = urlsplit(urljoin(f"/{name}", str(link["href"])))
            filename = url.path.removeprefix("/")
            if not url.scheme and not url.netloc and filename in unvisited:
                pending.append(filename)
                unvisited.remove(filename)


def _normalize_spaces(text: str) -> str:
    return " ".join(text.split())


def _check_item(item: Item, row: Tag) -> None:
    # Tags can separate words (<p>Hot</p><p>rice</p>) or split one word (Tom-<b>Yum</b>).
    row_texts = [_normalize_spaces(row.get_text(separator)) for separator in (" ", "")]
    for field, value in (
        ("name", item.name),
        ("price", item.display_price),
        ("description", item.description),
    ):
        if not value:
            continue
        pattern = re.escape(_normalize_spaces(value))
        if field == "price":
            pattern += r"(?!\d|[.,]\d)"  # A price must match the whole amount.
        if not any(re.search(pattern, text) for text in row_texts):
            raise ValueError(f"Menu item {item.item_id} is missing its full {field}: {value}")

    if item.image_url and not row.find("img", src=item.image_url):
        raise ValueError(f"Menu item {item.item_id} is missing its supplied photo.")
    buttons = row.select("button[data-add-item]:not([disabled])")
    if not buttons or any(button["data-add-item"] != item.item_id for button in buttons):
        raise ValueError(f"Menu item {item.item_id} needs its own working add_button(item).")
