from collections.abc import Iterator

import pytest
from playwright.sync_api import Page, sync_playwright
from webbuilder_shopper.browser import read_cart, read_confirmation
from webbuilder_shopper.grading import RICE, TEA, ReceiptLine


@pytest.fixture(scope="module")
def page() -> Iterator[Page]:
    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        yield browser.new_page(viewport={"width": 800, "height": 600})


@pytest.mark.parametrize("offscreen", ["cart", "rice", "quantity"])
def test_cart_requires_both_items_and_quantities_in_view(page: Page, offscreen: str) -> None:
    page.set_content(f"""
        <ul id="cart" aria-label="Cart items">
          <li><h2>{TEA}</h2><output aria-label="Quantity">1</output></li>
          <li><h2 id="rice">{RICE}</h2><output aria-label="Quantity" id="quantity">1</output></li>
        </ul>
    """)
    assert read_cart(page) == [(TEA, 1), (RICE, 1)]
    page.add_style_tag(content=f"#{offscreen} {{ position: absolute; top: 120vh }}")
    with pytest.raises(AssertionError, match="viewport"):
        read_cart(page)
    assert page.evaluate("window.scrollY") == 0


@pytest.mark.parametrize(
    "offscreen", ["receipt", "heading", "store", "name", "unit", "line", "total"]
)
def test_receipt_requires_confirmation_details_in_view(page: Page, offscreen: str) -> None:
    page.set_content(f"""
        <div id="receipt">
          <a id="store" href="/">Thai Peacock</a><h1 id="heading">Simulated order confirmed</h1>
          <ul aria-label="Confirmed items"><li>
            <h2 id="name">{TEA}</h2><span id="unit">2 × $4.50</span>
            <output id="line" aria-label="Line total">$9.00</output>
          </li></ul>
          <output id="total" aria-label="Total">$9.00</output>
        </div>
    """)
    assert read_confirmation(page) == ([ReceiptLine(TEA, 2, "$4.50", "$9.00")], "$9.00")
    page.add_style_tag(content=f"#{offscreen} {{ position: absolute; top: 120vh }}")
    with pytest.raises(AssertionError, match="viewport"):
        read_confirmation(page)
    assert page.evaluate("window.scrollY") == 0
