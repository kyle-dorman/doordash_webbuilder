"""Playwright actions for the five scripted Thai Peacock stories."""

import re
from typing import Literal

from playwright.async_api import Page, expect

from ..grading import (
    RICE,
    ROLLS,
    TEA,
    GradeError,
    grade_checkout,
    grade_contact,
    grade_hours,
    grade_initial_cart,
    grade_soup,
)
from ..serving import Attempt
from ..viewport import read_cart, read_confirmation, visible_text


async def verify_start(page: Page) -> None:
    """Check the fresh session through the cart link, then start shopping from Home."""
    home = page.get_by_role("heading", name="Thai Peacock", exact=True)
    await expect(home).to_be_visible()
    await page.get_by_role("link", name="Cart", exact=True).click()
    review = page.get_by_role("group", name="Order review", exact=True)
    await expect(review).to_be_visible()
    items = review.get_by_role("list", name="Cart items")
    await expect(items).to_be_attached()
    await expect(items.get_by_role("listitem")).to_have_count(0)
    await page.get_by_role("link", name="Home", exact=True).click()
    await expect(home).to_be_visible()


async def checkout(story: Literal["place", "change"], page: Page, attempt: Attempt) -> str:
    dishes = (ROLLS, ROLLS, RICE) if story == "place" else (TEA, RICE)
    for dish in dishes:
        await page.get_by_role("button", name=f"Add {dish} to cart", exact=True).click()
    await page.get_by_role("link", name=re.compile(r"^Review cart\b", re.I)).click()
    checkpoint = ""
    if story == "change":
        cart = await read_cart(page)
        attempt.check_mock()
        grade_initial_cart(cart, attempt.checkpoint_submission_count)
        initial_items = ", ".join(f"{qty} × {name}" for name, qty in cart)
        checkpoint = f"Cart showed {initial_items} with 0 submissions. "
        await page.get_by_role("button", name=f"Increase quantity of {TEA}", exact=True).click()
        await page.get_by_role("button", name=f"Remove {RICE}", exact=True).click()
    await page.get_by_role("button", name="Place order", exact=True).click()
    lines, total = await read_confirmation(page)
    grade_checkout(story, lines, total)
    items = ", ".join(f"{line.quantity} × {line.name}" for line in lines)
    return f"{checkpoint}Confirmed {items}, total {total}."


async def drive_story(story: str, page: Page, attempt: Attempt) -> str:
    """Drive a fresh page already on the homepage and grade its visible outcome."""
    await verify_start(page)
    if story in ("contact", "hours"):
        await page.get_by_role("link", name="Hours & location", exact=True).click()
        if story == "contact":
            contact = page.get_by_role("region", name="Thai Peacock", exact=True)
            address = await visible_text(contact.locator("address"))
            phone = await visible_text(contact.get_by_role("link"))
            grade_contact(address, phone)
            return f"{address}, {phone}."
        hours = page.get_by_role("region", name="Posted hours", exact=True)

        async def interval(day: str) -> str:
            row = hours.get_by_role("group", name=day, exact=True)
            await expect(row.get_by_text(day, exact=True)).to_be_visible()
            return await visible_text(row.get_by_role("definition"))

        tuesday = await interval("Tuesday")
        friday = await interval("Friday")
        grade_hours(tuesday, friday)
        return f"Tuesday {tuesday}, Friday {friday}."

    await page.get_by_role("link", name="Menu", exact=True).click()
    if story == "soup":
        heading = page.get_by_role("heading", name=re.compile(r"\bTom-Yum Soup\b", re.I))
        dish = page.get_by_role("article").filter(has=heading)
        await expect(heading).to_be_visible()
        description = await visible_text(dish.get_by_role("paragraph"))
        price = await visible_text(dish.locator("data"))
        grade_soup(description, price)
        return f"{description} Price {price}."
    if story == "place":
        return await checkout("place", page, attempt)
    if story == "change":
        return await checkout("change", page, attempt)
    raise GradeError(f"Unknown shopper story {story!r}")
