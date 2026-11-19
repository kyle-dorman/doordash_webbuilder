# Restaurant Web Builder

A Python workspace for building white-label restaurant websites from a restaurant feed. The MVP should reflect each restaurant's style, present its full menu, and complete orders through a mocked DoorDash checkout.

## Packages

| Package | Intended responsibility |
| --- | --- |
| [`webbuilder-agent`](packages/agent/) | Generate a restaurant's site from its feed using Inspect AI and OpenAI models. |
| [`webbuilder-mock-backend`](packages/mock-backend/) | Handle the simulated DoorDash ordering flow. |
| [`webbuilder-site-server`](packages/site-server/) | Serve generated restaurant sites. |

## Local setup

From the repository root, run the following with [uv](https://docs.astral.sh/uv/). The workspace uses Python 3.12 and shares one environment and lockfile.

```sh
uv sync --locked --all-packages
uv run --locked --package webbuilder-agent inspect --version
```

The initial agent stack uses [Inspect AI's OpenAI provider](https://inspect.aisi.org.uk/providers.html#openai). Set `OPENAI_API_KEY` in your environment for live model calls. To work with the OpenAI Agents SDK as well, run `uv sync --locked --all-packages --extra agents-sdk`.

## Example feed

The local sample lives at `~/data/webbuilder/restaurants_feed.json`. Each entry in `restaurants` has a `store_id`, `store_header`, `business_profile`, `menu_book`, and `reviews`. The full menu is under `menu_book.item_lists`. Cuisine tags and available imagery provide style cues. The feed's `order_url` values point to DoorDash, so generated sites should route checkout to the mock backend.

Start with [Task 001 — Explore the restaurant feed and choose MVP test cases](docs/tasks/001-explore-restaurant-feed.md).

## Development

Add dependencies to the package that uses them, for example with `uv add --package webbuilder-site-server <dependency>`. Ruff and pytest are shared development tools.

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv build --all-packages
```
