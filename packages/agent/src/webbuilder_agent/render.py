"""Render the designer's templates against one store and photograph a local preview."""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from jinja2 import DictLoader, StrictUndefined
from jinja2.sandbox import ImmutableSandboxedEnvironment
from markupsafe import escape
from playwright.async_api import Error as BrowserError
from playwright.async_api import Route, async_playwright
from playwright.async_api import TimeoutError as BrowserTimeout
from webbuilder_shared.cart import (
    add_button,
    cart_support,
    clock,
    phone,
    review_markup,
    write_cart_assets,
)
from webbuilder_shared.feed import Store

PAGE_NAME = re.compile(r"[a-z][a-z0-9-]*\.html")
_DOCUMENT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; base-uri 'none'; \
style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; \
img-src 'self' {image_origins}; form-action 'none'">
<title>{title}</title><link rel="stylesheet" href="style.css">
<style>[hidden]{{display:none!important}}.visually-hidden{{position:absolute;width:1px;\
height:1px;padding:0;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap;\
border:0}}</style></head><body>{body}
{support}{script}</body></html>
"""


def mood_assignment(store: Store) -> str:
    brief = files("webbuilder_agent").joinpath("mood-brief.txt").read_text(encoding="utf-8")
    return brief + "\nRestaurant feed:\n" + json.dumps(asdict(store), ensure_ascii=False, indent=2)


def storefront_assignment(board: dict[str, object]) -> str:
    brief = files("webbuilder_agent").joinpath("brief.txt").read_text(encoding="utf-8")
    return brief + "\nYour mood board:\n" + json.dumps(board, ensure_ascii=False, indent=2)


def _image_origins(store: Store) -> str:
    urls = [store.cover_image, store.header_image]
    urls.extend(item.image_url for section in store.sections for item in section.items)
    origins = set()
    for url in urls:
        if not url:
            continue
        parts = urlsplit(url)
        if parts.scheme in {"https", "http"} and parts.hostname:
            origins.add(f"{parts.scheme}://{parts.netloc}")
    return " ".join(sorted(origins))


def render(store: Store, sources: dict[str, str], output: Path) -> None:
    """Generate pages into a fresh preview directory. Template lookup is confined to this draft."""
    missing = {"index.html", "review.html", "style.css"} - sources.keys()
    if missing:
        raise ValueError("Missing required design files: " + ", ".join(sorted(missing)))
    env = ImmutableSandboxedEnvironment(
        loader=DictLoader(sources), autoescape=True, undefined=StrictUndefined
    )
    env.filters.update(clock=clock, phone=phone)
    env.globals.update(add_button=add_button, review_markup=review_markup)
    image_origins = escape(_image_origins(store))
    support = cart_support(store)
    write_cart_assets(output)
    script = ""
    if "storefront.js" in sources:
        (output / "storefront.js").write_text(sources["storefront.js"], encoding="utf-8")
        script = '\n<script src="storefront.js" defer></script>'
    for name in sources:
        if name in {"style.css", "storefront.js", "layout.html"}:
            continue
        if not PAGE_NAME.fullmatch(name):
            raise ValueError(f"Invalid page name {name!r}")
        body = env.get_template(name).render(store=store, page=name)
        if name == "review.html" and 'id="confirmed-line-template"' not in body:
            raise ValueError("review.html must include review_markup with your menu destination")
        title = store.name if name == "index.html" else f"{Path(name).stem.title()} | {store.name}"
        page = _DOCUMENT.format(
            title=escape(title),
            image_origins=image_origins,
            body=body,
            support=support,
            script=script,
        )
        (output / name).write_text(page, encoding="utf-8")
    (output / "style.css").write_text(sources["style.css"], encoding="utf-8")


class _PreviewHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@asynccontextmanager
async def _serve_preview(site: Path) -> AsyncIterator[str]:
    handler = partial(_PreviewHandler, directory=str(site))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=partial(server.serve_forever, poll_interval=0.05), daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            await asyncio.to_thread(server.shutdown)
            thread.join()


async def screenshot(site: Path, page: str, click: str | None = None) -> bytes:
    """Capture the shopper's desktop viewport, optionally after activating a control."""
    filename, _, anchor = page.partition("#")
    if not PAGE_NAME.fullmatch(filename) or not (site / filename).is_file():
        raise ValueError(f"Preview page does not exist: {filename!r}")

    async with _serve_preview(site) as origin, async_playwright() as driver:

        async def allow_preview_request(route: Route) -> None:
            request = route.request
            local = request.url.startswith(origin)
            https_image = request.resource_type == "image" and request.url.startswith("https://")
            if request.method == "GET" and (local or https_image):
                await route.continue_()
            else:
                await route.abort()

        browser = await driver.chromium.launch()
        tab = await browser.new_page(
            viewport={"width": 1280, "height": 900}, service_workers="block"
        )
        await tab.context.route("**/*", allow_preview_request)
        await tab.goto(f"{origin}{filename}#{anchor}", wait_until="domcontentloaded")
        try:
            await tab.wait_for_load_state("load", timeout=8000)
        except BrowserTimeout:
            pass  # Still show the diner experience when a feed image is slow.

        if click is not None:
            try:
                await tab.locator("css=" + click).click(timeout=3000)
            except BrowserError as error:
                reason = error.message.splitlines()[0]
                raise ValueError(f"Could not click {click!r} on {page}: {reason}") from error
        if not tab.url.startswith(origin):
            raise ValueError("The preview left the storefront. Use a local interaction.")
        return await tab.screenshot(type="png", animations="disabled", timeout=15000)
