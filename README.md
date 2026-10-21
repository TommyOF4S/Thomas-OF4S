# Thomas-OF4S

## Devon quote builder

Devon Office Furniture isn't on CET, so we design cubicles in CET with **AIS Divi** and
translate the result into Devon's own calculator. This tool does the translation:

**CET bill of materials (AIS Divi) → filled-in Devon calculator (.xlsm) + review report**

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

### Inputs

- **BOM**: CET's SIF export (`.sif`) works best, because it carries finishes. A `.csv` or `.xlsx`
  with *Part Number* and *Qty* columns also works.
- **Options**: `--grade keystone|summit|aspen`, `--trim`, `--delivery` (Devon's freight estimate,
  default 0), `--stations` (for cost per station), `--description`.
- **2D plan / dictation**: `--drawing` and `--notes` are included in the review report so the
  checker has them next to the flagged items. They don't change quantities yet (see below).

### How AIS parts become Devon parts

| AIS Divi | Devon |
|---|---|
| Panels `P-DL…HHWW` | `HM01.HHWW` with the height rounded **up** to Devon's 39/47/53/67/85 (50H → 53H). Powered panels become `.P4`. Glass panels become `HM51` (panel + 14" glass stacker). |
| Posts 2/3/4-way `P-DLPF*` | `HMA130` / `HMA137` / `HMC132` at that height. 2-way is flagged, because straight runs use `HMP213`. |
| End-of-run shroud | `HMA128` finished end kit |
| Infeeds, duplex outlets, data plates | `BE-SDFD1`/`BE-ENDFD`, `BE-REC1-4`, `BE01439-C` |
| Electrical jumpers | not quoted (Devon P4 panels connect directly); flagged to add pass-thrus |
| Worksurfaces `W-WSDDWW` | `WSDDWW`. Sizes Devon doesn't make get the next size up plus `MIS-002` custom cut. |
| Cantilevers L+R / shared, flat plate, U-channel | `HMP225.22` pairs / `HMP226.22`, `ACC-105`, `WPS-VC48` |
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
