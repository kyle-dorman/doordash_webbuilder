"""Exercise the retry policy against real browser contexts, carts and HTTP mock orders."""

import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright
from webbuilder_agent.storefront import generate
from webbuilder_mock_backend.server import Catalog, OrderHandler, load_catalog
from webbuilder_shopper.browser import checkout
from webbuilder_shopper.computer_model import ModelUnavailable
from webbuilder_shopper.computer_runner import CHANGE_REQUEST, REQUESTS, History, run_suite
from webbuilder_shopper.grading import RICE, ROLLS, STORE_ID, TEA


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright, playwright.chromium.launch() as chromium:
        yield chromium


@pytest.fixture
def site(tmp_path: Path) -> tuple[Path, Catalog]:
    # A tiny feed published by the real generator. No external feed or photos are needed.
    items = [
        {
            "id": item_id,
            "name": name,
            "price": {
                "unit_amount": cents,
                "currency": "USD",
                "display_string": f"${cents / 100:.2f}",
            },
        }
        for item_id, name, cents in (
            ("140247117", RICE, 250),
            ("140240246", ROLLS, 850),
            ("548484849", TEA, 450),
        )
    ]
    location = {
        "store_id": STORE_ID,
        "address": {
            "street": "219 Southwest 9th Avenue",
            "city": "Portland",
            "state": "OR",
            "zip_code": "97205",
            "country": "US",
        },
        "phone": "+15037197273",
        "timezone": "US/Pacific",
        "open_hours": [],
    }
    store = {
        "store_id": STORE_ID,
        "store_header": {"data": {"name": "Thai Peacock", "cuisine_type": "Thai"}},
        "business_profile": {"locations": [location]},
        "menu_book": {"item_lists": [{"name": "Menu", "items": items}]},
    }
    feed = tmp_path / "feed.json"
    feed.write_text(json.dumps({"restaurants": [store]}), encoding="utf-8")
    return generate(feed, STORE_ID, tmp_path / "site").parent, load_catalog(feed)


CONTACT = "219 Southwest 9th Avenue, Portland, OR 97205 · (503) 719-7273"
HOURS = "Tuesday 11:30 AM–9:15 PM. Friday 11:00 AM–9:45 PM."


type Outage = Literal["model", "browser", "mock"]


class DeterministicSession:
    def __init__(
        self,
        runs: Counter[str],
        history: History,
        outage: Outage | None = None,
    ) -> None:
        assert history == []
        self.history = history
        self.steps = 0
        self.runs = runs
        self.outage = outage

    def run(self, page: Page, request: str) -> str:
        self.steps += 1
        self.history.append({"event": "request", "text": request})
        if request == CHANGE_REQUEST:
            assert self.steps == 2 and self.history[0]["text"] == REQUESTS["change"]
            page.get_by_role("button", name=f"Increase quantity of {TEA}", exact=True).click()
            page.get_by_role("button", name=f"Remove {RICE}", exact=True).click()
            page.get_by_role("button", name="Place order", exact=True).click()
            return "Order placed."

        assert self.steps == 1
        assert urlsplit(page.url).path in {"/", "/index.html"}
        assert page.evaluate("sessionStorage.length") == 0
        # Cookies span the mock's changing localhost ports, unlike sessionStorage.
        assert "previous_attempt" not in page.evaluate("document.cookie")
        page.evaluate("document.cookie = 'previous_attempt=yes;path=/'")
        self.runs[request] += 1
        if request == REQUESTS["contact"]:
            return CONTACT
        if request == REQUESTS["hours"]:
            if self.outage == "model":
                raise ModelUnavailable("Service interrupted on the second story")
            if self.outage == "browser":
                page.close()
                return HOURS
            if self.outage == "mock":
                # Drive a real POST through the storefront and its failing HTTP mock.
                response = page.request.post(
                    urljoin(page.url, "/orders"),
                    data={"store_id": STORE_ID, "items": [{"item_id": "548484849", "quantity": 1}]},
                )
                assert response.status == 503
                return HOURS
            if self.runs[request] == 1:
                page.get_by_role("link", name="Menu", exact=True).click()
                checkout("place", page)
                page.get_by_role("link", name="Menu", exact=True).click()
                page.get_by_role("button", name=f"Add {TEA} to cart", exact=True).click()
                assert "548484849" in page.evaluate("JSON.stringify(sessionStorage)")
                self.history.append(
                    {"event": "action", "text": "Ordered rolls and rice; added tea"}
                )
            return HOURS
        if request == REQUESTS["soup"]:
            self.history.append({"event": "answer", "text": "32 oz, $14.50"})
            return "32 oz, $14.50"

        page.get_by_role("link", name="Menu", exact=True).click()
        if request == REQUESTS["place"]:
            return checkout("place", page)
        assert request == REQUESTS["change"] and request.endswith("Show me my cart.")
        page.get_by_role("button", name=f"Add {TEA} to cart", exact=True).click()
        if self.runs[request] == 2:
            page.get_by_role("button", name=f"Add {RICE} to cart", exact=True).click()
        page.get_by_role("link", name="Cart", exact=True).click()
        expect(page.get_by_role("list", name="Cart items")).to_be_visible()
        return "Here is your cart."


def test_pass_at_three_isolates_retries_and_keeps_all_failures(
    browser: Browser, site: tuple[Path, Catalog], tmp_path: Path
) -> None:
    directory, catalog = site
    counts: Counter[str] = Counter()

    def fresh(model: str, limit: int, history: History) -> DeterministicSession:
        assert (model, limit) == ("test-shopper", 32)
        return DeterministicSession(counts, history)

    evidence = tmp_path / "evidence"
    report = run_suite(browser, directory, catalog, "test-shopper", 32, evidence, fresh)
    assert report["status"] == "failed"
    assert report["first_attempt_passes"] == 2 and report["within_three_passes"] == 4
    attempts = report["attempts"]
    assert [(a["story"], a["attempt"], a["status"]) for a in attempts] == [
        ("contact", 1, "passed"),
        ("hours", 1, "failed"),
        ("hours", 2, "passed"),
        ("soup", 1, "failed"),
        ("soup", 2, "failed"),
        ("soup", 3, "failed"),
        ("place", 1, "passed"),
        ("change", 1, "failed"),
        ("change", 2, "passed"),
    ]
    assert len(attempts[1]["submissions"]) == 1
    assert attempts[2]["submissions"] == ()
    assert attempts[1]["answers"] == attempts[2]["answers"] == [HOURS]
    assert "zero" in attempts[1]["reason"].lower()
    assert [a["answers"] for a in attempts[3:6]] == [["32 oz, $14.50"]] * 3
    assert attempts[-2]["submissions"] == ()
    assert attempts[-2]["steps"] == 1
    assert attempts[-1]["steps"] == 2
    assert sorted(attempts[-1]["initial_cart"] or []) == sorted([(TEA, 1), (RICE, 1)])

    for attempt in attempts:
        history = json.loads((evidence / attempt["action_history"]).read_text())
        requests = [entry["text"] for entry in history if entry["event"] == "request"]
        expected = [REQUESTS[attempt["story"]]]
        if attempt["story"] == "change" and attempt["status"] == "passed":
            expected.append(CHANGE_REQUEST)
        assert requests == expected
        if attempt["status"] == "failed":
            assert attempt["reason"]
            screenshot = attempt["screenshot"]
            assert screenshot
            assert (evidence / screenshot).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert json.loads((evidence / "report.json").read_text()) == json.loads(json.dumps(report))


@pytest.mark.parametrize("outage", ["model", "browser", "mock"])
def test_service_loss_stops_suite_and_preserves_finished_attempt(
    outage: Outage,
    monkeypatch: pytest.MonkeyPatch,
    browser: Browser,
    site: tuple[Path, Catalog],
    tmp_path: Path,
) -> None:
    directory, catalog = site
    counts: Counter[str] = Counter()

    def fresh(model: str, limit: int, history: History) -> DeterministicSession:
        return DeterministicSession(counts, history, outage)

    if outage == "mock":

        def unavailable(handler: OrderHandler) -> None:
            handler.reply(503, {"error": "Mock unavailable"})

        monkeypatch.setattr(OrderHandler, "do_POST", unavailable)

    evidence = tmp_path / "evidence"
    report = run_suite(browser, directory, catalog, "test-shopper", 32, evidence, fresh)
    assert report["status"] == "incomplete"
    assert report["first_attempt_passes"] == report["within_three_passes"] == 1
    assert [(a["story"], a["attempt"], a["status"]) for a in report["attempts"]] == [
        ("contact", 1, "passed"),
        ("hours", 1, "incomplete"),
    ]
    assert json.loads((evidence / "report.json").read_text())["status"] == "incomplete"
