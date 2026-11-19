"""Locations for generated storefronts and run evidence."""

from pathlib import Path
from urllib.parse import quote

RUNS = Path.home() / "data/webbuilder/runs"


def store_directory_name(store_id: str) -> str:
    """Keep the existing reference site names and use feed IDs for other stores."""
    pilot_names = {"265151": "thai-peacock", "26303866": "one-stop-roti"}
    return pilot_names.get(store_id, f"store-{quote(store_id, safe='')}")
