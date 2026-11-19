"""Verify two submitted menus against the source feed and place one mock Roti order."""

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlsplit

from playwright.async_api import Browser, Error, Page, async_playwright, expect
from webbuilder_mock_backend.server import Catalog, load_catalog
from webbuilder_shopper.computer_use.browser import VIEWPORT
from webbuilder_shopper.computer_use.report import file_digest, identify_build, write_json
from webbuilder_shopper.grading import GradeError
from webbuilder_shopper.serving import Attempt, serve_attempt
from webbuilder_shopper.viewport import read_cart, viewport_text

THAI = "265151"
ROTI = "26303866"
CURRY = "10703144790"


class FeedPrice(TypedDict):
    display_string: str


class FeedItem(TypedDict):
    id: str
    name: str
    description: str | None
    image_url: str | None
    price: FeedPrice


class FeedSection(TypedDict):
    name: str
    items: list[FeedItem]


def normalized(text: str) -> str:
    # Browsers collapse whitespace, and the stylesheet can change capitalization.
    return " ".join(text.casefold().split())


async def check_menu(page: Page, expected: list[FeedSection]) -> dict[str, object]:
    sections = page.locator("[data-menu-section]")
    names = await sections.evaluate_all("nodes => nodes.map(n => n.dataset.menuSection)")
    errors = []
    if names != [section["name"] for section in expected]:
        errors.append("Section names or order differ from feed")
    records = []
    for section, source in zip(await sections.all(), expected, strict=False):
        label = source["name"]
        if normalized(label) not in normalized(await section.inner_text()):
            errors.append(f"{label}: section title is missing from the visible text")
        rows = section.locator("[data-menu-item]")
        ids = await rows.evaluate_all("nodes => nodes.map(n => n.dataset.menuItem)")
        if ids != [item["id"] for item in source["items"]]:
            errors.append(f"{label}: item IDs or order differ from feed")
        items = []
        for row, item in zip(await rows.all(), source["items"], strict=False):
            item_id = item["id"]
            text = normalized(await row.inner_text())
            prices = re.findall(r"\$\s*\d+(?:,\d{3})*\.\d{2}\b", text)
            images = await row.locator("img").evaluate_all(
                "nodes => nodes.filter(n => n.checkVisibility()).map(n => n.currentSrc || n.src)"
            )
            button = row.locator("button[data-add-item]")
            price = item["price"]["display_string"]
            checks = {
                "visible": await row.is_visible(),
                "name": normalized(item["name"]) in text,
                "price": set(prices) == {price},
                "description": normalized(item["description"] or "") in text,
                "image": images == ([item["image_url"]] if item["image_url"] else []),
                "add_button": await button.count() == 1
                and await button.get_attribute("data-add-item") == item_id
                and await button.is_visible()
                and await button.is_enabled(),
            }
            for field, passed in checks.items():
                if not passed:
                    errors.append(f"{label} / {item_id}: {field} differs from feed or is unusable")
            items.append({"id": item_id, "name": item["name"], "price": price, "checks": checks})
        records.append({"section": label, "rendered_ids": ids, "items": items})
    return {
        "page": urlsplit(page.url).path,
        "status": "failed" if errors else "passed",
        "rendered_sections": names,
        "sections": records,
        "errors": errors,
    }


async def curry_order(page: Page, attempt: Attempt, evidence: Path) -> dict[str, object]:
    section = page.locator('[data-menu-section="Roti"]')
    row = section.locator(f'[data-menu-item="{CURRY}"]')
    await expect(row).to_contain_text("Curry Chicken", ignore_case=True)
    await expect(row).to_contain_text("$14.95")
    await row.get_by_role("button", name="Add Curry Chicken to cart", exact=True).click()
    await page.get_by_role("link", name="Go to cart", exact=True).click()
    cart = await read_cart(page)
    if [(normalized(name), qty) for name, qty in cart] != [
        ("curry chicken", 1)
    ] or attempt.checkpoint_submission_count:
        raise AssertionError(f"Incorrect cart before checkout: {cart!r}")
    await page.screenshot(path=evidence / "roti-cart.png", scale="css")
    await page.get_by_role("button", name="Place order", exact=True).click()
    heading = await viewport_text(page.get_by_role("heading", name="Simulated order confirmed"))
    lines = page.get_by_role("list", name="Confirmed items").get_by_role("listitem")
    await expect(lines).to_have_count(1)
    name = await viewport_text(lines.get_by_role("heading"))
    quantity = await viewport_text(lines.locator("[data-confirmed-quantity]"))
    line_total = await viewport_text(lines.get_by_label("Line total", exact=True))
    total = await viewport_text(page.get_by_label("Total", exact=True))
    await page.screenshot(path=evidence / "roti-receipt.png", scale="css")
    if (normalized(name), quantity, line_total, total) != (
        "curry chicken",
        "1 × $14.95",
        "$14.95",
        "$14.95",
    ):
        raise AssertionError(f"Unexpected receipt: {name}, {quantity}, {line_total}, total {total}")
    return {
        "heading": heading,
        "item": name,
        "quantity_and_unit_price": quantity,
        "line_total": line_total,
        "total": total,
        "cart_screenshot": "roti-cart.png",
        "receipt_screenshot": "roti-receipt.png",
    }


async def verify_store(
    browser: Browser,
    catalog: Catalog,
    site: Path,
    store_id: str,
    menu: list[FeedSection],
    evidence: Path,
) -> dict[str, object]:
    report: dict[str, object] = {"site": str(site), "build_sha256": identify_build(site)[1]}
    passed_menu = False
    try:
        with serve_attempt(site, catalog) as attempt:
            async with await browser.new_context(viewport=VIEWPORT) as context:
                context.set_default_timeout(5_000)
                page = await context.new_page()
                try:
                    await page.goto(attempt.url, wait_until="domcontentloaded")
                    # Use the same visible entry points a diner uses on these submitted builds.
                    entry = "Menu" if store_id == THAI else "Browse menu"
                    await page.get_by_role("link", name=entry, exact=True).click()
                    menu_report = await check_menu(page, menu)
                    report["menu"] = menu_report
                    passed_menu = menu_report["status"] == "passed"
                    if store_id == ROTI:
                        report["receipt"] = await curry_order(page, attempt, evidence)
                except (Error, AssertionError, GradeError) as error:
                    await page.screenshot(path=evidence / f"{store_id}-failure.png", scale="css")
                    report["failure_screenshot"] = f"{store_id}-failure.png"
                    report["error"] = str(error)
        report["submissions"] = attempt.submissions
        if store_id == ROTI:
            expected_order = {
                "store_id": ROTI,
                "items": [
                    {
                        "item_id": CURRY,
                        "name": "Curry Chicken",
                        "quantity": 1,
                        "unit_price_cents": 1495,
                        "line_total_cents": 1495,
                    }
                ],
                "subtotal_cents": 1495,
            }
            if attempt.submissions != (expected_order,):
                report["order_error"] = (
                    "Expected exactly one accepted order for Curry Chicken at $14.95"
                )
        if store_id == THAI and attempt.submissions:
            report["order_error"] = "Browsing the menu submitted an order"
        report["status"] = (
            "failed"
            if "error" in report or "order_error" in report or not passed_menu
            else "passed"
        )
    except (Error, OSError) as error:
        report.update(status="incomplete", error=str(error))
    return report


async def verify(feed: Path, thai: Path, roti: Path, evidence: Path) -> bool:
    restaurants = json.loads(feed.read_text(encoding="utf-8"))["restaurants"]
    menus = {store["store_id"]: store["menu_book"]["item_lists"] for store in restaurants}
    catalog = load_catalog(feed)
    results = {}
    async with async_playwright() as pw, await pw.chromium.launch() as browser:
        for store_id, site in ((THAI, thai), (ROTI, roti)):
            results[store_id] = await verify_store(
                browser, catalog, site, store_id, menus[store_id], evidence
            )
    passed = all(result["status"] == "passed" for result in results.values())
    write_json(
        evidence / "report.json",
        {
            "status": "passed" if passed else "failed",
            "feed_sha256": file_digest(feed),
            "viewport": VIEWPORT,
            "stores": results,
        },
    )
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("feed", "thai-site", "roti-site", "evidence"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    args = parser.parse_args()
    feed, thai, roti, evidence = (
        path.expanduser().resolve()
        for path in (args.feed, args.thai_site, args.roti_site, args.evidence)
    )
    if any(evidence.is_relative_to(site) for site in (thai, roti)):
        parser.error("Evidence must be outside the submitted sites")
    if evidence.exists() and (not evidence.is_dir() or any(evidence.iterdir())):
        parser.error("Choose a new or empty evidence folder")
    evidence.mkdir(parents=True, exist_ok=True)
    passed = asyncio.run(verify(feed, thai, roti, evidence))
    print(f"{'PASSED' if passed else 'FAILED'} · {evidence / 'report.json'}")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
