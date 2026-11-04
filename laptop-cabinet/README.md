# LC-60 laptop storage cabinet

Custom casework package for a client who needs to store 60 laptops (10" x 14" x 1-1/2", stacked no more than 5 high) in one lockable cabinet about 35" tall. Everything a fabricator needs to price it is in `out/`.

**Rev 1 (Nov 4, 2026):** four lockable doors moved into the base scope; carcass depth 16" to 18"; laptop stacks pushed toward the back (3" free in front, 1/2" behind).

## Design

| | |
|---|---|
| Overall | 49" W x 19" D x 35" H (18" carcass + 1" doors) |
| Layout | 4 columns x 3 tiers = 12 bays, 5 laptops each = **60 laptops** |
| Clear bay | 11" W x 9" H x 17-1/2" D (1/2" each side, 1-1/2" lift room above a stack, 3" in front, 1/2" behind) |
| Doors | 4, one per column, 1" TFM, all hinged left, 110° soft-close concealed hinges, cam locks keyed alike, 96 mm wire pulls |
| Panels | 1" sides, top, bottom deck, 2 fixed shelves, 9 dividers. 1/2" back in a rabbet |
| Base | 4" toe kick, recessed 3". First bay floor at 5" |
| Material | 1" particleboard with thermally fused laminate (TFM), 3 mm PVC edgeband |
| Weight | about 235 lb empty, 535 lb loaded |

Height stack-up: 4 base + 1 deck + 9 bay + 1 shelf + 9 bay + 1 shelf + 9 bay + 1 top = 35".
Width: 1 side + 4 x 11 bay + 3 x 1 divider + 1 side = 49".

## Files (`out/`)

| File | What it is |
|---|---|
| `LC-60_Drawing_Set.pdf` | 13 sheets, 11 x 17: cover and notes, front elevation (doors closed), interior elevation, section, side elevation, plans, loaded elevation, isometrics, exploded view, part details, door details, cut list, door swing plan, alternates and quote request |
| `LC-60_Cut_List.xlsx` | Cut list (with formulas), hardware, materials, alternates with a price column, design basis |
| `LC-60_Cut_List.csv` | Plain cut list |
| `LC-60_Drawings.dxf` | All views and part details at 1:1, inches, layered (OUTLINE, HIDDEN, CUT, DIM, EDGEBAND...) |
| `LC-60_Parts_CNC.dxf` | One flat outline of each part at 1:1 for nesting |
| `renders/*.png` | 3D renders |
| `sheets/*.png` | Sheet images |
| `viewer.html` | Interactive 3D viewer with the drawing set and cut list |

## Regenerating

All dimensions live in `src/geometry.py`. Change an input (bay size, panel thickness, base height) and rebuild:

```bash
cd laptop-cabinet/src && python3 build.py
```

Pass a path to `three.min.js` (r128) as the first argument to also refresh the 3D renders (needs Node with Playwright and Chromium). Requires `reportlab`, `Pillow`, `openpyxl` and `pdftoppm`.

## Open items to confirm with the client

1. Exact laptop model and size, with or without a protective case.
2. No charging inside the cabinet is assumed (ALT-1 ventilation / ALT-2 charging if that changes).
3. Door pull and lock finish.
4. Is 35" a hard maximum? Glides add about 3/8".
5. Against a wall, or freestanding with a finished back?
6. Laminate color and number of cabinets.
