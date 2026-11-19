"""Private observations of the cart and receipt currently visible to the shopper."""

import re

from playwright.async_api import Locator, Page, expect

from .grading import GradeError, ReceiptLine


async def visible_text(locator: Locator) -> str:
    await expect(locator).to_be_visible()
    return " ".join((await locator.inner_text()).split())


async def viewport_text(locator: Locator) -> str:
    """Read a field only if it intersects the shopper's current viewport."""
    text = await visible_text(locator)
    await expect(locator).to_be_in_viewport(timeout=250)
    return text


async def read_cart(page: Page) -> list[tuple[str, int]]:
    """Read every visible cart line at the edit story's first checkpoint."""
    cart = page.get_by_role("list", name="Cart items")
    await expect(cart).to_be_visible()
    lines = []
    for row in await cart.get_by_role("listitem").all():
        name = await viewport_text(row.get_by_role("heading"))
        count = await viewport_text(row.get_by_label("Quantity", exact=True))
        try:
            lines.append((name, int(count)))
        except ValueError as error:
            raise GradeError(f"Invalid visible cart quantity {count!r} for {name}") from error
    return lines


async def read_confirmation(page: Page) -> tuple[list[ReceiptLine], str]:
    """Read the visible receipt independently of the checkout response."""
    await viewport_text(page.get_by_role("heading", name="Simulated order confirmed", exact=True))
    await viewport_text(page.get_by_role("link", name="Thai Peacock", exact=True))
    items = page.get_by_role("list", name="Confirmed items")
    await expect(items).to_be_visible()
    lines = []
    for row in await items.get_by_role("listitem").all():
        name = await viewport_text(row.get_by_role("heading"))
        unit = await viewport_text(row.get_by_text(re.compile(r"^\s*\d+\s*[×x]\s*", re.I)))
        quantity, price = re.split(r"\s*[×x]\s*", unit, maxsplit=1, flags=re.I)
        lines.append(
            ReceiptLine(
                name, int(quantity), price, await viewport_text(row.get_by_label("Line total"))
            )
        )
    return lines, await viewport_text(page.get_by_label("Total", exact=True))
