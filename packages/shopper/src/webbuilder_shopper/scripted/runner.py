"""Generate Thai Peacock and run its five shopper stories in headless Chromium."""

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import Browser, Error, async_playwright
from webbuilder_static.storefront import generate
from webbuilder_mock_backend.server import Catalog, load_catalog

from ..grading import STORE_ID, STORIES, grade_submissions
from ..serving import serve_attempt
from .browser import drive_story


async def run_story(story: str, browser: Browser, directory: Path, catalog: Catalog) -> str:
    with serve_attempt(directory, catalog) as attempt:
        async with await browser.new_context() as context:
            context.set_default_timeout(5_000)
            page = await context.new_page()
            await page.goto(attempt.url, wait_until="domcontentloaded")
            answer = await drive_story(story, page, attempt)
    # Both servers have finished handling all requests from this page.
    submissions = attempt.submissions
    grade_submissions(story, submissions)
    activity = "1 accepted order" if submissions else "0 submissions"
    return f"{answer} | {activity}"


async def run_stories(directory: Path, catalog: Catalog) -> int:
    """Exercise one build, with a fresh browser context and mock for each story."""
    passed = 0
    async with async_playwright() as playwright, await playwright.chromium.launch() as browser:
        for story, title in STORIES.items():
            try:
                result = await run_story(story, browser, directory, catalog)
            except (AssertionError, Error, OSError, ValueError) as error:
                print(f"FAIL  {title} | {error}", flush=True)
            else:
                print(f"PASS  {title} | {result}", flush=True)
                passed += 1

    print(f"{passed}/{len(STORIES)} stories passed.", flush=True)
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--feed", type=Path, default=Path("~/data/webbuilder/restaurants_feed.json")
    )
    parser.add_argument("--output", type=Path, default=Path("build/thai-peacock"))
    args = parser.parse_args()
    try:
        index = generate(args.feed, STORE_ID, args.output)
        catalog = load_catalog(args.feed)
        print(f"Generated {index.resolve()}", flush=True)
        passed = asyncio.run(run_stories(index.parent, catalog))
    except (Error, KeyError, OSError, ValueError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    if passed != len(STORIES):
        raise SystemExit(1)
