"""Token counts and standard-rate estimates for the shopper comparison."""

from decimal import Decimal
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from agents.usage import Usage

MODEL = "gpt-5.4-2026-03-05"
TERRA = "gpt-6.1-terra"
SHORT_CONTEXT_LIMIT = 272_000


class UsageSummary(TypedDict):
    input_tokens: int
    cached_input_tokens: int
    cache_write_input_tokens: int
    ttl_30m_tokens: int
    ttl_12h_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    responses_with_usage: int
    priced_responses: int
    # Estimate for the subset of responses with enough reported usage to price.
    reported_cost_usd: float | None
    estimated_cost_usd: float | None


def token_counts(usage: "Usage | None") -> dict[str, int] | None:
    if usage is None or not usage.total_tokens:
        return None
    counts = {
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": usage.input_tokens_details.cached_tokens,
        "output_tokens": usage.output_tokens,
        "reasoning_tokens": usage.output_tokens_details.reasoning_tokens,
        "total_tokens": usage.total_tokens,
    }
    details = usage.input_tokens_details
    writes = getattr(details, "cache_write_tokens", None)
    if isinstance(writes, int):
        counts["cache_write_input_tokens"] = writes
    retention = getattr(details, "cache_write_tokens_details", None)
    if retention is not None:
        for field in ("ttl_30m_tokens", "ttl_12h_tokens"):
            value = getattr(retention, field, None)
            if isinstance(value, int):
                counts[field] = value
    return counts


def _response_cost(row: dict[str, int], model: str) -> Decimal | None:
    """Estimate one response in USD using the standard model rates per million tokens."""
    inputs, cached, outputs = row["input_tokens"], row["cached_input_tokens"], row["output_tokens"]
    if not 0 <= cached <= inputs or outputs < 0:
        return None
    if model == MODEL:
        # https://developers.openai.com/api/docs/models/gpt-5.4
        input_cost = (inputs - cached) * Decimal("2.50") + cached * Decimal("0.25")
        output_cost = outputs * Decimal("15.00")
    elif model == TERRA:
        # https://developers.openai.com/api/docs/models/gpt-6.1-terra
        # https://developers.openai.com/api/docs/guides/prompt-caching
        writes = row.get("cache_write_input_tokens")
        short_writes = row.get("ttl_30m_tokens", 0)
        long_writes = row.get("ttl_12h_tokens", 0)
        if (
            writes is None
            or min(short_writes, long_writes) < 0
            or short_writes + long_writes != writes
            or cached + writes > inputs
        ):
            return None
        ordinary = inputs - cached - writes
        input_cost = (
            ordinary
            + cached * Decimal("0.05")
            + short_writes * Decimal("1.25")
            + long_writes * Decimal("2.50")
        )
        output_cost = outputs * Decimal("5.00")
        if inputs > SHORT_CONTEXT_LIMIT:
            input_cost *= 2
            output_cost *= Decimal("1.5")
    else:
        return None
    return (input_cost + output_cost) / 1_000_000


def summarize_usage(
    history: list[dict[str, object]], model: str, turns: int | None = None
) -> UsageSummary:
    """Keep measured usage and its subtotal even if an attempt lacks a priced response."""
    responses = [event for event in history if event["event"] == "response"]
    counts = [usage for event in responses if isinstance(usage := event.get("usage"), dict)]
    # Preserve the existing GPT-5.4 short-context estimator's scope. Its long-context
    # pricing applies to the full session; Terra's threshold applies to individual requests.
    prices = []
    if model != MODEL or all(row["input_tokens"] <= SHORT_CONTEXT_LIMIT for row in counts):
        prices = [cost for row in counts if (cost := _response_cost(row, model)) is not None]
    subtotal = float(sum(prices)) if prices else None
    complete = len(prices) == len(responses) and (turns is None or turns == len(responses))
    return UsageSummary(
        input_tokens=sum(row["input_tokens"] for row in counts),
        cached_input_tokens=sum(row["cached_input_tokens"] for row in counts),
        cache_write_input_tokens=sum(row.get("cache_write_input_tokens", 0) for row in counts),
        ttl_30m_tokens=sum(row.get("ttl_30m_tokens", 0) for row in counts),
        ttl_12h_tokens=sum(row.get("ttl_12h_tokens", 0) for row in counts),
        output_tokens=sum(row["output_tokens"] for row in counts),
        reasoning_tokens=sum(row["reasoning_tokens"] for row in counts),
        total_tokens=sum(row["total_tokens"] for row in counts),
        responses_with_usage=len(counts),
        priced_responses=len(prices),
        reported_cost_usd=subtotal,
        estimated_cost_usd=subtotal if complete else None,
    )
