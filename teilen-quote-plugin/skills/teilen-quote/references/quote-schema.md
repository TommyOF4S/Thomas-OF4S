# Saved quote format

One document per quote in the app's `quotes` collection. The app reads exactly these fields. Lengths are decimal feet in `h` and `l`; `hText` and `lText` are what shows in the input box.

```json
{
  "number": "TN-2610-006",
  "status": "draft",
  "project": "Acme HQ 3rd floor",
  "site": "100 Main St, Miami, FL",
  "client": { "company": "Acme", "name": "Maria Lopez", "email": "", "phone": "" },
  "date": "2026-10-23",
  "validDays": 30,
  "preparedBy": "Thomas",
  "assumptions": { "laborRate": 50, "doorDeduction": 21, "shipping": 600 },
  "margin": 0.30,
  "taxRate": 0,
  "itemize": true,
  "notes": "",
  "internal": "Created by Claude from <where the dimensions came from>.",
  "walls": [
    {
      "id": "w1",
      "name": "Conference room A front",
      "model": "T109",
      "hText": "9'6\"", "h": 9.5,
      "lText": "14'", "l": 14,
      "qty": 1,
      "doors": [ { "code": "A1", "qty": 1 } ]
    }
  ],
  "frozen": null,
  "createdAt": 1792781091574,
  "updatedAt": 1792781091574,
  "source": "claude-skill"
}
```

Rules:

- `status` is one of `draft`, `sent`, `won`, `lost`. Always create as `draft`.
- `margin` and `taxRate` are fractions (0.30 is 30%).
- `itemize: true` shows installation as its own line on the customer quote. With `false`, install is folded into each wall.
- `createdAt` and `updatedAt` are epoch milliseconds. Use the current time.
- Wall `id`s must be unique within the quote.
- Leave `frozen` as `null`. The app locks prices itself when the status leaves Draft.
