import base64
import json
import re
import struct
from pathlib import Path

import pytest
from inspect_ai.model import (
    ChatMessage,
    ContentImage,
    GenerateConfig,
    ModelOutput,
    get_model,
)
from inspect_ai.tool import ToolChoice, ToolInfo
from test_storefront import write_sample_feed
from webbuilder_agent.builder import IncompleteBuild, generate
from webbuilder_agent.render import render
from webbuilder_shared.feed import load_store

MODEL = "mockllm/design"
HOME = """<main id="menu"><h1>{{ store.name }}</h1>
{% for section in store.sections %}
<h2>{{ section.name }}</h2>
{% for item in section.items %}
<article>{{ item.name }} {{ item.display_price }} {{ add_button(item) }}</article>
{% endfor %}{% endfor %}</main><a href="review.html">Review order</a>"""
CHECKOUT = "<h1>{{ store.name }}</h1>{{ review_markup('index.html#menu') }}"


def snapshot(site: Path) -> dict[Path, bytes]:
    return {p.relative_to(site): p.read_bytes() for p in site.rglob("*") if p.is_file()}


def test_preview_revision_and_submission(tmp_path: Path) -> None:
    feed = write_sample_feed(tmp_path, with_photos=False)
    store = load_store(feed, "123")
    output, evidence = tmp_path / "site", tmp_path / "evidence"
    css = "body { background: white; }"
    steps = iter(
        [
            ("edit", {"filename": "index.html", "content": HOME + "{{ unknown_value }}"}),
            ("edit", {"filename": "review.html", "content": CHECKOUT}),
            ("edit", {"filename": "style.css", "content": css}),
            ("preview", {}),
            ("edit", {"filename": "index.html", "old_text": "{{ unknown_value }}", "content": ""}),
            ("preview", {}),
            ("edit", {"filename": "style.css", "old_text": "white", "content": "gold"}),
            ("submit", {}),
            ("preview", {}),
            ("submit", {}),
        ]
    )
    token = ""
    images: list[bytes] = []
    seen_errors: list[str] = []

    def respond(
        messages: list[ChatMessage],
        tools: list[ToolInfo],
        choice: ToolChoice,
        config: GenerateConfig,
    ) -> ModelOutput:
        nonlocal token
        # Providers without image-in-tool support receive the screenshot in a user message.
        latest = messages[-1]
        for message in messages[-2:]:
            if message.role == "tool" and message.error:
                seen_errors.append(message.error.message)
            if match := re.search(r"Preview ID: ([0-9a-f]+)", message.text):
                token = match[1]
        if isinstance(latest.content, list):
            for part in latest.content:
                if isinstance(part, ContentImage):
                    image = base64.b64decode(part.image.split(",", 1)[1])
                    assert image[:8] == b"\x89PNG\r\n\x1a\n"
                    assert struct.unpack(">II", image[16:24]) == (1280, 900)
                    images.append(image)
        name, args = next(steps)
        if name == "submit":
            args = {"preview_id": token, "assessment": "Adjusted the background after preview."}
        return ModelOutput.for_tool_call(MODEL, name, args)

    model = get_model(MODEL, custom_outputs=respond, memoize=False)
    # The final permitted assistant message submits. Its tool receipt hits Inspect's limit.
    index = generate(feed, "123", output, evidence=evidence, model=model, message_limit=21)
    report = json.loads((evidence / "run.json").read_text())
    assert report["status"] == "submitted" and (evidence / report["inspect_log"]).is_file()
    assert report["limit"]["type"] == "message"
    assert len(report["previews"]) == 2
    assert any("unknown_value" in message for message in seen_errors)
    assert any("current draft" in message for message in seen_errors)
    assert images == [(evidence / name).read_bytes() for name in ("first.png", "final.png")]
    assert images[0] != images[1]
    assert index == output / "index.html"
    for source, site, color in [
        ("first-source", evidence / "first", "white"),
        ("submitted-source", output, "gold"),
    ]:
        files = {p.name: p.read_text() for p in (evidence / source).iterdir()}
        assert files["style.css"] == css.replace("white", color)
        rebuilt = tmp_path / ("rebuilt-" + color)
        rebuilt.mkdir()
        render(store, files, rebuilt)
        assert snapshot(site) == snapshot(rebuilt)
    assert report["submitted_preview"] == report["previews"][-1]["image"]


def test_message_budget_cannot_publish_an_unsubmitted_build(tmp_path: Path) -> None:
    feed = write_sample_feed(tmp_path, with_photos=False)
    model = get_model(MODEL, memoize=False)
    with pytest.raises(IncompleteBuild, match="No preview was submitted"):
        generate(feed, "123", tmp_path / "site", model=model, message_limit=3)
    report = json.loads((tmp_path / "site-evidence" / "run.json").read_text())
    assert report["status"] == "incomplete" and report["limit"]["type"] == "message"
    assert not (tmp_path / "site").exists()
