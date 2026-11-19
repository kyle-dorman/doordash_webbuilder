"""Record SDK attempts, their private grades and cumulative suite results."""

import hashlib
import json
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from typing import Literal, TypedDict

from agents import custom_span, trace

from ..grading import STORIES
from .shopper import MODEL_SETTINGS
from .usage import UsageSummary, summarize_usage

ATTEMPT_LIMIT = 3
type Status = Literal["passed", "failed", "incomplete"]


class AttemptResult(TypedDict):
    story: str
    attempt: int
    status: Status
    reason: str
    steps: int
    answers: list[str]
    action_history: str
    trace_id: str | None
    usage: UsageSummary
    screenshot: str | None
    checkpoint_screenshot: str | None
    checkpoint_submission_count: int | None
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
    runner: str
    versions: dict[str, str]
    stories: list[str]
    model_settings: dict[str, object]
    attempt_limit: int
    step_limit: int
    first_attempt_passes: int
    within_three_passes: int
    reported_total_tokens: int
    estimated_total_cost_usd: float | None
    estimated_cost_per_passing_story_usd: float | None
    attempts: list[AttemptResult]


def new_report(
    directory: Path,
    model: str,
    step_limit: int,
    feed: Path | None = None,
    *,
    story: str | None = None,
) -> Report:
    packages = ["webbuilder-shopper", "openai-agents", "openai", "playwright"]
    return Report(
        status="running",
        reason="",
        directory=str(directory.resolve()),
        build_sha256="",
        feed=str(feed.resolve()) if feed else None,
        feed_sha256=None,
        model=model,
        runner="sdk",
        versions={name: version(name) for name in packages},
        stories=[story] if story else list(STORIES),
        model_settings=dict(MODEL_SETTINGS),
        attempt_limit=ATTEMPT_LIMIT,
        step_limit=step_limit,
        first_attempt_passes=0,
        within_three_passes=0,
        reported_total_tokens=0,
        estimated_total_cost_usd=None,
        estimated_cost_per_passing_story_usd=None,
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


def record_attempt(report: Report, attempt: AttemptResult) -> None:
    report["attempts"].append(attempt)
    report["reported_total_tokens"] += attempt["usage"]["total_tokens"]
    if attempt["status"] == "passed":
        report["within_three_passes"] += 1
        report["first_attempt_passes"] += int(attempt["attempt"] == 1)
    # Include retries and failures. An unpriced attempt makes the total unknown.
    costs = [entry["usage"]["estimated_cost_usd"] for entry in report["attempts"]]
    total = sum(Decimal(str(cost)) for cost in costs if cost is not None)
    complete = None not in costs
    passes = report["within_three_passes"]
    report["estimated_total_cost_usd"] = float(total) if complete else None
    report["estimated_cost_per_passing_story_usd"] = (
        float(total / passes) if complete and passes else None
    )


class AttemptRecorder:
    """Keep the shopper's frames, turn history and private grade under one trace."""

    def __init__(self, evidence: Path, story: str, number: int, model: str) -> None:
        self.evidence = evidence
        self.stem = f"{story}-{number}"
        self.model = model
        self.history: list[dict[str, object]] = []
        self.trace = trace("Thai Peacock shopper", metadata={"model": model, "story": story})
        self.result = AttemptResult(
            story=story,
            attempt=number,
            status="incomplete",
            reason="",
            steps=0,
            answers=[],
            action_history=f"{self.stem}.json",
            trace_id=None,
            usage=summarize_usage([], model, 0),
            screenshot=None,
            checkpoint_screenshot=None,
            checkpoint_submission_count=None,
            initial_cart=None,
            confirmation=None,
            submissions=(),
        )

    def save_observation(self, png: bytes) -> str:
        """Keep the exact frame supplied to the model, sharing identical frames."""
        path = Path(f"{self.stem}-frames") / f"{hashlib.sha256(png).hexdigest()}.png"
        target = self.evidence / path
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            target.write_bytes(png)
        # If the browser is lost, this is the last view we can provide.
        self.result["screenshot"] = path.as_posix()
        return path.as_posix()

    def save_checkpoint(self, png: bytes) -> None:
        path = self.evidence / f"{self.stem}-cart.png"
        path.write_bytes(png)
        self.result["checkpoint_screenshot"] = path.name

    def save_final_view(self, png: bytes) -> None:
        path = self.evidence / f"{self.stem}.png"
        path.write_bytes(png)
        self.result["screenshot"] = path.name

    def finish(self) -> None:
        result = self.result
        result["usage"] = summarize_usage(self.history, self.model, result["steps"])
        write_json(self.evidence / result["action_history"], self.history)
        with custom_span(
            "Private shopper grade",
            data={
                "story": result["story"],
                "attempt": result["attempt"],
                "status": result["status"],
                "turns": result["steps"],
                "usage": result["usage"],
                "report": "report.json",
                "history": result["action_history"],
                "checkpoint": result["checkpoint_screenshot"],
                "final_view": result["screenshot"],
            },
        ):
            pass
