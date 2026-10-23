# Teilen quote builder

A friendlier version of the **TN_OFFICIAL TEILEN CALCULATOR** Google Sheet. It is one HTML page, published as a claude.ai artifact.

Live page: https://claude.ai/artifact/Cc1RAMzHjToBgrW7iKUktr

## What it does

- Prices Teilen demountable walls one wall at a time: panel model, height, length, doors, quantity.
- Uses the same math as the sheet:
  - Billable sqft = height × length − door deduction (21 sqft) × doors
  - Panels = billable sqft × model $/sqft (Teilen base × (1 + price increase))
  - Doors = door price × quantity
  - Install = length × labor rate per linear ft
  - Total cost = all walls + one freight charge per project
- Adds what the sheet left out: margin, sell price, gross profit, optional sales tax, and a branded OF4S customer quote (copy for email, HTML download you can print to PDF, CSV).
- Saves quotes with a status (Draft, Sent, Won, Lost). A quote that leaves Draft locks the prices it had at that moment.
- Price list tab holds the Teilen base prices (sheet dated Jan 8, 2026) and the increase %. Only editors of the artifact can change it.

## Files

- `teilen-quote-builder.html`: the page. Pricing logic sits between the `CALC-START` and `CALC-END` markers.

Opened directly in a browser instead of through claude.ai, the page still works but saves quotes only in that browser.
