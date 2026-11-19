# Restaurant feed profile

[Task 001](tasks/001-explore-restaurant-feed.md) closed on 2026-11-19.

Source file `~/data/webbuilder/restaurants_feed.json` · `generated_at` = `2026-11-19`

The desktop MVP will display choice instructions as supplied. Size, protein, and side selection are planned for Tier 2. [Website feature roadmap](website-feature-roadmap.md)

## Three stores to try

| Proposed role | Store | What we should see |
| --- | --- | --- |
| First build | **Thai Peacock** · `265151` | Both store images and a photo for every item. Show all 13 lists. In `menu_book.item_lists`, open **Small Plates**, then item `140240246`, “3. Vegan Crispy Spring Rolls (4) (VG)”. Its `price` gives `unit_amount=850`, `currency=USD`, `display_string=$8.50`. Two orders plus one **Sides** → Rice (16oz.) (`140247117`, $2.50) should produce a **$19.50 subtotal** on the mock confirmation. |
| Text-only storefront | **ONE STOP ROTI SHOP AND BAKERY, INC.** · `26303866` | No store or item images and only 3 item descriptions. Use the restaurant name as the masthead. **Roti** → Curry Chicken (`10703144790`) should still be visible and orderable at $14.95 with just its name and price. |
| Ambiguous order | **Joy** · `476002` | **Small Plates And Soups** → Cold Salad Appetizers (`9287260604`) is listed at $0.00 and says “Pick from daily selection in select sizes”. The selections, sizes and their prices are absent. Provisionally, keep the entry visible and explain why it cannot be added to the mock cart. |

## What the feed supplies

Each entry in `restaurants` represents a store, keyed by a string `store_id`. `store_header.data` supplies the name, cuisine, tags, price range, address, image URLs and DoorDash store link. `business_profile.locations` has one location per store with phone, time zone and weekly hours. `reviews` has an aggregate rating and count for every store. Bryant Cafe and Willie G’s have ratings but no written reviews to feature.

`menu_book.item_lists` holds named sections in feed order. Each entry in a section’s `items` has an ID, name, price, and optional description and photo URL. The snapshot has **216 entries in 163 sections**, with 18 entries per store. No section is empty and 122 contain a single entry. All 216 IDs are distinct across all lists and stores. “Full menu” here means every supplied entry in its original section.

| Store ID | Restaurant | Lists | Entries | Item photos | Style cues | Store images |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `1388` | Bay Cities Italian Deli & Bakery | 18 | 18 | 15/18 | Italian deli, sandwiches | Header + cover |
| `10586` | Quang | 12 | 18 | 16/18 | Vietnamese, pho, bubble tea | Header + cover |
| `3932` | Adelitas Taqueria, Restaurant & Bar | 18 | 18 | 15/18 | Mexican, tacos, burritos | Header + cover |
| `238516` | Dynasty Chinese Food | 18 | 18 | 10/18 | Chinese, bilingual section names | Header + cover |
| `265151` | Thai Peacock | 13 | 18 | 18/18 | Thai, noodles, fried rice | Header + cover |
| `476002` | Joy | 14 | 18 | 17/18 | Taiwanese, bilingual dish names | Header + cover |
| `254678` | Yamazaru | 17 | 18 | 16/18 | Japanese, ramen, sushi | Header + cover |
| `26303866` | ONE STOP ROTI SHOP AND BAKERY, INC. | 8 | 18 | 0/18 | Indian cuisine label, roti and doubles sections | None |
| `329653` | Bryant Cafe | 4 | 18 | 0/18 | American Traditional, burgers | Cover only |
| `541378` | Willie G's BBQ And Fish | 13 | 18 | 0/18 | Soul Food, fish, barbecue | Cover only |
| `333810` | Puerto Rico Bakery & Restaurant | 10 | 18 | 12/18 | Puerto Rican, bilingual menu | Header + cover |
| `65787` | Central Texas Style BBQ | 18 | 18 | 16/18 | American, barbecue | Header + cover |

Photo counts measure supplied URLs. Across the feed, 135/216 entries have a photo and 64/216 lack a description. Use the store’s images where supplied and let names, section labels and prices stand alone elsewhere. All 12 logos and business descriptions are null. Colors and typography are design choices the feed leaves open.

## What matters for the mock

- **Keep the original labels and IDs.** Thai Peacock’s $16.50 Lychee Hibiscus Daiquiri appears under **Popular Drinks** (`913650617`) and **House Signature Cocktails (Alcoholic)** (`478625263`). Keep both placements. Preserve sections such as Bay Cities’ **APPAREL** and Dynasty’s **Egg Foo Young (omelets)芙蓉蛋🥚**.
- **Calculate a store-specific subtotal.** All 216 prices are integer USD cents and agree with their display strings. Four entries are $0.00, including two separately identified utensil packs at Quang. The high end is Quang’s 40-roll catering tray at $155.00 (**Appetizers**, `40861038099`). Preserve those amounts. Send the store ID, item IDs and quantities to the mock to price and confirm the order. All 12 `order_url` values lead to live DoorDash pages. Taxes, fees, payment and fulfillment details are absent, so a simulated confirmation can stop at the item subtotal.
- **Keep choice instructions visible.** None of the 216 entries supplies structured modifiers, defaults or surcharges. Even a positive price can accompany an unresolved choice. Thai Peacock’s **Fried Rice** → Khao Pad (`140245490`, $16.50) asks for a protein but lists none. Defer customization until we choose how such entries should behave.
- **Show hours as supplied.** Dynasty (`238516`) has two intervals every day, including Monday 00:00–02:00 and 11:00–23:59 local time. Defer live order gating since the snapshot has store hours but no item availability.
