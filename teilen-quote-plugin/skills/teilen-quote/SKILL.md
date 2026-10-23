---
name: teilen-quote
description: Price Teilen demountable wall systems (glass, melamine and mixed office-front walls, T101 to T118, Teilen doors like A1, FL1, FLP, FLS) using OF4S's official Teilen calculator math, then save the quote to the shared Teilen Quote Builder so the team can finish it and send a branded customer quote. Use whenever someone asks for a Teilen quote, Teilen pricing, what a glass or demountable wall would cost, how much a set of office fronts or partition walls costs from Teilen, or wants a Teilen project added to the quote builder, even if they don't name the skill.
---

# Teilen quote

OF4S buys Teilen demountable walls and resells them installed. This skill prices a project exactly the way the **Teilen Quote Builder** does (it was built from the TN_OFFICIAL TEILEN CALCULATOR Google Sheet), and saves the result into that app.

- App: https://claude.ai/artifact/Cc1RAMzHjToBgrW7iKUktr
- Pricing script: `scripts/teilen_calc.js` (same code as the app)
- Price list and model notes: `references/price-list.md`
- Saved-quote format: `references/quote-schema.md`

## 1. Collect the walls

For each wall you need:

| Field | Notes |
|---|---|
| Name | "Conference room A front". Optional. |
| Model | A T-code from the price list. If the person describes it ("glass on top, solid bottom"), map it and say which code you chose. |
| Height and length | Feet. Accept 9'6", 9 6, 114", 9.5. |
| Doors | Door code and count. A wall can mix door types. |
| Qty | Identical walls, default 1. |

Project level, defaulting to the app's settings: install labor $50 per linear ft, door deduction 21 sqft per door, freight $600 per project, margin 30%, sales tax 0. Use the person's numbers when they give them. Some past projects used $60/ft labor and $1,200 freight.

Ask only for what is missing and can't be reasonably defaulted: model, height and length for each wall. If you're reading the walls from a drawing or plan, list what you read back to the person before pricing.

## 2. Price it with the script

Never do this math by hand. Write the quote to a JSON file and run:

```bash
node scripts/teilen_calc.js /path/to/quote.json
```

The input is the quote format in `references/quote-schema.md`. Only `walls`, `assumptions`, `margin` and `taxRate` matter for pricing. The script prints per-wall cost, warnings, total cost, sell lines, sell total and gross profit.

The math, so you can explain it:

1. Billable sqft = height × length − (door deduction × number of doors), never below 0
2. Panels = billable sqft × model price per sqft
3. Doors = door price × count
4. Install = length × labor rate
5. Wall cost = panels + doors + install, times the wall qty
6. Total cost = all walls + one freight charge
7. Customer price = each line ÷ (1 − margin), rounded to the cent. Tax is applied on top.

"Your price" is the Teilen base price plus the 5% increase. `node scripts/teilen_calc.js --prices` prints the list.

## 3. Report

Give the person:

- A short table, one row per wall: model, size, doors, wall cost.
- Total cost from Teilen, the margin, the customer price, gross profit and $ per sqft.
- Every warning the script printed, in plain words. For example, the doors don't fit the wall length, an 80" door is on a wall under 80", or T111 is on a wall 8' or shorter.

Keep cost and profit out of anything meant for the customer.

## 4. Save it to the quote builder

Offer to save the quote. On a yes, write one document to the app's database with the `ArtifactData` tool:

- `url`: https://claude.ai/artifact/Cc1RAMzHjToBgrW7iKUktr
- `action`: `set`, `collection`: `quotes`, `doc_id`: a new id such as `q` + a timestamp. Never overwrite an existing doc_id.
- `data`: the full quote document from `references/quote-schema.md`.

Before writing, `list` the `quotes` collection once to pick the next quote number (`TN-YYMM-###`, one higher than the highest number for the current month).

Then send the app link and tell them to open the quote there. From the app they can adjust it, change the status, and use the **Customer quote** tab to copy it for email or download a branded OF4S quote.

If the write fails with "no access", the person can't edit the app yet. Tell them to ask Thomas to share the Teilen Quote Builder with them as an editor or contributor. Give them the numbers in chat in the meantime.

Never change the `settings` collection (the price list). Only editors change pricing, in the app's Price list tab.

## Writing style

Follow the OF4S voice: short, direct sentences, sentence case, no em dashes in body copy, and the client addressed by first name in anything customer facing.
