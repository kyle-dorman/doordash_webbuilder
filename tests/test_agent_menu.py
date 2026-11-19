from dataclasses import replace
from pathlib import Path

import pytest
from test_storefront import write_sample_feed
from webbuilder_agent.menu import check_full_menu
from webbuilder_agent.render import render
from webbuilder_shared.feed import Store, load_store

SECTION = """<details data-menu-section="{{ section.name }}"><summary>{{ section.name }}</summary>
{% for item in section.items %}
<div data-menu-item="{{ item.item_id }}">
<b>{{ item.name }}</b> <span>{{ item.display_price }}</span>
{% if item.description %}<p>{{ item.description }}</p>{% endif %}
{% if item.image_url %}<img src="{{ item.image_url }}">{% endif %}
{{ add_button(item) }}</div>{% endfor %}</details>"""


def build_menu(tmp_path: Path, *, photos: bool, section_template: str = SECTION) -> Store:
    store = load_store(write_sample_feed(tmp_path, photos), "123")
    sides, bento = store.sections
    # The same listing appears twice within one section, and again in a different section.
    rice = sides.items[0]
    store = replace(store, sections=(sides, replace(bento, items=(rice, *bento.items, rice))))
    files = {
        "index.html": '<h1>{{ store.name }}</h1><a href="./sides.html#menu">Menu</a>',
        "sides.html": '{% set section = store.sections[0] %}{% include "layout.html" %}'
        '<a href="bento.html">Continue to bento</a>',
        "bento.html": '{% set section = store.sections[1] %}{% include "layout.html" %}',
        "layout.html": section_template,
        "review.html": '{{ review_markup("sides.html") }}',
        "style.css": "",
    }
    render(store, files, tmp_path / "site")
    return store


@pytest.mark.parametrize("photos", [True, False])
def test_complete_menu_can_span_pages_and_use_disclosures(tmp_path: Path, photos: bool) -> None:
    store = build_menu(tmp_path, photos=photos)
    check_full_menu(store, tmp_path / "site")


@pytest.mark.parametrize(
    ("original", "replacement", "error"),
    [
        ("{{ section.name }}</summary>", "Specials</summary>", "section name"),
        ("in section.items %}", "in section.items[:-1] %}", "every item"),
        ("in section.items %}", "in section.items|sort(attribute='item_id') %}", "feed order"),
        ("{{ item.name }}</b>", "House rice</b>", "full name"),
        ("{{ item.display_price }}", "{{ item.display_price }}0", "full price"),
        ("{{ item.description }}", "Choose mild", "full description"),
        ("<p>{{ item.description }}", "<p hidden>{{ item.description }}", "full description"),
        ("{{ item.image_url }}", "placeholder.jpg", "supplied photo"),
        ("{{ add_button(item) }}", '<button data-add-item="100">Add</button>', "add_button"),
    ],
)
def test_missing_menu_information_is_reported(
    tmp_path: Path, original: str, replacement: str, error: str
) -> None:
    section_template = SECTION.replace(original, replacement)
    store = build_menu(tmp_path, photos=True, section_template=section_template)
    with pytest.raises(ValueError, match=error):
        check_full_menu(store, tmp_path / "site")


def test_full_menu_sections_must_be_reachable_and_in_order(tmp_path: Path) -> None:
    store = build_menu(tmp_path, photos=False)
    (tmp_path / "site" / "index.html").write_text('<a href="bento.html">Bento</a>')
    with pytest.raises(ValueError, match="every full-menu section"):
        check_full_menu(store, tmp_path / "site")
    (tmp_path / "site" / "index.html").write_text(
        '<a href="bento.html">Bento</a><a href="sides.html">Sides</a>'
    )
    with pytest.raises(ValueError, match="feed order"):
        check_full_menu(store, tmp_path / "site")
