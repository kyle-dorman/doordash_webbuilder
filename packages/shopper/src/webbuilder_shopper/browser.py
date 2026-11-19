"""Playwright observations and shopper actions for the Thai Peacock stories."""

import re
from typing import Literal

from playwright.sync_api import Locator, Page, expect

from .grading import (
    RICE,
    ROLLS,
    TEA,
    GradeError,
    ReceiptLine,
    grade_checkout,
    grade_contact,
    grade_hours,
    grade_initial_cart,
    grade_soup,
)


def visible_text(locator: Locator) -> str:
    expect(locator).to_be_visible()
    return " ".join(locator.inner_text().split())


def read_cart(page: Page) -> list[tuple[str, int]]:
    """Read every visible cart line at the edit story's first checkpoint."""
    cart = page.get_by_role("list", name="Cart items")
    expect(cart).to_be_visible()
    lines = []
    for row in cart.get_by_role("listitem").all():
        name = visible_text(row.get_by_role("heading"))
        count = visible_text(row.get_by_label("Quantity", exact=True))
        try:
            lines.append((name, int(count)))
        except ValueError as error:
            raise GradeError(f"Invalid visible cart quantity {count!r} for {name}") from error
    return lines


def read_confirmation(page: Page) -> tuple[list[ReceiptLine], str]:
    """Read the visible receipt independently of the checkout response."""
    expect(
        page.get_by_role("heading", name="Simulated order confirmed", exact=True)
    ).to_be_visible()
    expect(page.get_by_role("link", name="Thai Peacock", exact=True)).to_be_visible()
    items = page.get_by_role("list", name="Confirmed items")
    expect(items).to_be_visible()
    lines = []
    for row in items.get_by_role("listitem").all():
        name = visible_text(row.get_by_role("heading"))
        unit = visible_text(row.get_by_text(re.compile(r"^\s*\d+\s*[×x]\s*", re.I)))
        quantity, price = re.split(r"\s*[×x]\s*", unit, maxsplit=1, flags=re.I)
        lines.append(
            ReceiptLine(name, int(quantity), price, visible_text(row.get_by_label("Line total")))
        )
    return lines, visible_text(page.get_by_label("Total", exact=True))


def verify_start(page: Page) -> None:
    """Check the fresh session through the cart link, then start shopping from Home."""
    home = page.get_by_role("heading", name="Thai Peacock", exact=True)
    expect(home).to_be_visible()
    page.get_by_role("link", name="Cart", exact=True).click()
    expect(page.get_by_text("Your cart is empty.", exact=True)).to_be_visible()
    expect(page.get_by_role("list", name="Cart items").get_by_role("listitem")).to_have_count(0)
    page.get_by_role("link", name="Home", exact=True).click()
    expect(home).to_be_visible()


def checkout(story: Literal["place", "change"], page: Page) -> str:
    dishes = (ROLLS, ROLLS, RICE) if story == "place" else (TEA, RICE)
    for dish in dishes:
        page.get_by_role("button", name=f"Add {dish} to cart", exact=True).click()
    page.get_by_role("link", name=re.compile(r"^Review cart\b", re.I)).click()
    checkpoint = ""
    if story == "change":
        cart = read_cart(page)
        grade_initial_cart(cart)
        checkpoint = "Cart showed " + ", ".join(f"{qty} × {name}" for name, qty in cart) + ". "
        page.get_by_role("button", name=f"Increase quantity of {TEA}", exact=True).click()
        page.get_by_role("button", name=f"Remove {RICE}", exact=True).click()
    page.get_by_role("button", name="Place order", exact=True).click()
    lines, total = read_confirmation(page)
    grade_checkout(story, lines, total)
    items = ", ".join(f"{line.quantity} × {line.name}" for line in lines)
    return f"{checkpoint}Confirmed {items}, total {total}."


def drive_story(story: str, page: Page) -> str:
    """Drive a fresh page already on the homepage and grade its visible outcome."""
    verify_start(page)
    if story in ("contact", "hours"):
        page.get_by_role("link", name="Hours & location", exact=True).click()
        if story == "contact":
            contact = page.get_by_role("region", name="Thai Peacock", exact=True)
            address = visible_text(contact.locator("address"))
            phone = visible_text(contact.get_by_role("link"))
            grade_contact(address, phone)
            return f"{address}, {phone}."
        hours = page.get_by_role("region", name="Posted hours", exact=True)

        def interval(day: str) -> str:
            row = hours.get_by_role("group", name=day, exact=True)
            expect(row.get_by_text(day, exact=True)).to_be_visible()
            return visible_text(row.get_by_role("definition"))

        tuesday = interval("Tuesday")
        friday = interval("Friday")
        grade_hours(tuesday, friday)
        return f"Tuesday {tuesday}, Friday {friday}."

    page.get_by_role("link", name="Menu", exact=True).click()
    if story == "soup":
        heading = page.get_by_role("heading", name=re.compile(r"\bTom-Yum Soup\b", re.I))
        dish = page.get_by_role("article").filter(has=heading)
        expect(heading).to_be_visible()
        description = visible_text(dish.get_by_role("paragraph"))
        price = visible_text(dish.locator("data"))
        grade_soup(description, price)
        return f"{description} Price {price}."
    if story == "place":
        return checkout("place", page)
    if story == "change":
        return checkout("change", page)
    raise GradeError(f"Unknown shopper story {story!r}")
