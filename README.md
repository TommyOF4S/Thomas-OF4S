# Thomas-OF4S

## Devon quote builder

Devon Office Furniture isn't on CET, so we design cubicles in CET with **AIS Divi** and
translate the result into Devon's own calculator. This tool does the translation:

**CET bill of materials (AIS Divi) → filled-in Devon calculator (.xlsm) + review report**

### Hosted page (nothing to install)

**https://claude.ai/artifact/DoCnKnN2pD1asBzVaGtKuF**. It runs entirely in the browser:
drop the CET export, 2D plan image and notes, build, and download the filled Devon calculator
(`.xlsx`, Devon's formulas intact, macros removed), the review report and the crosswalk.

- An editor stores Devon's calculator once and everyone with access uses it. To update the
  prices, drop the new calculator on the page. Don't share the page by public link, because the
  stored calculator holds dealer pricing.
- **2D plan from CET as PDF**: the page reads every panel off the drawing and measures every
  joint. Two panels in a straight line (a break between two 180° panels) become a
  panel-to-panel connector (`HMP213`), 90° corners `HMA130`, three panels `HMA137`, four panels
  `HMC132`, and free ends `HMA128` finished ends. Colored dots marked on the plan become the
  matching high/low filler strips. These replace the AIS post counts. The plan is
  drawn beside the flags with a colored dot on every joint so you can check it, and the plan is
  cross-checked against the BOM (panel count, widths, posts) to catch mismatched revisions.
- **Fix mapping** on any flagged part saves a correction that's shared with the team and used
  on every later quote. It works like `mappings/overrides.csv`, but lives in the page.
- Source: `devon_quote/web/hosted.html` + `devon_quote/web/engine.js` (a JavaScript port of the
  Python engine). Rebuild with `python -m devon_quote.web.build_hosted` and republish
  `build/devon_quote_builder.html`. `tests/test_engine_parity.py` checks that the JS port and the
  Python package produce identical quotes, and `tests/test_plan.py` does the same for plan reading.
  They need Node with `jszip@3.10.1` and `pdfjs-dist@3.11.174` on `NODE_PATH`.

### Local drag-and-drop page

Double-click **`Devon Quote Builder.bat`** (Windows) or **`devon-quote-builder.command`** (Mac),
or run `python -m devon_quote serve`. A page opens in your browser:

1. Drop the CET export (`.sif`, or a `.csv`/`.xlsx` with part numbers and quantities).
2. Drop the 2D plan (PDF or image). It's shown next to the flagged items so you can check them.
3. Type notes, or click **Dictate** and talk (Chrome/Edge).
4. Fill in project, zip, grade, stations and delivery, then click **Build Devon quote**.

You get the estimated Devon total, everything that needs a look, and downloads for the filled
Devon calculator, the review report and the crosswalk. Copies are saved in `out/`. To swap in a
new Devon calculator, drop its `.xlsm` anywhere on the page. The page runs only on your computer
(127.0.0.1), and no files leave it.

### Command line

```
python -m devon_quote BOM.sif --project "Acme HQ" --ship-to 33010 \
    --stations 24 --delivery 4500 --notes dictation.txt --drawing plan.pdf
```

It writes three files to `out/`:

| File | What it is |
|---|---|
| `<project>_Devon_Quote.xlsm` | A copy of Devon's official calculator with every quantity, the fabric grade and the header filled in. Devon's formulas and macros are untouched, so it prices itself when opened, exactly like a calculator Devon sends. |
| `<project>_review.md` | Estimated Devon total, every line that needs a human check, unmapped parts, the AIS finishes to match, your notes, and the full Devon line list. |
| `<project>_crosswalk.csv` | Each AIS line next to the Devon part(s) it became. |

### Setup

1. `pip install -r requirements.txt` (Python 3.10+).
2. Put Devon's calculator in `templates/` (currently `DEVON_OFFICIAL_CALC_10.21.26.xlsm`).
   **It is git-ignored on purpose**: it holds dealer pricing and this repo is public.
   When Devon issues a new calculator, drop it in `templates/`. The newest file is used,
   and the price list is read straight from it.

### Inputs (command line)

- **BOM**: CET's SIF export (`.sif`) works best, because it carries finishes. A `.csv` or `.xlsx`
  with *Part Number* and *Qty* columns also works.
- **Options**: `--grade keystone|summit|aspen`, `--trim`, `--delivery` (Devon's freight estimate,
  default 0), `--stations` (for cost per station), `--description`.
- **2D plan / dictation**: `--drawing` and `--notes` are included in the review report so the
  checker has them next to the flagged items. They don't change quantities yet (see below).

### Reading the 2D plan

The 2D and the SIF are matched up, never added together. The SIF has no part for straight
panel-to-panel joints, so the 2D is the only source for Devon's panel-to-panel connectors. With a
2D plan, every connector and finished end comes from the plan, and the SIF's posts become a
cross-check (2-way posts = corners, 3-way = 3-way joints, end-of-run shrouds = free ends); any
mismatch is flagged in the review, not added. Saved corrections for posts and shrouds apply only to
quotes without a 2D.

Give the CET 2D exported as **PDF** (`--drawing plan.pdf`, or drop it on either page).
`devon_quote/plan.py` finds the panels (the thin, gray-filled outlines whose lengths match
standard panel widths at that drawing's scale, detected per page), groups panel ends that meet
into joints, and classifies each joint by how many panels meet and at what angle. Connectors
then come from the plan instead of the AIS post counts. Runs that end at a wall are counted as
finished ends, so swap those to wall starts (`HMA199`).

**Height changes from the panel labels.** Export the 2D with CET's panel labels showing: a
letter, then the height and width in inches (`A6660` = 66"H × 60"W). The letter only tells the
heights in one drawing apart (A, B, C...); the digits carry the height. Each label is matched to the
nearest panel of the width it names, so every joint knows the heights meeting there:

- each connector is quoted at the **tallest** panel height at its joint (a 2-way between a 66" and
  a 42" panel is a 67" `HMA130.67`);
- where heights differ, one high/low filler strip from each lower height up to the tallest
  (42" next to 66" → `HMHL3967`, using the Divi-to-Devon heights: 42→39, 50→53, 66→67, 82→85);
- a panel with no label takes its height from the BOM when the BOM has only one height in that
  width; otherwise it's flagged;
- the review flags labels that aren't next to a panel of their width, joints with three different
  heights, height changes Devon has no filler strip for (anything to 85"), and plan label sizes
  that don't match the BOM.

Labels need a PDF (the text is read directly); a PNG or JPG has no text to read.

**Marking height changes with dots.** For a PNG/JPG, or to override the labels, put a filled dot
on each joint where the height changes. Dots win over labels when both are there (the review says
if they disagree). The color picks the filler strip:

| Dot | Heights | Devon filler strip |
|---|---|---|
| Red | 39" to 53" | `HMHL3953` |
| Blue | 39" to 67" | `HMHL3967` |
| Yellow | 47" to 53" | `HMHL4753` |
| Green | 47" to 67" | `HMHL4767` |
| Purple | 53" to 67" | `HMHL5367` |

The joint keeps its normal connector; each dot adds one filler strip. 39" to 47" (`HMHL3947`)
has no color (the labels find it). A colored dot that isn't on a joint is flagged. If the BOM has
more than one panel height and the plan has neither labels nor dots, the review says so.

**Marking panel-to-panel connectors.** Draw a **pink dash** on each panel-to-panel joint. When
the plan has pink dashes, each marked joint is quoted as one panel-to-panel connector (`HMP213`),
instead of the measured straight-joint count; two strokes on the same joint count once. The review
flags straight joints with no dash, dashes on a corner, 3-way or 4-way joint (those joints keep
their own connector too), and dashes that aren't on a joint. Plans without pink dashes use the
measured straight joints.

**2D images (PNG/JPG) and picture-only PDFs.** The marks are read from the pixels: the page sorts
pixels into the mark colors, groups touching pixels, and keeps long thin pink shapes (dashes) and
round solid dot-sized shapes (dots) that sit on panel lines. It ignores letter holes in colored
callout boxes, dotted dimension lines, and the pinkish blurred edges of red lines. With marks but
no vector plan, each pink dash adds a panel-to-panel connector; colored dots add their filler
strips; every other connector (AIS 2-way posts as corners, 3-way, 4-way, ends) comes from the SIF. The hosted page lists every mark it found, numbered on the
plan, with a checkbox to untick anything that isn't a designer mark (such as a CET symbol).
`devon_quote/marks.py` and `imageMarks()` in `web/engine.js` are the same algorithm;
`tests/test_marks.py` checks they agree pixel for pixel.

(`HMA224` appears in Devon's calculator but isn't a real SKU; the tool never offers or quotes it.)

### How AIS parts become Devon parts

| AIS Divi | Devon |
|---|---|
| Panels `P-DL…HHWW` | `HM01.HHWW` at the Devon equivalent height: Divi 42H → 39H, 50H → 53H, 82H → 85H; any other height rounds **up** to Devon's 39/47/53/67/85. Powered panels become `.P4`. Glass panels become `HM51` (panel + 14" glass stacker). |
| Posts 2/3/4-way `P-DLPF*` | `HMA130` / `HMA137` / `HMC132` at that height. An AIS 2-way post is always a corner. |
| Straight joints | AIS lists nothing for them; Devon needs a panel-to-panel connector `HMP213` at each. Only the 2D shows them, so without one the review warns that none are quoted. |
| End-of-run shroud | `HMA128` finished end kit |
| Infeeds, duplex outlets, data plates | `BE-SDFD1`/`BE-ENDFD`, `BE-REC1-4`, `BE01439-C` |
| Electrical jumpers | not quoted (Devon P4 panels connect directly); flagged to add pass-thrus |
| Worksurfaces `W-WSDDWW` | `WSDDWW`. Sizes Devon doesn't make get the next size up plus `MIS-002` custom cut. |
| Cantilevers left/right, shared, flat plate, U-channel | Pairs = (AIS lefts + rights) ÷ 2, rounded up: `HMP225.22` (22") or `HMP165.16` (16") per depth; shared `HMP226`; `ACC-105`; `WPS-VC48` |
| Pedestals, laterals | `ECO-BBF-MT` / `ECO-FF-MT` / `ECO-MOB BF`, `G-LF230` |

Devon's no-charge fastener kits (`ACC-106/107/108`) and touch-up paint (`ACC-110`) are added
automatically.

**Teaching it**: add rows to `mappings/overrides.csv` (`ais_part,devon_part,ratio,note`;
wildcards allowed; leave `devon_part` blank for "nothing needed"). Overrides always win over
the built-in rules, so every correction you make once is reused on every future quote.

### Tests

```
python -m pytest -q
```

The tests need the Devon calculator in `templates/`. Without it, most of them skip.

### Next steps

- Use the 2D plan and dictation automatically, with Claude reading the drawing to settle the
  flagged items (straight vs. corner joints, wall starts, finished ends, pass-thrus).
- Load the full AIS Divi price list / catalog so every Divi part number is recognized.
- Check the output against past jobs that have both a CET file and Devon's actual quote.
