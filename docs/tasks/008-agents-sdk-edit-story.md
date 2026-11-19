# Task 008 — Compare native and Agents SDK shoppers on the edit story

**Status** · Closed on 2026-11-19. Both runners passed the fresh edit story on attempt 1.

Use the Task 007 grader and the existing Thai Peacock build for both runners. Run a fresh native control and an OpenAI Agents SDK pilot with `gpt-5.4-2026-03-05`. Record the build digest, model settings, viewport, and runner version. The historical 14-turn edit pass provides context. The fresh control uses the same viewport checks and checkpoint screenshots as the pilot.

Let the SDK Runner own the conversation and give its ComputerTool the existing restricted Playwright page. Preserve the allowed actions and stop on flagged actions. Both requests share one conversation and one 32-turn budget. The harness owns checkpoint release, receipt and mock grading, fresh attempts, and the three-attempt limit.

**Done when** · Both runners report every attempt. A pass shows one tea and one rice before the second request, followed by one accepted order and a visible $9.00 confirmation for two teas. Link each SDK attempt’s trace ID to its screenshots, tool outcomes, usage, and private grade. Compare pass counts, turns, and cost, and record whether the SDK runner is ready for the five-story comparison. [Task 007](007-computer-use-shopper.md)

## Live comparison

Each runner passed **1/1 stories on the first attempt** and **1/1 within three attempts**. The fresh native control took 16 turns with the current viewport grader. The historical 14-turn native pass used the earlier grader. [Task 007 grading changes](007-computer-use-shopper.md#grading-changes-after-the-baseline)

| Runner | Attempt | Turns to verified cart | Further turns to order | Total turns | Input tokens (cached subset) | Output tokens | Estimated model cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Native Responses | 1 · pass | 13 | 3 | 16 | 207,414 (154,880) | 1,052 | $0.185835 |
| OpenAI Agents SDK | 1 · pass | 12 | 3 | 15 | 182,699 (136,448) | 777 | $0.1613945 |

Both checkpoint images show one Thai Lime Tea and one Rice (16oz.) with a $7.00 subtotal. Each mock received exactly one submission and accepted two Thai Lime Teas at $4.50 each. Both final viewport images show those two teas and the $9.00 total.

| Attempt | Private grade, mock and usage | Visible cart before edit | Visible receipt | Tool evidence |
| --- | --- | --- | --- | --- |
| Native 1 | [Report](evidence/008-native/report.json) | [Cart](evidence/008-native/change-1-cart.png) | [Receipt](evidence/008-native/change-1.png) | [Actions and per-turn usage](evidence/008-native/change-1.json) |
| SDK 1 | [Report with trace ID](evidence/008-sdk/report.json) | [Cart](evidence/008-sdk/change-1-cart.png) | [Receipt](evidence/008-sdk/change-1.png) | [Actions, per-turn usage and frame paths](evidence/008-sdk/change-1.json) |

The SDK exported one trace for the whole attempt, `trace_77fc7ae4e3d8458da09ddc59fce77206`. The trace covers both requests, the computer calls and the private grade. The grade span names the local evidence files. The action history associates each tool screenshot with its call ID and each model response with its token usage. [SDK trace](https://platform.openai.com/logs/trace?trace_id=trace_77fc7ae4e3d8458da09ddc59fce77206) · [Saved viewport frames](evidence/008-sdk/change-1-frames/)

The estimates use the reported tokens from every turn and standard rates of $2.50 per million uncached input tokens, $0.25 per million cached input tokens and $15.00 per million output tokens. Output includes reasoning tokens. The per-attempt figures are also the total spend per passing story because neither runner needed a retry. [GPT-5.4 pricing](https://developers.openai.com/api/docs/models/gpt-5.4)

## Repeat the comparison

At revision `912adcb`, use the existing build and its source feed, with `OPENAI_API_KEY` in `.env`. Install Chromium once with `make shopper-browser`. Each invocation prints its own fresh evidence directory under `logs/computer-shopper/`. To choose a destination, pass `--evidence` with a new or empty directory for that runner.

```sh
for runner in native sdk; do
  uv run --locked --package webbuilder-shopper --env-file .env run-computer-shopper \
    --runner "$runner" --story change --site build/thai-peacock \
    --feed ~/data/webbuilder/restaurants_feed.json \
    --model gpt-5.4-2026-03-05 --step-limit 32
done
```

- **Build and feed.** Both runners served byte-identical snapshots of the eight files in `build/thai-peacock`, store `265151`. Build SHA-256 is `fa7738a6d3846517f324576391d6187b8795a8355e490926d1ccc2442eefefd9`. The feed SHA-256 is `45a4250e335a3197505941fcccd2a1cd9a63b54f0afc550301f53bd82c63c02d`. [Native manifest](evidence/008-native/build-files.json) · [SDK manifest](evidence/008-sdk/build-files.json)
- **Model and browser.** Both used `gpt-5.4-2026-03-05` with the GA `computer` tool, identical shopper instructions, low reasoning effort, and a maximum of 2,048 output tokens per response. Both used OpenAI Python 3.55.1, Playwright 1.65.2, and headless Chromium 159.0.8154.6 with a 1280 × 900 PNG viewport. The SDK runner used `openai-agents` 0.25.0. The reports include the package versions and settings.
- **Requests and budget.** Each attempt starts at the homepage in a new browser context with an empty cart, a new mock, and a new conversation. The first request is “Add one Thai Lime Tea and one 16 oz rice to the cart. Show me my cart.” After the private grader verifies both quantities in the viewport, checks for zero submissions and saves the cart PNG, it releases “Change the quantity to two teas, remove the rice, and place the order.” Every model response counts as one turn, including final answers and batches of actions.
- **SDK handoff.** The SDK Runner owns model turns and tool dispatch. At the checkpoint, the harness resumes the same conversation using the last response ID and the remaining turns. The ComputerTool operates on the same restricted page and uses the native action checks. A pending safety check stops the attempt before tool execution. The harness grades the visible receipt and the drained mock record independently of the shopper’s answer. [Current SDK adapter](../../packages/shopper/src/webbuilder_shopper/computer_use/shopper.py) · [Current harness](../../packages/shopper/src/webbuilder_shopper/computer_use/runner.py)

## Verification and recommendation

`make check` passed formatting, lint, strict type checks, and all **94 tests**. The SDK tests exercise the real Runner and ComputerTool with offline model responses, including a budget exhausted across the two requests, blocked actions, and token accounting on interrupted responses. The harness tests cover checkpoint release, fresh retries, early stopping, and evidence retention. [SDK tests](../../tests/test_sdk_model.py) · [Harness tests](../../tests/test_computer_runner.py)

**Use the SDK runner for Task 009.** It completed the two-request edit under the same budget and grader and preserved a trace that ties the browser actions to the graded outcome. In this pair it used one fewer turn and about $0.0244 less in estimated model cost. A single attempt per runner supports proceeding with the five-story evaluation, while estimates of relative cost and reliability need more runs. [Task 009](009-shopper-model-comparison.md)
