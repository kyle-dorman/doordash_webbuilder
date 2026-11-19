# Task 005 — Submit the order to the mock backend

**Status** · Closed on 2026-11-19 after verification in Chrome.

Connect the shared order review page to `webbuilder-mock-backend`. The customer should be able to place a simulated order and read its confirmation on the restaurant site.

## Order flow

1. When the customer selects **Place order**, send the store ID and a list of item IDs with their quantities. Cart edits stay in the browser until this action.
2. Look up each item in that store’s feed menu. Accept positive whole-number quantities and calculate line amounts and the subtotal from the listed prices in integer cents.
3. Return the confirmed items, quantities, and subtotal. Show them on a shared confirmation view and label the order as simulated. If the request fails, keep the cart available for correction or retry.

## Done when

- From the locally served Thai Peacock site (`265151`), order two crispy spring rolls (`140240246`, $8.50 each) and one rice (`140247117`, $2.50). The mock returns line amounts of $17.00 and $2.50, and the confirmation shows **$19.50**.
- An item belonging to another store or a quantity of zero yields an error. Only an accepted order shows a confirmation.
- As a final check, enter One Stop Roti’s ID (`26303866`) in the same generator. On its storefront without photos, order one Curry Chicken (`10703144790`) and confirm **$14.95** using the same cart and checkout.
- A teammate can run the site and mock locally and repeat the walkthrough using the project’s run instructions.

## Verification

Both generated storefronts used the same checkout script and the same running mock. The browser sent only the store ID and item IDs with their quantities when **Place order** was clicked. [Local setup and browser walkthrough](../../README.md#run-the-storefronts-and-mock-checkout-locally)

| Storefront | Lines on the simulated confirmation | Confirmed total |
| --- | --- | --- |
| Thai Peacock | 2 × crispy spring rolls at $8.50 = $17.00, 1 × rice at $2.50 = $2.50 | **$19.50** |
| One Stop Roti (text-only) | 1 × Curry Chicken at $14.95 | **$14.95** |

A failed connection and a rejected submission each kept the receipt hidden and the Thai Peacock cart editable. Changing the spring rolls to one gave **$11.00** after a reload. Restoring the second order and retrying confirmed **$19.50**.

`make check` passed formatting, lint, strict type checks, and all 21 tests.

To repeat the two rejection checks against the running mock, run the commands below. Each returns HTTP 400 with an error message. The first submits One Stop Roti’s Curry Chicken to Thai Peacock. The second submits a quantity of zero.

```sh
curl -i http://127.0.0.1:8001/orders -H 'Content-Type: application/json' \
  -d '{"store_id":"265151","items":[{"item_id":"10703144790","quantity":1}]}'
curl -i http://127.0.0.1:8001/orders -H 'Content-Type: application/json' \
  -d '{"store_id":"265151","items":[{"item_id":"140240246","quantity":0}]}'
```
