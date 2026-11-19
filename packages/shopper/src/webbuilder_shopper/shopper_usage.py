"""Token counts and standard-rate estimates for the edit-story comparison."""

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from agents.usage import Usage
    from openai.types.responses.response_usage import ResponseUsage

# USD per million tokens, https://developers.openai.com/api/docs/models/gpt-5.4
MODEL = "gpt-5.4-2026-03-05"


class UsageSummary(TypedDict):
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    responses_with_usage: int
    estimated_cost_usd: float | None


def token_counts(usage: "ResponseUsage | Usage | None") -> dict[str, int] | None:
    if usage is None or not usage.total_tokens:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": usage.input_tokens_details.cached_tokens,
        "output_tokens": usage.output_tokens,
        "reasoning_tokens": usage.output_tokens_details.reasoning_tokens,
        "total_tokens": usage.total_tokens,
    }


def summarize_usage(
    history: list[dict[str, object]], model: str, turns: int | None = None
) -> UsageSummary:
    """Sum reported counts. Quote a cost only for a complete, known short-context run."""
    responses = [event for event in history if event["event"] == "response"]
    counts = [usage for event in responses if isinstance(usage := event.get("usage"), dict)]
    input_tokens = sum(row["input_tokens"] for row in counts)
    cached = sum(row["cached_input_tokens"] for row in counts)
    output = sum(row["output_tokens"] for row in counts)
    complete = len(counts) == (len(responses) if turns is None else turns)
    estimate = None
    if (
        counts
        and complete
        and model == MODEL
        and all(row["input_tokens"] <= 272_000 for row in counts)
    ):
        estimate = ((input_tokens - cached) * 2.50 + cached * 0.25 + output * 15.00) / 1_000_000
    return UsageSummary(
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        output_tokens=output,
        reasoning_tokens=sum(row["reasoning_tokens"] for row in counts),
        total_tokens=sum(row["total_tokens"] for row in counts),
        responses_with_usage=len(counts),
        estimated_cost_usd=estimate,
    )
