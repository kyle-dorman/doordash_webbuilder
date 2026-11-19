# Task 009 — Compare GPT-5.4 and GPT-6.1 Terra across five stories

**Status** · Closed on November 19, 2026. Both five-story SDK runs completed. [Task 008 pilot](008-agents-sdk-edit-story.md)

Run all five agreed Thai Peacock stories through the verified SDK runner with `gpt-5.4-2026-03-05` and `gpt-6.1-terra`. Change only the model. Hold the build, feed, requests, tools, viewport, reasoning setting, grader, and 32-turn budget fixed. Give each story up to three fresh attempts and stop at its first pass.

**Done when** · Report each model’s first-attempt passes, within-three passes, and total model cost per passing story, including failed attempts in the spend. Keep per-attempt steps, usage, applicable token rates, and links to traces and grader evidence. Identify incomplete runs separately. [Five agreed stories](../website-feature-roadmap.md#agreed-thai-peacock-shopper-stories)

## Live results

Both models passed all five stories on attempt 1. Terra used 26 turns to GPT-5.4’s 35 and cost **80.3% less per passing story** in this comparison. The lookup stories took the same number of turns. Terra placed the spring-roll order in 7 turns to GPT-5.4’s 12, and completed the edit in 9 turns to GPT-5.4’s 13.

| Model | First attempt | Within three | Total turns | Total estimated spend | Cost per passing story |
| --- | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.4-2026-03-05` | 5/5 | 5/5 | 35 | $0.3071165 | $0.0614233 |
| `gpt-6.1-terra` | 5/5 | 5/5 | 26 | $0.06037315 | $0.01207463 |

**Incomplete runs** · 0 for each model. There were also zero failed attempts. All 61 model responses had usage and are included in the totals. The reports are in `~/data/webbuilder/runs/009/<model>/report.json`, using the model IDs above.

## Attempt evidence

Each row links to the SDK trace. In each model directory, `<story>-1.json` contains turn-by-turn actions and token usage, `<story>-1-frames/` contains shopper screenshots, and `<story>-1.png` is the final viewport. Story IDs in table order are `contact`, `hours`, `soup`, `place`, and `change`. The edit checkpoint is `change-1-cart.png`. Each private grade in `report.json` includes the answer and mock submission record. Input includes the listed cache reads and writes. All cache writes used 30-minute retention.

### GPT-5.4

| Story · attempt | Turns and usage | Input | Cache reads | Cache writes | Output | Estimated USD | Evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Contact details · 1 | 3 | 11,259 | 4,864 | 0 | 100 | $0.0187035 | [Trace](https://platform.openai.com/logs/trace?trace_id=trace_0c0184021e9a4b5ba3fa398cba31329c) |
| Posted hours · 1 | 3 | 11,252 | 1,792 | 0 | 103 | $0.025643 | [Trace](https://platform.openai.com/logs/trace?trace_id=trace_ac90ad99b63447abb66143338e4ce9d7) |
| Tom-Yum Soup · 1 | 4 | 17,940 | 9,216 | 0 | 160 | $0.026514 | [Trace](https://platform.openai.com/logs/trace?trace_id=trace_9e5f4de19f5f44dd95a9e5eaafa6b124) |
| Place an order · 1 | 12 | 123,440 | 96,256 | 0 | 533 | $0.100019 | [Trace](https://platform.openai.com/logs/trace?trace_id=trace_7fdf557f149043358b7928942a337f12) |
| Change an order · 1 | 13 | 138,694 | 98,048 | 0 | 674 | $0.136237 | [Trace](https://platform.openai.com/logs/trace?trace_id=trace_74e14bcd1f3a4b64aa442d6050530085) |

### GPT-6.1 Terra

| Story · attempt | Turns and usage | Input | Cache reads | Cache writes | Output | Estimated USD | Evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Contact details · 1 | 3 | 11,219 | 6,045 | 5,165 | 80 | $0.0071675 | [Trace](https://platform.openai.com/logs/trace?trace_id=trace_5256f0752abb4b89bf3b0dcdaa6198c7) |
| Posted hours · 1 | 3 | 11,236 | 6,055 | 5,172 | 84 | $0.00719675 | [Trace](https://platform.openai.com/logs/trace?trace_id=trace_09542b2e3d5a458cb75f9ee2921dd6ed) |
| Tom-Yum Soup · 1 | 4 | 17,848 | 11,231 | 6,605 | 99 | $0.0093248 | [Trace](https://platform.openai.com/logs/trace?trace_id=trace_26796046baf440f285489c5332fafdf5) |
| Place an order · 1 | 7 | 46,387 | 35,415 | 10,951 | 249 | $0.0167255 | [Trace](https://platform.openai.com/logs/trace?trace_id=trace_20ec24a158e84dcd8475d11b4070fc6f) |
| Change an order · 1 | 9 | 68,459 | 55,982 | 12,450 | 314 | $0.0199586 | [Trace](https://platform.openai.com/logs/trace?trace_id=trace_ee7a4bcf86b7456ebf058ddb1868d1d6) |

For the edit, GPT-5.4 reached the verified cart at turn 10 and Terra at turn 6. Both checkpoint PNGs match the last shopper screenshot before the second request. Each model took three more turns, submitted one accepted order for two teas and left a $9.00 receipt visible. Both spring-roll orders and their receipts totaled $19.50. The three lookups produced zero mock submissions for either model.

## Reproduce the comparison

From the repository root, supply the existing Thai Peacock build, its source feed, and `OPENAI_API_KEY` in `.env`. Give each model a fresh external evidence directory.

```sh
make shopper-browser
run=~/data/webbuilder/runs/009-repeat-$(date +%Y%m%d-%H%M%S)
for model in gpt-5.4-2026-03-05 gpt-6.1-terra; do
  uv run --locked --package webbuilder-shopper --env-file .env run-computer-shopper \
    --site ~/data/webbuilder/runs/reference/thai-peacock --feed ~/data/webbuilder/restaurants_feed.json \
    --model "$model" --step-limit 32 --evidence "$run/$model"
done
make check
```

Both runs served the same eight-file snapshot of `~/data/webbuilder/runs/reference/thai-peacock` for store `265151`. Build SHA-256 was `fa7738a6d3846517f324576391d6187b8795a8355e490926d1ccc2442eefefd9`. Source feed SHA-256 was `45a4250e335a3197505941fcccd2a1cd9a63b54f0afc550301f53bd82c63c02d`. Both match the Task 008 pilot. The shared environment used `openai-agents` 0.25.0, OpenAI Python 3.55.1, Playwright 1.65.2 and headless Chromium 159.0.8154.6. Each model directory contains its `build-files.json` manifest.

The storefront loads remote images as the page opens. On the soup story, the restaurant logo had loaded in GPT-5.4’s first screenshot and was still loading in Terra’s. The first screenshot paths are recorded in each model’s `soup-1.json`.

The comparison uses the SDK shopper and private grader verified at `912adcb`. Each attempt starts at the homepage in a fresh browser context with its own conversation and mock checkout. The SDK supplies the same shopper instructions, restricted GA `computer` tool, 1280 × 900 PNG viewport, low reasoning effort and 2,048 output-token limit to both models. One model response counts as one turn. Each story stops at its first pass or after three failed attempts. An infrastructure interruption stops that run and preserves the attempts already recorded. [Runner and exact requests](../../packages/shopper/src/webbuilder_shopper/computer_use/runner.py) · [SDK adapter](../../packages/shopper/src/webbuilder_shopper/computer_use/shopper.py) · [Private grader](../../packages/shopper/src/webbuilder_shopper/grading.py)

The edit story begins with “Add one Thai Lime Tea and one 16 oz rice to the cart. Show me my cart.” The grader verifies one of each in the viewport and checks for zero submissions. The harness saves the cart PNG before sending “Change the quantity to two teas, remove the rice, and place the order.” The SDK continues from the same response ID with the turns remaining from the original 32. A pass requires exactly one accepted mock order and a visible receipt for two teas totaling $9.00.

## Model cost

Standard API rates verified on November 19, 2026, in USD per million tokens. [GPT-5.4 pricing](https://developers.openai.com/api/docs/models/gpt-5.4) · [Terra pricing](https://developers.openai.com/api/docs/models/gpt-6.1-terra) · [Prompt-cache usage fields](https://developers.openai.com/api/docs/guides/prompt-caching)

| Model | Ordinary input | Cache read | 30-minute write | 12-hour write | Output |
| --- | ---: | ---: | ---: | ---: | ---: |
| GPT-5.4 | $2.50 | $0.25 | — | — | $15.00 |
| GPT-6.1 Terra | $1.00 | $0.05 | $1.25 | $2.50 | $5.00 |

For GPT-5.4, ordinary input equals total input less cached reads. For Terra, subtract both cached reads and writes from total input, then price the reads and each write duration separately. The API includes reasoning tokens in output. Terra requests above 272,000 input tokens use twice the input and cache rates and 1.5 times the output rate. Each attempt is priced from its individual responses. Spend per passing story divides spend across **all attempts** by the number of distinct stories that passed. [Estimator](../../packages/shopper/src/webbuilder_shopper/computer_use/usage.py)

All requests in these runs were below the long-context threshold. Terra reported 78 ordinary input tokens, 114,728 cached reads, 40,343 writes and 826 output tokens. GPT-5.4 reported 92,409 ordinary input tokens, 210,176 cached reads and 1,570 output tokens.

## Verification

`make check` passed formatting, lint, strict type checking and all **96 tests**. The cost tests cover both Terra write durations, the per-request long-context boundary, missing usage, and the inclusion of failed attempts in cost per passing story. [SDK usage tests](../../tests/test_sdk_model.py) · [Retry and cost tests](../../tests/test_computer_runner.py)
