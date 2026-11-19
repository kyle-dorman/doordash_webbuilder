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

The feed profile records the store comparisons and example orders. The feature roadmap sets the scope for the desktop MVP tasks. [Feed profile](docs/restaurant-feed-profile.md) · [Feature roadmap](docs/website-feature-roadmap.md)

## Preview Thai Peacock

From the repository root, serve the reviewed storefront for store `265151`.

```sh
uv run --locked --package webbuilder-site-server serve-storefront --directory build/thai-peacock
```

Open [Thai Peacock](http://127.0.0.1:8000/) in a desktop browser. Keep the server running while browsing. Press Ctrl+C in its terminal to stop it.

If the generated files are missing, run the Task 002 generator first.

```sh
uv run --locked --package webbuilder-agent generate-storefront \
  --feed ~/data/webbuilder/restaurants_feed.json \
  --store-id 265151 --output build/thai-peacock
```

The landing page features up to three photographed dishes, selected by matching restaurant tags to dish names, sections and descriptions. Feed order breaks ties and supplies pictured dishes when matches run out. The browser loads photos from the CDN URLs in the feed.

**Menu** and **Order now** both open `menu.html`. **Hours & location** opens `visit.html` with the address, phone and weekly hours. To preview another restaurant, change the store ID and output directory.

## Development

Run these commands from the workspace root.

- `make fix` applies Ruff's automatic lint fixes, sorts imports, and formats Python code.
- `make check` checks formatting and lint, runs strict mypy across the packages and tests, and runs pytest. Use `make type` or `make test` to run either step on its own.
- `uv build --all-packages` builds the three distributions.

Install the recommended VS Code extensions to use Ruff formatting and import sorting on save. The workspace uses Python 3.12 style and a 100-character line limit.

Add dependencies to the package that uses them, for example with `uv add --package webbuilder-site-server <dependency>`.
