# Restaurant Web Builder

A Python workspace for building white-label restaurant websites from a restaurant feed. The MVP should reflect each restaurant's style, present its full menu, and complete orders through a mocked DoorDash checkout.

## Packages

| Package | Intended responsibility |
| --- | --- |
| [`webbuilder-agent`](packages/agent/) | Design and preview a storefront with one Inspect AI assignment per restaurant. |
| [`webbuilder-shared`](packages/shared/) | Read restaurant feeds and supply the catalog, cart and simulated checkout. |
| [`webbuilder-static`](packages/static/) | Generate the deterministic reference storefront from a restaurant feed. |
| [`webbuilder-mock-backend`](packages/mock-backend/) | Handle the simulated DoorDash ordering flow. |
| [`webbuilder-site-server`](packages/site-server/) | Serve generated restaurant sites. |
| [`webbuilder-shopper`](packages/shopper/) | Run and grade shopper stories against a generated site and its mock checkout. |

## Local setup

From the repository root, run the following with [uv](https://docs.astral.sh/uv/). The workspace uses Python 3.12 and shares one environment and lockfile.

```sh
uv sync --locked --all-packages
```

Generated storefronts, screenshots, Inspect logs, and shopper reports live under `~/data/webbuilder/runs/`. The task record links to the reference sites, first renders, submitted builds and shopper results. [Independent Terra pilot](docs/tasks/011-agentic-storefront-builder.md#independent-terra-pilot) · [Original Task 011 pilot](docs/tasks/011-agentic-storefront-builder.md#pilot-results)

The computer-use shopper uses the OpenAI Agents SDK. Set `OPENAI_API_KEY` in your environment for live model calls.

## Example feed

The local sample lives at `~/data/webbuilder/restaurants_feed.json`. Each entry in `restaurants` has a `store_id`, `store_header`, `business_profile`, `menu_book`, and `reviews`. The full menu is under `menu_book.item_lists`. Cuisine tags and available imagery provide style cues. The feed's `order_url` values point to DoorDash, so generated sites should route checkout to the mock backend.

The feed profile records the store comparisons and example orders. The feature roadmap sets the scope for the desktop MVP tasks. [Feed profile](docs/restaurant-feed-profile.md) · [Feature roadmap](docs/website-feature-roadmap.md)

## Run the storefronts and mock checkout locally

Generate both storefronts from the same feed. These commands run from the repository root and do not require an API key.

```sh
feed=~/data/webbuilder/restaurants_feed.json
uv run --locked --package webbuilder-static generate-storefront \
  --feed "$feed" --store-id 265151
uv run --locked --package webbuilder-static generate-storefront \
  --feed "$feed" --store-id 26303866
```

Start the mock in its own terminal. It reads menu prices at startup and listens on `127.0.0.1:8001`. If you switch feeds, regenerate the storefronts and restart the mock with that file.

```sh
uv run --locked --package webbuilder-mock-backend serve-mock-backend \
  --feed ~/data/webbuilder/restaurants_feed.json
```

Start Thai Peacock in a second terminal.

```sh
uv run --locked --package webbuilder-site-server serve-storefront \
  --directory ~/data/webbuilder/runs/reference/thai-peacock
```

Start One Stop Roti in a third terminal.

```sh
uv run --locked --package webbuilder-site-server serve-storefront \
  --directory ~/data/webbuilder/runs/reference/one-stop-roti --port 8002
```

Keep the servers running while browsing. Each storefront forwards `POST /orders` to the same mock. To use a different mock port, set `--port` on the mock and `--mock-port` on each storefront. Press Ctrl+C in each terminal to stop its server.

### Try a simulated order

Open **Menu**, add the items below, open **Review cart**, and select **Place order**.

- At Thai Peacock, add **3. Vegan Crispy Spring Rolls (4) (VG)** twice from **Small Plates** and **Rice (16oz.)** once from **Sides**. The simulated confirmation shows **$17.00** and **$2.50**, totaling **$19.50**. [Open Thai Peacock](http://127.0.0.1:8000/)
- At One Stop Roti, add one **Curry Chicken** from **Roti**. The same checkout on the text-only storefront confirms **$14.95**. [Open One Stop Roti](http://127.0.0.1:8002/)

Cart edits stay in the current browser tab until submission. The mock prices each selection from the specified store’s menu. A successful confirmation clears that store’s cart. If checkout fails, edit the quantities or select **Place order** again. [Task 5 verification and rejection examples](docs/tasks/005-mock-checkout.md#verification)

To preview another restaurant, change the store ID. Use `--output` to choose a different destination. The landing page features up to three photographed dishes, selected by matching restaurant tags to dish names, sections and descriptions. Feed order breaks ties and supplies pictured dishes when matches run out. The browser loads photos from the CDN URLs in the feed. **Hours & location** shows the address, phone and weekly hours.

## Generate an agent-designed storefront

Install the preview browser with `make shopper-browser`. With `OPENAI_API_KEY` in `.env`, give the builder a single store.

```sh
uv run --locked --package webbuilder-agent --env-file .env generate-agent-storefront \
  --feed ~/data/webbuilder/restaurants_feed.json --store-id 265151
```

Use store ID `26303866` for One Stop Roti. The builder uses `openai/gpt-6.1-terra` with high reasoning effort and can use up to 100 messages for edits and previews. Use `--model` to choose another model and `--message-limit` to change the budget.

Each restaurant gets its own assignment from its feed. The builder draws a mood and palette from the food, tags and imagery, then designs the layout and a browsing interaction to suit. It can be selective on the landing page. The full menu includes every section, item, price, supplied description and dish image in feed order. The builder previews the site and tries its custom control in Chromium. The shared cart handles ordering and checkout.

Each run gets a fresh folder at `~/data/webbuilder/runs/agent/<timestamp>/<restaurant>/`. The submitted site goes in `submitted/`. The `agent/` directory keeps the first render, source files, screenshots, run record and Inspect log. Use `--output` and `--evidence` to choose specific destinations. A run that ends before submission is recorded as incomplete.

Serve the submitted output with `serve-storefront` and the same mock checkout as the reference. Pass the printed index file’s parent directory to `run-computer-shopper --site` to evaluate Thai Peacock after submission. [Task 011 pilot and comparisons](docs/tasks/011-agentic-storefront-builder.md#pilot-results)

## Run all five Thai Peacock shopper stories

From the repository root, with the sample feed at `~/data/webbuilder/restaurants_feed.json`, run

```sh
make stories
```

This installs Playwright’s headless Chromium on first use, generates `~/data/webbuilder/runs/reference/thai-peacock`, and runs each story in a fresh browser session with its own local site and mock checkout. The scripted tester chooses each Playwright action in Python and runs without an API key. The command prints one result per story and exits successfully when all five pass. The generated site stays in place for the next runner. [Task 006 results](docs/tasks/006-scripted-browser-tests.md#verification)

### Run the computer-use shopper on that build

The shopper defaults to `gpt-6.1-terra`. With the Task 006 build present and `OPENAI_API_KEY` in `.env`, this command runs all five stories through the Agents SDK.

```sh
uv run --locked --package webbuilder-shopper --env-file .env run-computer-shopper \
  --site ~/data/webbuilder/runs/reference/thai-peacock --feed ~/data/webbuilder/restaurants_feed.json
```

The shopper chooses its actions from viewport screenshots using the SDK’s `ComputerTool`. Each story gets up to three fresh attempts and stops at its first pass. The command serves a snapshot of the supplied build and writes the report, action histories and screenshots under `~/data/webbuilder/runs/computer-shopper/`.

Add `--story change` to run just the cart edit. The grader checks for one tea, one rice and zero submissions, then saves the cart screenshot. Only then does it send the change request in the same conversation with the remaining turns. A pass requires one accepted order and a visible $9.00 receipt for two teas. [Task 010 verification](docs/tasks/010-split-shopper-testers.md#verification)

Use `--model` to select another model. The original two-runner pilot is available at revision `912adcb`. [Edit pilot](docs/tasks/008-agents-sdk-edit-story.md) · [Five-story model comparison](docs/tasks/009-shopper-model-comparison.md)

## Development

Run these commands from the workspace root.

- `make fix` applies Ruff's automatic lint fixes, sorts imports, and formats Python code.
- `make check` checks formatting and lint, runs strict mypy across the packages and tests, and runs pytest. Use `make type` or `make test` to run either step on its own.
- `uv build --all-packages` builds the workspace distributions.

Install the recommended VS Code extensions to use Ruff formatting and import sorting on save. The workspace uses Python 3.12 style and a 100-character line limit.

Add dependencies to the package that uses them, for example with `uv add --package webbuilder-site-server <dependency>`.
