"""Reference feed API and ranking of its featured menu items."""

import re

from webbuilder_shared.feed import DayHours, Item, Section, Store, load_store

__all__ = ["DayHours", "Item", "Section", "Store", "featured_items", "load_store"]


def _match_text(text: str) -> str:
    """Normalize whole words, including common menu plurals such as noodles and sandwiches."""
    words = re.findall(r"[^\W_]+", text.casefold())
    for index, word in enumerate(words):
        if word.endswith(("ches", "shes", "xes", "sses")):
            words[index] = word[:-2]
        elif len(word) > 3 and not word.endswith("ss"):
            words[index] = word.removesuffix("s")
    return " " + " ".join(words) + " "


def featured_items(store: Store) -> list[Item]:
    """Rank pictured dishes by store tags, using the original order for ties."""
    cuisine = _match_text(store.cuisine)
    tags = {_match_text(tag) for tag in store.tags if tag.strip()}
    ranked = []
    for section in store.sections:
        section_text = _match_text(section.name)
        for item in section.items:
            if not item.image_url:
                continue
            fields = (
                (_match_text(item.name), 4),
                (section_text, 2),
                (_match_text(item.description or ""), 1),
            )
            scores = {tag: sum(weight for field, weight in fields if tag in field) for tag in tags}
            cuisine_score = scores.pop(cuisine, 0)
            ranked.append(((sum(scores.values()), cuisine_score), item))

    result: list[Item] = []
    seen_names: set[str] = set()
    seen_ids: set[str] = set()
    for _, item in sorted(ranked, key=lambda entry: entry[0], reverse=True):
        name = " ".join(item.name.casefold().split())
        if name not in seen_names and item.item_id not in seen_ids:
            result.append(item)
            seen_names.add(name)
            seen_ids.add(item.item_id)
            if len(result) == 3:
                break
    return result
