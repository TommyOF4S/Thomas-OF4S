# How the Devon quote is built

Everything here is what the bundled code does; it matches the OF4S hosted quote builder.

## Matching the SIF and the 2D, never adding them

The SIF and the 2D describe the same design, so they are matched up, not summed. With a 2D plan (PDF):

- every connector and finished end comes from the joints measured on the plan;
- the SIF's posts become a cross-check: AIS 2-way posts = plan corners, 3-way posts = plan 3-way joints,
  4-way posts (`P-DLPF4…`) = plan 4-way joints, end-of-run shrouds (`P-DLSEOR`) = plan free ends.
  A mismatch is flagged ("make sure the plan and the BOM are the same revision"), never added on top;
- saved corrections for posts and shrouds only apply when there's no 2D.

## Connectors

| On the plan / in the SIF | Devon part |
|---|---|
| Two panels in a straight line (180°). AIS lists nothing for these, so only the 2D shows them | `HMP213` panel-to-panel |
| Corner (2 panels at 90°); AIS 2-way post `P-DLPF2…` / `P-DLPFPP2…` (always a corner) | `HMA130` 2-way |
| 3 panels; AIS `P-DLPF3…` / `P-DLPFPP3…` | `HMA137` 3-way |
| 4 panels; AIS `P-DLPF4…` | `HMC132` 4-way |
| Free end of a run; AIS `P-DLSEOR` | `HMA128` finished end (swap to `HMA199` wall start where it meets a wall) |

Devon connector size codes by height: code A (`HMA130`, `HMA137`, `HMA128`) uses 39/47/53/67/85; code B
(`HMP213`, `HMC132`, `HMA199`) uses 34/42/48/62/80 for the same heights.

Without any 2D: AIS posts map one-for-one as above, and the review warns that no panel-to-panel connectors
are quoted, since the SIF can't show straight joints.

## Heights

Divi panel heights become Devon heights: 42 → 39, **50 → 53 or 47 (chosen per quote)**, 66 → 67 (rounds up),
82 → 85. Any other height rounds up to the next Devon height (39/47/53/67/85) and is flagged if the step is
over 6". Posts and connectors follow the panel heights.

## Height changes (high/low filler strips)

CET's panel labels in the 2D PDF (`A6660` = 66"H x 60"W; the letter only tells the heights in that drawing
apart) are matched to the nearest panel of the width they name. At a joint where panels of different heights
meet:
- the connector is quoted at the **taller** height (a 2-way between a 66" and a 39" panel is `HMA130.67`);
- one filler strip goes from each lower height up to the tallest, e.g. 39" next to 67" = `HMHL3967`.
  Devon's strips: `HMHL3947`, `HMHL3953`, `HMHL3967`, `HMHL4753`, `HMHL4767`, `HMHL5367` (none to 85").
A panel with no label takes its height from the SIF when the SIF has only one height in that width;
otherwise it's flagged. Colored dots drawn on the 2D (red 3953, blue 3967, yellow 4753, green 4767, purple
5367) override the labels.

## Other parts

- Panels `P-DL…HHWW` → `HM01.HHWW` at the Devon height; powered panels → `.P4`; quarter-glass panels → `HM51`.
- Worksurfaces, supports, pedestals and electrical have their own rules; `HMA224` in Devon's calculator is not
  a real SKU and is never used.
- Cantilevers: AIS sells lefts and rights, Devon sells pairs: pairs = (lefts + rights) / 2, rounded up.
- Devon's no-charge hardware kits (ACC-106/107/108/110) are added automatically.

## Standing corrections

`scripts/mappings/overrides.csv` holds OF4S's saved part mappings; they win over the built-in rules (except
that posts and shrouds come from the 2D plan when there is one). Current ones: `A-PPDV` → `BE-PP12`,
`E-MW8W4PJ30E` → `BE-30JU`, `E-MW8W4PJ36E` → `BE-36JU`, `E-UN8W4BIFL` → `BE-ENDFD`, `S-GPEDBBFS24` and
`S-PEDBBFJ24` → `ECO-BBF-MT`, `W-WSCC2436` → `WSC2436`, `WPS-SSSAR` → nothing, and three post fillers that
match the built-in rule (`P-DLPF266` → `HMA130.67`, `P-DLPFPP242` → `HMA130.39`, `P-DLPFPP342` → `HMA137.39`).

## Delivery

Left blank, delivery = **$445 + $0.27 per pound** of the order weight, rounded to $5. Fitted to 25 Devon
quotes to OF4S (all shipping to 33010, Aug 2024 – Oct 2026): it explains 96% of the variation and is usually
within about $110; mid-size orders vary most because Devon's numbers are carrier quotes. Devon confirms the
real figure; far-away, liftgate or inside deliveries will run higher.
