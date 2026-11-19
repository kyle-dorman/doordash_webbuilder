"""Generate Thai Peacock and run its five shopper stories in headless Chromium."""

import argparse
from pathlib import Path

from playwright.sync_api import Browser, Error, sync_playwright
from webbuilder_agent.storefront import generate
from webbuilder_mock_backend.server import Catalog, load_catalog

from .browser import drive_story
from .grading import STORE_ID, STORIES, grade_submissions
from .serving import serve_attempt


def run_stories(browser: Browser, directory: Path, catalog: Catalog) -> int:
    """Exercise the same build five times, with a fresh browser context and mock each time."""
    passed = 0
    for story, title in STORIES.items():
        try:
            with serve_attempt(directory, catalog) as attempt, browser.new_context() as context:
                context.set_default_timeout(5_000)
                page = context.new_page()
                page.goto(attempt.url, wait_until="domcontentloaded")
                answer = drive_story(story, page)
            submissions = attempt.submissions
            grade_submissions(story, submissions)
        except (AssertionError, Error, OSError, ValueError) as error:
            print(f"FAIL  {title} | {error}", flush=True)
        else:
            activity = "1 accepted order" if submissions else "0 submissions"
            print(f"PASS  {title} | {answer} | {activity}", flush=True)
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
        with sync_playwright() as playwright, playwright.chromium.launch() as browser:
            passed = run_stories(browser, index.parent, catalog)
    except (Error, KeyError, OSError, ValueError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    if passed != len(STORIES):
        raise SystemExit(1)
