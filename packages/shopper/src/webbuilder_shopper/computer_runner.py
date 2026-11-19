"""Run five screenshot-driven shopper stories against an existing Thai Peacock build."""

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, Protocol, TypedDict
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Error, Page, Route, sync_playwright
from webbuilder_mock_backend.server import Catalog, load_catalog

from .browser import read_cart, read_confirmation
from .computer_model import (
    MODEL_SETTINGS,
    VIEWPORT,
    ModelUnavailable,
    ShopperFailure,
    ShopperSession,
)
from .grading import (
    STORE_ID,
    STORIES,
    GradeError,
    grade_checkout,
    grade_initial_cart,
    grade_lookup_answer,
    grade_submissions,
)
from .serving import Attempt, serve_attempt

ATTEMPT_LIMIT = 3
DEFAULT_STEP_LIMIT = 32
REQUESTS = {
    "contact": "What’s the full address and phone number?",
    "hours": "When does Thai Peacock open and close on Tuesday and Friday?",
    "soup": "What size is the Tom-Yum Soup, and how much does it cost?",
    "place": "Order two servings of vegan crispy spring rolls and one 16 oz rice.",
    "change": "Add one Thai Lime Tea and one 16 oz rice to the cart. Show me my cart.",
}
CHANGE_REQUEST = "Change the quantity to two teas, remove the rice, and place the order."

type History = list[dict[str, object]]
type Status = Literal["passed", "failed", "incomplete"]


class Session(Protocol):
    @property
    def steps(self) -> int: ...

    def run(self, page: Page, request: str) -> str: ...


type SessionFactory = Callable[[str, int, History], Session]


class AttemptResult(TypedDict):
    story: str
    attempt: int
    status: Status
    reason: str
    steps: int
    answers: list[str]
    action_history: str
    screenshot: str | None
    checkpoint_screenshot: str | None
    initial_cart: list[tuple[str, int]] | None
    confirmation: dict[str, object] | None
    submissions: tuple[dict[str, object] | None, ...]


class Report(TypedDict):
    status: Literal["running", "passed", "failed", "incomplete"]
    reason: str
    directory: str
    build_sha256: str
    feed: str | None
    feed_sha256: str | None
    model: str
    model_settings: dict[str, object]
    attempt_limit: int
    step_limit: int
    first_attempt_passes: int
    within_three_passes: int
    attempts: list[AttemptResult]


def new_report(directory: Path, model: str, step_limit: int, feed: Path | None = None) -> Report:
    return Report(
        status="running",
        reason="",
        directory=str(directory.resolve()),
        build_sha256="",
        feed=str(feed.resolve()) if feed else None,
        feed_sha256=None,
        model=model,
        model_settings=dict(MODEL_SETTINGS),
        attempt_limit=ATTEMPT_LIMIT,
        step_limit=step_limit,
        first_attempt_passes=0,
        within_three_passes=0,
        attempts=[],
    )


def write_json(path: Path, data: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identify_build(directory: Path) -> tuple[dict[str, str], str]:
    files = {
        path.relative_to(directory).as_posix(): file_digest(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }
    digest = hashlib.sha256()
    for name, value in files.items():
        digest.update(f"{value}  {name}\n".encode())
    return files, digest.hexdigest()


def restrict_to_storefront(route: Route, homepage: str) -> None:
    request = route.request
    url = urlsplit(request.url)
    if url.scheme == "http" and url.netloc == urlsplit(homepage).netloc:
        route.continue_()
    elif request.resource_type == "image" and url.scheme == "https":
        route.continue_()
    else:
        route.abort()


def shop_and_grade(
    session: Session,
    page: Page,
    attempt: Attempt,
    result: AttemptResult,
    catalog: Catalog,
    evidence: Path,
) -> None:
    story = result["story"]
    answer = session.run(page, REQUESTS[story])
    result["answers"].append(answer)
    if story == "change":
        cart = read_cart(page)
        result["initial_cart"] = cart
        grade_initial_cart(cart)
        attempt.check_mock()
        if attempt.submissions:
            raise GradeError("Order submitted before the cart change request.")
        checkpoint = evidence / f"change-{result['attempt']}-cart.png"
        page.screenshot(path=checkpoint, scale="css")
        result["checkpoint_screenshot"] = checkpoint.name
        answer = session.run(page, CHANGE_REQUEST)
        result["answers"].append(answer)
    if story in ("change", "place"):
        lines, total = read_confirmation(page)
        result["confirmation"] = {"items": [vars(line) for line in lines], "total": total}
        grade_checkout("change" if story == "change" else "place", lines, total)
    else:
        grade_lookup_answer(
            story, answer, menu_names=(item.name for item in catalog[STORE_ID].values())
        )


def run_attempt(
    browser: Browser,
    directory: Path,
    catalog: Catalog,
    model: str,
    step_limit: int,
    evidence: Path,
    story: str,
    number: int,
    session_factory: SessionFactory,
) -> AttemptResult:
    stem = f"{story}-{number}"
    history: History = []
    result = AttemptResult(
        story=story,
        attempt=number,
        status="incomplete",
        reason="",
        steps=0,
        answers=[],
        action_history=f"{stem}.json",
        screenshot=None,
        checkpoint_screenshot=None,
        initial_cart=None,
        confirmation=None,
        submissions=(),
    )
    screenshot: bytes | None = None
    problems: list[str] = []
    session: Session | None = None
    served: Attempt | None = None
    try:
        with serve_attempt(directory, catalog) as attempt:
            served = attempt
            with browser.new_context(viewport=VIEWPORT, service_workers="block") as context:
                context.set_default_timeout(5_000)
                context.route("**/*", lambda route: restrict_to_storefront(route, attempt.url))
                page = context.new_page()
                try:
                    # A fresh context has no cart in session storage. The shopper starts at home.
                    page.goto(attempt.url, wait_until="domcontentloaded")
                    attempt.check_mock()
                    session = session_factory(model, step_limit, history)
                    if isinstance(session, ShopperSession):
                        session.on_step = attempt.check_mock
                    try:
                        shop_and_grade(session, page, attempt, result, catalog, evidence)
                    except (GradeError, ShopperFailure, AssertionError) as error:
                        problems.append(str(error))
                finally:
                    if session is not None:
                        result["steps"] = session.steps
                        screenshot = getattr(session, "last_screenshot", None)
                    # Keep the last view until the drained mock record can be graded.
                    # A browser loss here also makes an otherwise correct attempt incomplete.
                    screenshot = page.screenshot(timeout=5_000)
        attempt.check_mock()
        try:
            grade_submissions(story, attempt.submissions)
        except GradeError as error:
            problems.append(str(error))
        result["reason"] = " ".join(problems)
        result["status"] = "failed" if problems else "passed"
    except (Error, OSError, ModelUnavailable, AssertionError, KeyboardInterrupt) as error:
        result["reason"] = str(error) or "Run interrupted."
        result["status"] = "incomplete"
    finally:
        if served is not None:
            result["submissions"] = served.submissions
        if result["status"] != "passed" and screenshot is not None:
            result["screenshot"] = f"{stem}.png"
            (evidence / f"{stem}.png").write_bytes(screenshot)
        write_json(evidence / result["action_history"], history)
    return result


def run_suite(
    browser: Browser,
    directory: Path,
    catalog: Catalog,
    model: str,
    step_limit: int,
    evidence: Path,
    session_factory: SessionFactory = ShopperSession,
    *,
    report: Report | None = None,
) -> Report:
    if report is None:
        report = new_report(directory, model, step_limit)
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
            for story, title in STORIES.items():
                for number in range(1, ATTEMPT_LIMIT + 1):
                    attempt = run_attempt(
                        browser,
                        snapshot,
                        catalog,
                        model,
                        step_limit,
                        evidence,
                        story,
                        number,
                        session_factory,
                    )
                    report["attempts"].append(attempt)
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
                        return report
                    if status == "passed":
                        report["within_three_passes"] += 1
                        report["first_attempt_passes"] += int(number == 1)
                    write_json(evidence / "report.json", report)
                    if status == "passed":
                        break
            report["status"] = (
                "passed" if report["within_three_passes"] == len(STORIES) else "failed"
            )
    except (Error, OSError, KeyboardInterrupt) as error:
        report["status"] = "incomplete"
        report["reason"] = str(error) or "Run interrupted."
    write_json(evidence / "report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site", type=Path, required=True, help="Existing generated site directory"
    )
    parser.add_argument("--feed", type=Path, required=True, help="JSON feed used for this build")
    parser.add_argument("--model", required=True, help="OpenAI computer-capable model identifier")
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
    report = new_report(directory, args.model, args.step_limit, feed)
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
        with sync_playwright() as playwright, playwright.chromium.launch() as browser:
            run_suite(
                browser, directory, catalog, args.model, args.step_limit, evidence, report=report
            )
    except (Error, OSError, KeyError, TypeError, ValueError, KeyboardInterrupt) as error:
        report["status"] = "incomplete"
        report["reason"] = str(error) or "Run interrupted."
        write_json(evidence / "report.json", report)
    total = len(STORIES)
    print(
        f"{report['status'].upper()} · first attempt {report['first_attempt_passes']}/{total}"
        f" · within three {report['within_three_passes']}/{total}",
        flush=True,
    )
    if report["reason"]:
        print(report["reason"], flush=True)
    sys.exit({"passed": 0, "failed": 1, "incomplete": 2}[report["status"]])


if __name__ == "__main__":
    main()
