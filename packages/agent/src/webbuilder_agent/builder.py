"""Give an Inspect ReAct agent one restaurant and publish the draft it submits."""

import argparse
import base64
import hashlib
import json
import re
import secrets
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from inspect_ai import Task, eval
from inspect_ai.agent import AgentSubmit, react
from inspect_ai.dataset import Sample
from inspect_ai.model import ContentImage, ContentText, GenerateConfig, Model
from inspect_ai.tool import Tool, ToolError, ToolResult, tool
from jinja2 import TemplateError
from webbuilder_shared.feed import Store, load_store
from webbuilder_shared.paths import RUNS, store_directory_name

from .render import assignment, render, screenshot

DEFAULT_MODEL = "openai/gpt-5.4"
DEFAULT_MESSAGE_LIMIT = 40
PAGE_NAME = re.compile(r"[a-z][a-z0-9-]*\.html")


@dataclass
class Preview:
    token: str
    site: Path
    homepage: bytes
    page: str
    image_path: str
    revision: int


@dataclass
class Workspace:
    store: Store
    working: Path
    evidence: Path
    sources: dict[str, str] = field(default_factory=dict)
    revision: int = 0
    previews: list[Preview] = field(default_factory=list)
    submitted: Preview | None = None
    assessment: str = ""

    def edit(self, filename: str, content: str, old_text: str | None) -> str:
        if self.submitted:
            raise ToolError("The build has already been submitted.")
        if filename != "style.css" and not PAGE_NAME.fullmatch(filename):
            raise ToolError("Use style.css or a lowercase page name such as menu.html.")
        if old_text is not None:
            original = self.sources.get(filename, "")
            if not old_text or original.count(old_text) != 1:
                raise ToolError("The text to replace must occur exactly once in the file.")
            content = original.replace(old_text, content, 1)
        if content != self.sources.get(filename):
            self.sources[filename] = content
            self.revision += 1
        return f"Saved {filename} (revision {self.revision})."

    async def preview(self, page: str) -> ToolResult:
        if self.submitted:
            raise ToolError("The build has already been submitted.")
        filename = page.partition("#")[0]
        if not PAGE_NAME.fullmatch(filename) or filename not in self.sources:
            raise ToolError("Choose an existing page by its filename, for example index.html.")
        number = len(self.previews) + 1
        site = self.working / f"preview-{number}"
        # Start each render with an empty site, including a retry after a template error.
        if site.exists():
            shutil.rmtree(site)
        site.mkdir()
        try:
            render(self.store, self.sources, site)
        except (TemplateError, ValueError, TypeError, LookupError, ArithmeticError) as error:
            raise ToolError(str(error)) from error
        if not (site / filename).is_file():
            raise ToolError(f"{filename} is a template fragment. Preview a rendered page instead.")
        image = await screenshot(site, page)
        home = image if page == "index.html" else await screenshot(site, "index.html")
        image_path = f"previews/{number:02d}-{filename.removesuffix('.html')}.png"
        destination = self.evidence / image_path
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(image)
        preview = Preview(secrets.token_hex(8), site, home, page, image_path, self.revision)
        self.previews.append(preview)
        if number == 1:
            shutil.copytree(site, self.evidence / "first")
            (self.evidence / "first.png").write_bytes(home)
            self.save_sources("first-source")
        return [
            ContentText(text=f"Preview ID: {preview.token}\n{page}, revision {self.revision}."),
            ContentImage(image="data:image/png;base64," + base64.b64encode(image).decode("ascii")),
        ]

    def submit(self, preview_id: str, assessment: str) -> str:
        preview = self.previews[-1] if self.previews else None
        if not preview or preview.token != preview_id or preview.revision != self.revision:
            raise ToolError("Preview the current draft and submit the ID returned with its image.")
        self.submitted = preview
        self.assessment = assessment
        return "Submitted " + preview_id

    def save_sources(self, name: str) -> None:
        directory = self.evidence / name
        directory.mkdir()
        for filename, source in self.sources.items():
            (directory / filename).write_text(source, encoding="utf-8")


def build_task(workspace: Workspace, message_limit: int) -> Task:
    @tool
    def edit() -> Tool:
        async def execute(filename: str, content: str, old_text: str | None = None) -> str:
            """Write a storefront page template or stylesheet, or revise a passage in it.

            Args:
                filename: style.css or a lowercase page filename such as index.html.
                content: Complete new file, or replacement text when old_text is supplied.
                old_text: Optional unique exact passage to replace in the existing file.
            """
            return workspace.edit(filename, content, old_text)

        return execute

    @tool(max_output=0)
    def preview() -> Tool:
        async def execute(page: str = "index.html") -> ToolResult:
            """Render the current templates and see a 1280 by 900 browser screenshot.

            Args:
                page: Filename, optionally with an anchor (for example, index.html#menu).
            """
            return await workspace.preview(page)

        return execute

    @tool
    def submit() -> Tool:
        async def execute(preview_id: str, assessment: str) -> str:
            """Publish the current previewed build and explain your visual decisions.

            Args:
                preview_id: Exact ID returned with the latest screenshot of this draft.
                assessment: What you observed and changed after preview, or why you kept it.
            """
            return workspace.submit(preview_id, assessment)

        return execute

    return Task(
        name="build_storefront",
        dataset=[Sample(id=workspace.store.store_id, input=assignment(workspace.store))],
        solver=react(
            tools=[edit(), preview()],
            submit=AgentSubmit(tool=submit(), keep_in_messages=True),
        ),
        config=GenerateConfig(parallel_tool_calls=False),
        message_limit=message_limit,
    )


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
    model_name = model if isinstance(model, str) else str(model.name)
    report: dict[str, object] = {
        "store_id": store_id,
        "restaurant": store.name,
        "feed_sha256": hashlib.sha256(feed.expanduser().read_bytes()).hexdigest(),
        "model": model_name,
        "message_limit": message_limit,
        "status": "incomplete",
    }
    # Claim the evidence directory before starting a paid evaluation. An interrupted
    # run keeps its initial status and another writer cannot use the same directory.
    report_path = evidence / "run.json"
    with report_path.open("x", encoding="utf-8") as initial:
        initial.write(json.dumps(report, indent=2) + "\n")
    with TemporaryDirectory(prefix=".storefront-", dir=output.parent) as working:
        workspace = Workspace(store, Path(working), evidence)
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
            if log.status != "success" or workspace.submitted is None:
                error = log.error or (sample.error if sample else None)
                raise IncompleteBuild(error.message if error else "No preview was submitted.")
            selected = workspace.submitted
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
            report["previews"] = [
                {"revision": p.revision, "page": p.page, "image": p.image_path}
                for p in workspace.previews
            ]
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
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
        print(
            generate(
                args.feed,
                args.store_id,
                args.output,
                evidence=args.evidence,
                model=args.model,
                message_limit=args.message_limit,
            )
        )
    except (OSError, ValueError, KeyError, IncompleteBuild) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")


if __name__ == "__main__":
    main()
