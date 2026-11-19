# Task 008 — Compare native and Agents SDK shoppers on the edit story

**Status** · Planned.

Use the Task 007 grader and the existing Thai Peacock build for both runners. Run a fresh native control and an OpenAI Agents SDK pilot with `gpt-5.4-2026-03-05`. Record the build digest, model settings, viewport, and runner version. The historical 14-turn edit pass provides context. The fresh control uses the same viewport checks and checkpoint screenshots as the pilot.

Let the SDK Runner own the conversation and give its ComputerTool the existing restricted Playwright page. Preserve the allowed actions and stop on flagged actions. Both requests share one conversation and one 32-turn budget. The harness owns checkpoint release, receipt and mock grading, fresh attempts, and the three-attempt limit.

**Done when** · Both runners report every attempt. A pass shows one tea and one rice before the second request, followed by one accepted order and a visible $9.00 confirmation for two teas. Link each SDK attempt’s trace ID to its screenshots, tool outcomes, usage, and private grade. Compare pass counts, turns, and cost, and record whether the SDK runner is ready for the five-story comparison. [Task 007](007-computer-use-shopper.md)
