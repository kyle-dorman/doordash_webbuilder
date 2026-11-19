# Task 003 — Serve the reviewed storefront locally

**Status** · Closed on 2026-11-19 after owner review. Verified in desktop Chrome using the reviewed [Task 002 storefront](002-generate-static-storefront.md).

Use `webbuilder-site-server` to serve the generated Thai Peacock storefront (store `265151`) at a local HTTP address. Point the server at the output directory from Task 002 and serve the existing HTML and assets from disk. Document the command to run from the workspace root and the URL to open.

## Done when

1. Start the server with the documented command. Open its URL in a desktop browser and confirm the page matches the reviewed storefront, including the restaurant header, menu styling, and imagery.
2. Jump to **Small Plates** and find the crispy spring rolls at $8.50. Refresh the page and confirm the menu and its assets still load.

## Verified preview

From the workspace root, run this command and open [Thai Peacock](http://127.0.0.1:8000/).

```sh
uv run --locked --package webbuilder-site-server serve-storefront --directory ~/data/webbuilder/runs/reference/thai-peacock
```

- The served landing page matched the reviewed desktop preview, including the Thai Peacock header, hero photo and three featured dishes. The existing files were used directly with their original CDN image URLs.
- **Menu** and **Order now** each opened the full menu with 13 sections and 18 entries. **Hours & location** displayed the Portland address, phone number and all seven days of posted hours.
- **Small Plates** showed **Vegan Crispy Spring Rolls** at **$8.50**. With the browser cache disabled, refreshing kept the selected section and restored the styled menu, restaurant logo and all 18 dish photos. Clicking **Sides** and then **Small Plates** scrolled to each section and updated the highlighted link.
- `make check` passed formatting, lint, strict type checks and all seven tests. All three workspace packages built successfully.
