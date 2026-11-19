from collections.abc import AsyncIterator

import pytest
from playwright.async_api import Page, async_playwright
from webbuilder_shopper.grading import RICE, TEA, ReceiptLine
from webbuilder_shopper.viewport import read_cart, read_confirmation

pytestmark = pytest.mark.anyio


@pytest.fixture
async def page() -> AsyncIterator[Page]:
    async with async_playwright() as playwright, await playwright.chromium.launch() as browser:
        yield await browser.new_page(viewport={"width": 800, "height": 600})


@pytest.mark.parametrize("offscreen", ["cart", "rice", "quantity"])
async def test_cart_requires_both_items_and_quantities_in_view(page: Page, offscreen: str) -> None:
    await page.set_content(f"""
        <ul id="cart" aria-label="Cart items">
          <li><h2>{TEA}</h2><output aria-label="Quantity">1</output></li>
          <li><h2 id="rice">{RICE}</h2><output aria-label="Quantity" id="quantity">1</output></li>
        </ul>
    """)
    assert await read_cart(page) == [(TEA, 1), (RICE, 1)]
    await page.add_style_tag(content=f"#{offscreen} {{ position: absolute; top: 120vh }}")
    with pytest.raises(AssertionError, match="viewport"):
        await read_cart(page)
    assert await page.evaluate("window.scrollY") == 0


@pytest.mark.parametrize(
    "offscreen", ["receipt", "heading", "store", "name", "unit", "line", "total"]
)
async def test_receipt_requires_confirmation_details_in_view(page: Page, offscreen: str) -> None:
    await page.set_content(f"""
        <div id="receipt">
          <a id="store" href="/">Thai Peacock</a><h1 id="heading">Simulated order confirmed</h1>
          <ul aria-label="Confirmed items"><li>
            <h2 id="name">{TEA}</h2><span id="unit">2 × $4.50</span>
            <output id="line" aria-label="Line total">$9.00</output>
          </li></ul>
          <output id="total" aria-label="Total">$9.00</output>
        </div>
    """)
    assert await read_confirmation(page) == ([ReceiptLine(TEA, 2, "$4.50", "$9.00")], "$9.00")
    await page.add_style_tag(content=f"#{offscreen} {{ position: absolute; top: 120vh }}")
    with pytest.raises(AssertionError, match="viewport"):
        await read_confirmation(page)
    assert await page.evaluate("window.scrollY") == 0
