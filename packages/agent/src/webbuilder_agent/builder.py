"""Give an Inspect ReAct agent one restaurant and publish the draft it submits."""

import argparse
import base64
import hashlib
import json
import re
import secrets
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from typing import Final

from inspect_ai import Task, eval
from inspect_ai.agent import AgentSubmit, react
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser, ContentImage, ContentText, GenerateConfig, Model
from inspect_ai.solver import Generate, Solver, TaskState, chain, solver
from inspect_ai.tool import ToolDef, ToolError, ToolResult
from jinja2 import TemplateError
from webbuilder_shared.feed import Store, load_store
from webbuilder_shared.paths import RUNS, store_directory_name

from .menu import check_full_menu
from .render import PAGE_NAME, mood_assignment, render, screenshot, storefront_assignment

DEFAULT_MODEL = "openai/gpt-6.1-terra"
REASONING_EFFORT: Final = "high"
DEFAULT_MESSAGE_LIMIT = 100


@dataclass(frozen=True)
class Swatch:
    name: str
    hex: str


@dataclass(frozen=True)
class Preview:
    preview_id: str
    site: Path
    homepage: bytes
    page: str
    image_path: str
    revision: int
    click: str | None


@dataclass
class Workspace:
    store: Store
    working: Path
    evidence: Path
    report: dict[str, object]
    mood_board: dict[str, object] | None = None
    sources: dict[str, str] = field(default_factory=dict)
    revision: int = 0
    previews: list[Preview] = field(default_factory=list)
    submitted: Preview | None = None
    assessment: str = ""
    design_direction: str = ""

    def save_report(self) -> None:
        self.report["mood_board"] = self.mood_board
        temp = self.evidence / "run.json.tmp"
        temp.write_text(json.dumps(self.report, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.evidence / "run.json")

    def save_sources(self, name: str) -> None:
        directory = self.evidence / name
        directory.mkdir()
        for filename, source in self.sources.items():
            (directory / filename).write_text(source, encoding="utf-8")


def build_task(workspace: Workspace, message_limit: int) -> Task:
    async def mood_board(
        title: str,
        scene: str,
        feed_cues: list[str],
        palette: list[Swatch],
        materials: str,
        lettering: str,
    ) -> str:
        """Deliver the creative mood board for this restaurant.

        Args:
            title: A short name for the physical reference at the heart of the board.
            scene: How a person encounters that reference and which marks make it recognizable.
            feed_cues: Specific details from the restaurant feed that inspired the scene.
            palette: Named color swatches with six-digit hex values, dominant color first.
            materials: Tactile surfaces, textures, or patterns.
            lettering: The character and rhythm of the imagined letterforms.
        """
        if workspace.mood_board is not None:
            raise ToolError("The mood board has already been recorded.")
        if not all(s.strip() for s in (title, scene, materials, lettering)):
            raise ToolError("Give the board a title, scene, materials and lettering.")
        if not feed_cues or not all(cue.strip() for cue in feed_cues):
            raise ToolError("Include concrete feed cues for the mood board.")
        if not palette or any(
            not swatch.name.strip() or not re.fullmatch(r"#[0-9A-Fa-f]{6}", swatch.hex)
            for swatch in palette
        ):
            raise ToolError("Use a name and a six-digit #RRGGBB hex value for each palette swatch.")
        board: dict[str, object] = {
            "title": title,
            "scene": scene,
            "feed_cues": feed_cues,
            "palette": [asdict(swatch) for swatch in palette],
            "materials": materials,
            "lettering": lettering,
        }
        (workspace.evidence / "mood-board.json").write_text(
            json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        workspace.mood_board = board
        workspace.save_report()
        return "Mood board recorded."

    @solver
    def assign_storefront() -> Solver:
        async def solve(state: TaskState, generate: Generate) -> TaskState:
            if workspace.mood_board is None:
                raise IncompleteBuild("The mood board was not completed.")
            state.messages.append(
                ChatMessageUser(content=storefront_assignment(workspace.mood_board))
            )
            return state

        return solve

    async def design_direction(concept: str) -> str:
        """Record a short creative brief for this restaurant before editing the site.

        Args:
            concept: Describe how the layout and browsing interaction translate your mood board
                into the experience of ordering this restaurant's food.
        """
        if workspace.sources or not concept.strip():
            raise ToolError("Record a design direction before writing the first file.")
        workspace.design_direction = concept.strip()
        return "Design direction saved. You can now edit the storefront."

    async def edit(filename: str, content: str, old_text: str | None = None) -> str:
        """Write a page template, stylesheet or storefront script, or revise a passage in it.

        Args:
            filename: style.css, storefront.js or a lowercase page filename such as index.html.
            content: Complete new file, or replacement text when old_text is supplied.
            old_text: Optional unique exact passage to replace in the existing file.
        """
        if workspace.submitted:
            raise ToolError("The build has already been submitted.")
        if not workspace.design_direction:
            raise ToolError("Call design_direction with your concept for this restaurant first.")
        if filename not in {"style.css", "storefront.js"} and not PAGE_NAME.fullmatch(filename):
            raise ToolError(
                "Use style.css, storefront.js or a lowercase page name such as menu.html."
            )
        if old_text is not None:
            original = workspace.sources.get(filename, "")
            if not old_text or original.count(old_text) != 1:
                raise ToolError("The text to replace must occur exactly once in the file.")
            content = original.replace(old_text, content, 1)
        if content != workspace.sources.get(filename):
            workspace.sources[filename] = content
            workspace.revision += 1
        return f"Saved {filename} (revision {workspace.revision})."

    async def preview(page: str = "index.html", click: str | None = None) -> ToolResult:
        """Render the current templates and see a 1280 by 900 browser screenshot.

        Args:
            page: Filename, optionally with an anchor (for example, index.html#menu).
            click: Optional CSS selector for one visible control to activate before capture.
        """
        if workspace.submitted:
            raise ToolError("The build has already been submitted.")
        filename = page.partition("#")[0]
        if not PAGE_NAME.fullmatch(filename) or filename not in workspace.sources:
            raise ToolError("Choose an existing page by its filename, for example index.html.")

        site = Path(mkdtemp(prefix="preview-", dir=workspace.working))
        try:
            render(workspace.store, workspace.sources, site)
        except (TemplateError, ValueError, TypeError, LookupError, ArithmeticError) as error:
            raise ToolError(str(error)) from error
        if not (site / filename).is_file():
            raise ToolError(f"{filename} is a template fragment. Preview a rendered page instead.")
        try:
            image = await screenshot(site, page, click)
            # Keep a comparable homepage image even when the agent explores a different view.
            homepage = image
            if page != "index.html" or click is not None:
                homepage = await screenshot(site, "index.html")
        except ValueError as error:
            raise ToolError(str(error)) from error

        number = len(workspace.previews) + 1
        snapshot = Preview(
            preview_id=secrets.token_hex(8),
            site=site,
            homepage=homepage,
            page=page,
            image_path=f"previews/{number:02d}-{filename.removesuffix('.html')}.png",
            revision=workspace.revision,
            click=click,
        )
        destination = workspace.evidence / snapshot.image_path
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(image)
        if number == 1:
            shutil.copytree(site, workspace.evidence / "first")
            (workspace.evidence / "first.png").write_bytes(homepage)
            workspace.save_sources("first-source")
        workspace.previews.append(snapshot)
        return [
            ContentText(
                text=f"Preview ID: {snapshot.preview_id}\n{page}, revision {snapshot.revision}."
            ),
            ContentImage(image="data:image/png;base64," + base64.b64encode(image).decode("ascii")),
        ]

    async def submit(preview_id: str, assessment: str) -> str:
        """Publish the current previewed build and explain your visual decisions.

        Args:
            preview_id: Exact ID returned with the latest screenshot of this draft.
            assessment: What you observed and changed after preview, or why you kept it.
        """
        latest = workspace.previews[-1] if workspace.previews else None
        if not latest or latest.preview_id != preview_id or latest.revision != workspace.revision:
            raise ToolError("Preview the current draft and submit the ID returned with its image.")
        if not workspace.sources.get("storefront.js", "").strip():
            raise ToolError(
                "Implement your restaurant-specific browsing interaction in storefront.js."
            )
        if not any(
            preview.click and preview.revision == latest.revision for preview in workspace.previews
        ):
            raise ToolError("Preview the custom interaction using click on the current draft.")
        try:
            check_full_menu(workspace.store, latest.site)
        except ValueError as error:
            raise ToolError(str(error)) from error
        workspace.submitted = latest
        workspace.assessment = assessment
        return "Submitted " + preview_id

    return Task(
        name="build_storefront",
        dataset=[Sample(id=workspace.store.store_id, input=mood_assignment(workspace.store))],
        solver=chain(
            react(prompt=None, submit=AgentSubmit(tool=ToolDef(mood_board), keep_in_messages=True)),
            assign_storefront(),
            react(
                tools=[ToolDef(design_direction), ToolDef(edit), ToolDef(preview, max_output=0)],
                submit=AgentSubmit(tool=ToolDef(submit), keep_in_messages=True),
            ),
        ),
        config=GenerateConfig(parallel_tool_calls=False, reasoning_effort=REASONING_EFFORT),
        message_limit=message_limit,
    )


def _prepare_directories(
    store_id: str, output: Path | None, evidence: Path | None
) -> tuple[Path, Path]:
    """Choose separate, empty destinations for the submitted site and its build record."""
    if output is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        run = RUNS / "agent" / stamp / store_directory_name(store_id)
        output = run / "submitted"
        evidence = evidence or run / "agent"
    output = output.expanduser().resolve()
    evidence = (evidence or output.with_name(output.name + "-evidence")).expanduser().resolve()
    if output.is_relative_to(evidence) or evidence.is_relative_to(output):
        raise ValueError("Choose separate directories for the published site and its evidence.")
    for directory in (output, evidence):
        if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
            raise ValueError(
                f"Choose an empty destination to preserve the previous run: {directory}"
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    return output, evidence


class IncompleteBuild(RuntimeError):
    """Inspect stopped before the agent submitted a successfully previewed build."""


def generate(
    feed: Path,
    store_id: str,
    output: Path | None = None,
    *,
    evidence: Path | None = None,
    model: str | Model = DEFAULT_MODEL,
    message_limit: int = DEFAULT_MESSAGE_LIMIT,
) -> Path:
    """Run one assignment and publish the exact submitted preview at output."""
    if message_limit < 1:
        raise ValueError("The message limit must be positive.")
    store = load_store(feed, store_id)
    output, evidence = _prepare_directories(store_id, output, evidence)
    report: dict[str, object] = {
        "store_id": store_id,
        "restaurant": store.name,
        "feed_sha256": hashlib.sha256(feed.expanduser().read_bytes()).hexdigest(),
        "model": model if isinstance(model, str) else str(model.name),
        "reasoning_effort": REASONING_EFFORT,
        "message_limit": message_limit,
        "status": "incomplete",
    }
    # Claim the evidence directory before starting a paid evaluation. An interrupted
    # run keeps its initial status and another writer cannot use the same directory.
    report_path = evidence / "run.json"
    with report_path.open("x", encoding="utf-8") as initial:
        initial.write(json.dumps(report, indent=2) + "\n")
    with TemporaryDirectory(prefix=".storefront-", dir=output.parent) as working:
        workspace = Workspace(store, Path(working), evidence, report)
        try:
            (log,) = eval(
                build_task(workspace, message_limit),
                model=model,
                display="none",
                log_dir=str(evidence / "logs"),
                log_images=True,
                log_model_api=False,
                log_header_only=False,
                score=False,
            )
            report["inspect_log"] = str(Path(log.location).relative_to(evidence))
            sample = log.samples[0] if log.samples else None
            if sample and sample.limit:
                report["limit"] = sample.limit.model_dump()
            selected = workspace.submitted
            if log.status != "success" or selected is None:
                error = log.error or (sample.error if sample else None)
                raise IncompleteBuild(error.message if error else "No preview was submitted.")
            workspace.save_sources("submitted-source")
            (evidence / "final.png").write_bytes(selected.homepage)
            report.update(
                submitted_preview=selected.image_path,
                submitted_revision=selected.revision,
                assessment=workspace.assessment,
            )
            selected.site.replace(output)
            report["status"] = "submitted"
        except Exception as error:
            report["error"] = str(error)
            raise
        finally:
            report["design_direction"] = workspace.design_direction
            report["previews"] = [
                {"revision": p.revision, "page": p.page, "click": p.click, "image": p.image_path}
                for p in workspace.previews
            ]
            workspace.save_report()
    return output / "index.html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", type=Path, required=True)
    parser.add_argument("--store-id", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="Default: ~/data/webbuilder/runs/agent/<time>/<restaurant>/submitted",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        help="Default: agent/ beside submitted/, or <explicit output>-evidence",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Vision-capable Inspect model")
    parser.add_argument("--message-limit", type=int, default=DEFAULT_MESSAGE_LIMIT)
    args = parser.parse_args()
    try:
        index = generate(
            args.feed,
            args.store_id,
            args.output,
            evidence=args.evidence,
            model=args.model,
            message_limit=args.message_limit,
        )
    except (OSError, ValueError, KeyError, IncompleteBuild) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    print(index)


if __name__ == "__main__":
    main()
