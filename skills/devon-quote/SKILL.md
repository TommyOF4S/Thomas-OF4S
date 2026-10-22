---
name: devon-quote
description: Turn an AIS Divi cubicle design from CET (the SIF bill of materials, plus the 2D plan as a PDF) into a filled-in Devon Office Furniture quote, using Devon's own calculator (.xlsm). Use this whenever someone wants a Devon quote, Devon pricing, or a Devon calc filled in from an AIS / Divi / CET design or SIF file, asks how many Devon panel-to-panel connectors, high/low filler strips or connectors a layout needs, wants to cross an AIS part over to Devon, or wants a Devon freight/delivery estimate, even if they don't say "skill" or name the files.
---

# Devon quote from an AIS Divi design

OF4S designs cubicles in CET with AIS Divi parts, but Devon isn't in CET, so every Devon quote has to be
rebuilt by hand. This skill does that crossover: it reads the CET SIF and 2D plan, maps each AIS part to
its Devon equivalent, counts the connectors the SIF can't show, and fills in Devon's official calculator so
Devon's own formulas price it. The bundled code is the same engine as the OF4S hosted quote builder page.

## What to collect

1. **The SIF** (`.sif` export from CET; a `.csv`/`.xlsx` with part numbers and quantities also works). Required.
2. **Devon's calculator**, the `.xlsm` Devon sends (named like `DEVON_OFFICIAL_CALC_10.21.26.xlsm`). Required:
   all pricing comes from it, and it is not bundled with this skill because it holds Devon's dealer pricing.
   If the user hasn't attached it, ask for it. Don't price from memory or from an old quote.
3. **The 2D plan exported from CET as a PDF, with panel labels on** (labels like `A6660` = 66"H x 60"W).
   Strongly recommended. The AIS SIF never lists straight panel-to-panel joints, so without the 2D the quote
   has no Devon panel-to-panel connectors (HMP213); the PDF also gives each joint's panel heights, which
   decide the high/low filler strips and connector heights. A PNG/JPG 2D only works if the designer drew
   pink dashes (panel-to-panel joints) and colored dots (height changes) on it.
4. **Quote details**, asked for together in one question when missing: project name, ship-to zip, fabric grade
   (Keystone, Summit or Aspen; default Keystone), number of workstations (for cost per station), and the
   delivery amount if Devon already gave one.
5. **50"H AIS panels**: they can be quoted as Devon **53"H or 47"H**. If the SIF has 50" panels (part numbers
   like `P-DL…50WW`) and the user hasn't said which, ask; default 53.

## Run it

The code is in `scripts/` next to this file. It needs Python 3.10+ with `openpyxl`, `pdfplumber`, `numpy`
and `pillow`; check with `python3 -c "import openpyxl, pdfplumber, numpy, PIL"` and `pip install` what's
missing.

```bash
cd <this skill's folder>/scripts
python3 -m devon_quote "<path to SIF>" \
  --template "<path to Devon calculator .xlsm>" \
  --drawing "<path to 2D plan .pdf>"   \
  --project "Acme HQ" --ship-to 33010 --grade keystone --stations 24 \
  --divi50 53 \
  -o "<output folder>"
```

- Repeat `--drawing` for several plan files. Leave it out only if there's no 2D at all.
- Leave out `--delivery` to have delivery estimated from the order weight ($445 + $0.27/lb, fitted to past
  Devon quotes to OF4S); pass `--delivery 1200` to use Devon's number, or `--delivery 0` for a pickup.
- Pick an output folder the user can open (their working directory or an `outputs/` folder), not a temp dir.

It writes three files and prints a summary:
- `<project>_Devon_Quote.xlsm`: Devon's calculator with the quantities filled in. It recalculates when opened
  in Excel or Google Sheets. This is the deliverable.
- `<project>_review.md`: the estimated total, connectors read from the plan, every flag, and the line items.
- `<project>_crosswalk.csv`: each AIS line and the Devon part(s) it became.

## Tell the user

Read the review file, then give a short answer:
- the estimated Devon total (product net + surcharge + delivery) and cost per station, saying when delivery
  is an estimate;
- what the 2D supplied (panel-to-panel connectors, filler strips, corners, 3-way and 4-way connectors);
- **every flag**: warnings, unmapped AIS parts (not in the quote yet) and "to confirm" lines, each in plain
  words with what to check. Don't bury these; they're the reason a person reviews the quote;
- the three files, with the calculator first.

If something looks off (the plan and SIF disagree, a part is unmapped), say what you'd check rather than
guessing a fix. `references/rules.md` explains how every part is mapped and counted; read it when the user
asks why a number came out as it did, or before suggesting a change.

## Corrections

OF4S's standing corrections are already built in (`scripts/mappings/overrides.csv`, e.g. AIS `A-PPDV` power
pole → `BE-PP12`, `E-MW8W4PJ36E` jumper → `BE-36JU`, BBF pedestals → `ECO-BBF-MT`) and apply to every quote
automatically. When the user says an AIS part should map to a different Devon part, don't edit the skill. Copy
`scripts/mappings/overrides.csv` to the output folder, add a row (`ais_part,devon_part,ratio,note`;
wildcards like `E-MW8W4*` work; a blank `devon_part` means "nothing on the Devon side"), and rerun with
`--overrides <that copy>`. Suggest they send lasting corrections to Thomas so the shared skill gets them.
