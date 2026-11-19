"""Run screenshot-driven shopper stories against an existing Thai Peacock build."""

import argparse
import asyncio
import json
import shutil
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from playwright.async_api import Browser, Error, Page, Route, async_playwright
from webbuilder_mock_backend.server import Catalog, load_catalog

from ..grading import (
    STORE_ID,
    STORIES,
    GradeError,
    grade_checkout,
    grade_initial_cart,
    grade_submissions,
)
from ..serving import Attempt, serve_attempt
from ..viewport import read_cart, read_confirmation
from .answers import grade_lookup_answer
from .browser import VIEWPORT, ShopperFailure
from .report import (
    AttemptRecorder,
    AttemptResult,
    Report,
    file_digest,
    identify_build,
    new_report,
    record_attempt,
    write_json,
)
from .shopper import ModelUnavailable, SdkShopperSession
from .usage import TERRA

DEFAULT_STEP_LIMIT = 32
REQUESTS = {
    "contact": "What’s the full address and phone number?",
    "hours": "When does Thai Peacock open and close on Tuesday and Friday?",
    "soup": "What size is the Tom-Yum Soup, and how much does it cost?",
    "place": "Order two servings of vegan crispy spring rolls and one 16 oz rice.",
    "change": "Add one Thai Lime Tea and one 16 oz rice to the cart. Show me my cart.",
}
CHANGE_REQUEST = "Change the quantity to two teas, remove the rice, and place the order."


async def restrict_to_storefront(route: Route, *, homepage: str) -> None:
    request = route.request
    url = urlsplit(request.url)
    if url.scheme == "http" and url.netloc == urlsplit(homepage).netloc:
        await route.continue_()
    elif request.resource_type == "image" and url.scheme == "https":
        await route.continue_()
    else:
        await route.abort()


async def shop_and_grade(
    shopper: SdkShopperSession,
    page: Page,
    attempt: Attempt,
    recorder: AttemptRecorder,
    catalog: Catalog,
) -> None:
    result = recorder.result
    story = result["story"]
    answer = await shopper.run(REQUESTS[story])
    result["answers"].append(answer)
    if story == "change":
        cart = await read_cart(page)
        result["initial_cart"] = cart
        cart_png = await page.screenshot(scale="css")
        attempt.check_mock()
        submission_count = attempt.checkpoint_submission_count
        result["checkpoint_submission_count"] = submission_count
        grade_initial_cart(cart, submission_count)
        recorder.save_checkpoint(cart_png)
        result["answers"].append(await shopper.run(CHANGE_REQUEST))

    if story in ("change", "place"):
        lines, total = await read_confirmation(page)
        result["confirmation"] = {"items": [asdict(line) for line in lines], "total": total}
        grade_checkout(story, lines, total)
    else:
        grade_lookup_answer(
            story, answer, menu_names=(item.name for item in catalog[STORE_ID].values())
        )


async def visit_storefront(
    browser: Browser, attempt: Attempt, catalog: Catalog, recorder: AttemptRecorder, step_limit: int
) -> None:
    """Keep one page for the entire story and capture its last view before closing."""
    async with await browser.new_context(viewport=VIEWPORT, service_workers="block") as context:
        context.set_default_timeout(5_000)
        await context.route("**/*", partial(restrict_to_storefront, homepage=attempt.url))
        page = await context.new_page()
        shopper = SdkShopperSession(
            page,
            recorder.model,
            step_limit,
            recorder.history,
            on_step=attempt.check_mock,
            save_observation=recorder.save_observation,
        )
        try:
            await page.goto(attempt.url, wait_until="domcontentloaded")
            await shop_and_grade(shopper, page, attempt, recorder, catalog)
        finally:
            recorder.result["steps"] = shopper.steps
            recorder.save_final_view(await page.screenshot(scale="css"))


async def run_attempt(
    browser: Browser, directory: Path, catalog: Catalog, recorder: AttemptRecorder, step_limit: int
) -> AttemptResult:
    result = recorder.result
    problems: list[str] = []
    attempt: Attempt | None = None
    with recorder.trace:
        try:
            if recorder.trace.export() is None:
                raise ModelUnavailable("Enable Agents SDK tracing to record the shopper attempt")
            result["trace_id"] = recorder.trace.trace_id
            with serve_attempt(directory, catalog) as attempt:
                try:
                    await visit_storefront(browser, attempt, catalog, recorder, step_limit)
                except (GradeError, ShopperFailure, AssertionError) as error:
                    problems.append(str(error))
            # serve_attempt has now drained the site's pending checkouts.
            try:
                grade_submissions(result["story"], attempt.submissions)
            except GradeError as error:
                problems.append(str(error))
            result["reason"] = " ".join(problems)
            result["status"] = "failed" if problems else "passed"
        except (
            Error,
            OSError,
            ModelUnavailable,
            asyncio.CancelledError,
            KeyboardInterrupt,
        ) as error:
            result["reason"] = str(error) or "Run interrupted."
        finally:
            if attempt is not None:
                result["submissions"] = attempt.submissions
            recorder.finish()
    return result


async def run_suite(browser: Browser, catalog: Catalog, evidence: Path, report: Report) -> None:
    directory = Path(report["directory"])
    report["versions"]["chromium"] = browser.version
    evidence.mkdir(parents=True, exist_ok=True)
    try:
        if not (directory / "index.html").is_file():
            raise FileNotFoundError(f"No storefront index.html in {directory}")
        with TemporaryDirectory(prefix="computer-shopper-") as scratch:
            snapshot = Path(scratch) / "site"
            shutil.copytree(directory, snapshot)
            manifest, report["build_sha256"] = identify_build(snapshot)
            write_json(evidence / "build-files.json", manifest)
            write_json(evidence / "report.json", report)
            for story in report["stories"]:
                title = STORIES[story]
                for number in range(1, report["attempt_limit"] + 1):
                    recorder = AttemptRecorder(evidence, story, number, report["model"])
                    attempt = await run_attempt(
                        browser, snapshot, catalog, recorder, report["step_limit"]
                    )
                    record_attempt(report, attempt)
                    status = attempt["status"]
                    print(
                        f"{status.upper():10} {title} · attempt {number} · {attempt['steps']} steps"
                        f"  {attempt['reason']}",
                        flush=True,
                    )
                    if status == "incomplete":
                        report["status"] = "incomplete"
                        report["reason"] = f"{title}, attempt {number}: {attempt['reason']}"
                        write_json(evidence / "report.json", report)
                        return
                    write_json(evidence / "report.json", report)
                    if status == "passed":
                        break
            report["status"] = (
                "passed" if report["within_three_passes"] == len(report["stories"]) else "failed"
            )
    except (Error, OSError, asyncio.CancelledError, KeyboardInterrupt) as error:
        report["status"] = "incomplete"
        report["reason"] = str(error) or "Run interrupted."
    write_json(evidence / "report.json", report)


async def evaluate(catalog: Catalog, evidence: Path, report: Report) -> None:
    async with async_playwright() as playwright, await playwright.chromium.launch() as browser:
        await run_suite(browser, catalog, evidence, report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site", type=Path, required=True, help="Existing generated site directory"
    )
    parser.add_argument("--feed", type=Path, required=True, help="JSON feed used for this build")
    parser.add_argument(
        "--model", default=TERRA, help="OpenAI computer-capable model (default: %(default)s)"
    )
    parser.add_argument(
        "--story", choices=tuple(STORIES), help="Run just this story (default: all)"
    )
    parser.add_argument("--step-limit", type=int, default=DEFAULT_STEP_LIMIT)
    parser.add_argument("--evidence", type=Path, help="New or empty run directory")
    args = parser.parse_args()
    if args.step_limit < 1:
        parser.error("--step-limit must be positive")
    directory, feed = args.site.expanduser().resolve(), args.feed.expanduser().resolve()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    evidence = (args.evidence or Path("logs/computer-shopper") / stamp).expanduser().resolve()
    if evidence.is_relative_to(directory):
        parser.error("--evidence must be outside the site directory")
    if evidence.exists() and (not evidence.is_dir() or any(evidence.iterdir())):
        parser.error(f"Choose a new or empty evidence directory: {evidence}")
    evidence.mkdir(parents=True, exist_ok=True)
    report = new_report(directory, args.model, args.step_limit, feed, story=args.story)
    try:
        # Claim the directory before starting services, even for simultaneous invocations.
        with (evidence / "report.json").open("x", encoding="utf-8") as initial:
            json.dump(report, initial, ensure_ascii=False, indent=2)
            initial.write("\n")
    except FileExistsError:
        parser.error(f"Evidence directory is already in use: {evidence}")
    print(f"Evidence: {evidence}", flush=True)
    try:
        report["feed_sha256"] = file_digest(feed)
        catalog = load_catalog(feed)
        if STORE_ID not in catalog:
            raise ValueError(f"Source feed has no Thai Peacock store {STORE_ID}.")
        asyncio.run(evaluate(catalog, evidence, report))
    except (Error, OSError, KeyError, TypeError, ValueError, KeyboardInterrupt) as error:
        report["status"] = "incomplete"
        report["reason"] = str(error) or "Run interrupted."
        write_json(evidence / "report.json", report)
    total = len(report["stories"])
    print(
        f"{report['status'].upper()} · first attempt {report['first_attempt_passes']}/{total}"
        f" · within three {report['within_three_passes']}/{total}",
        flush=True,
    )
    spend = report["estimated_total_cost_usd"]
    per_pass = report["estimated_cost_per_passing_story_usd"]
    if spend is not None:
        print(f"Estimated spend across all attempts: ${spend:.6f}", flush=True)
    if per_pass is not None:
        print(f"Estimated cost per passing story: ${per_pass:.6f}", flush=True)
    if report["reason"]:
        print(report["reason"], flush=True)
    sys.exit({"passed": 0, "failed": 1, "incomplete": 2}[report["status"]])


if __name__ == "__main__":
    main()
