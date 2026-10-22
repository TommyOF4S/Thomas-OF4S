"""Write the review report (Markdown) and the AIS -> Devon crosswalk (CSV)."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .bom import BomLine
from .catalog import GRADES, Catalog
from .mapper import MapResult
from .pricing import Estimate


def _money(x: float) -> str:
    return f"${x:,.2f}"


def finishes(lines: list[BomLine]) -> list[tuple[str, str, float]]:
    """AIS finish selections (fabric, paint, laminate) with how many items use each."""
    seen: Counter = Counter()
    for ln in lines:
        for o in ln.options:
            g, d = o.group, o.description
            if not g or not d or d.lower().startswith(("grade", "no ", "(fabric", "insert laminates", "divi insert")):
                continue
            if any(k in g.lower() for k in ("fabric", "paint", "laminate", "trim", "edge", "glass", "color")):
                seen[(g, d)] += ln.qty
    return [(g, d, q) for (g, d), q in sorted(seen.items())]


def write_crosswalk(path: Path, result: MapResult) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ais_part", "ais_description", "ais_qty", "tag", "devon_part", "devon_qty", "status", "note"])
        for m in result.mappings:
            s = m.source
            if not m.targets:
                w.writerow([s.part, s.description, f"{s.qty:g}", s.tag, "", "", m.status, m.note])
            for part, ratio in m.targets:
                w.writerow([s.part, s.description, f"{s.qty:g}", s.tag, part, f"{s.qty * ratio:g}", m.status, m.note])


def write_report(
    path: Path,
    *,
    project: str,
    bom_file: str,
    quote_file: str,
    catalog: Catalog,
    grade: int,
    lines: list[BomLine],
    result: MapResult,
    est: Estimate,
    notes: str = "",
    drawings: list[str] | None = None,
) -> None:
    out: list[str] = []
    w = out.append
    w(f"# Devon quote review · {project or 'untitled project'}\n")
    w(f"- AIS bill of materials: `{bom_file}` ({len(lines)} lines, {sum(l.qty for l in lines):g} pieces)")
    w(f"- Devon calculator filled in: `{quote_file}`")
    w(f"- Price list: {catalog.title} · fabric grade {GRADES[grade]} · net = list × {catalog.net_multiplier:g}")
    if drawings:
        w(f"- 2D plan(s) for checking: " + ", ".join(f"`{d}`" for d in drawings))
    w("")

    w("## Estimated Devon cost\n")
    w("| | |\n|---|---:|")
    w(f"| List | {_money(est.list_total)} |")
    w(f"| Product net | {_money(est.product_net)} |")
    w(f"| Surcharge ({catalog.surcharge_rate:.0%}) | {_money(est.surcharge)} |")
    if est.delivery_auto:
        w(f"| Delivery (estimated from {est.weight:,.0f} lbs: $445 + $0.27/lb; Devon confirms) | {_money(est.delivery)} |")
    else:
        w(f"| Delivery (estimate) | {_money(est.delivery)} |")
    w(f"| **Total** | **{_money(est.total)}** |")
    if est.per_station:
        w(f"| Per station ({est.stations}) | {_money(est.per_station)} |")
    w(f"| Weight (approx.) | {est.weight:,.0f} lbs |\n")
    w("These totals are this tool's own math. The calculator recalculates its own figures when you open it, and the two should match.\n")

    review, unmapped = result.review, result.unmapped
    w(f"## Needs your attention ({len(unmapped)} unmapped, {len(review)} to confirm)\n")
    if result.warnings:
        for x in result.warnings:
            w(f"- ⚠️ {x}")
        w("")
    if unmapped:
        w("### Unmapped: not in the Devon quote yet\n")
        w("Add these by hand, or teach the tool by adding a row to `mappings/overrides.csv`.\n")
        w("| AIS part | Description | Qty | Why |\n|---|---|---:|---|")
        for m in unmapped:
            w(f"| {m.source.part} | {m.source.description} | {m.source.qty:g} | {m.note} |")
        w("")
    if review:
        w("### Mapped: please confirm\n")
        w("| AIS part | Qty | → Devon | Check |\n|---|---:|---|---|")
        for m in review:
            tgt = ", ".join(p for p, _ in m.targets) or "—"
            w(f"| {m.source.part} | {m.source.qty:g} | {tgt} | {m.note} |")
        w("")
    if not unmapped and not review and not result.warnings:
        w("Nothing flagged.\n")

    if result.plan is not None:
        w("## Connectors from the 2D plan\n")
        w(f"Read {result.plan.panels} panels off the plan and measured every joint. These replace the AIS post counts.\n")
        if result.plan.pink_dashes:
            w("Panel-to-panel connectors are counted from the pink dashes drawn on the plan, one per marked joint.\n")
        tags = Counter(l.text for l in result.plan.labels if l.matched)
        if tags:
            w(f"Panel heights come from the CET panel labels ({sum(tags.values())} of {result.plan.panels} panels labeled: "
              + ", ".join(f"{t} x {n}" for t, n in sorted(tags.items())) + "). Each connector is quoted at the tallest "
              "panel at its joint; where heights change, a high/low filler strip covers the step.\n")
        w("| Joint on the plan | Qty | Devon part |\n|---|---:|---|")
        labels = {"straight": "Two panels in a straight line (180°)", "pink": "Panel-to-panel joint (pink dash on the plan)", "l": "Corner, two panels at 90°",
                  "tee": "Three panels", "cross": "Four panels", "ends": "Free end of a run",
                  "filler": "Height change (panel labels): high/low filler strip" if result.height_points
                  else "Height change (colored dot): high/low filler strip"}
        for kind, part, qty in result.plan_parts:
            w(f"| {labels[kind]} | {qty} | {part} |")
        w("")
        w("Free ends are quoted as finished ends. Swap any that stop at a wall to a wall start (HMA199).\n")

    if result.marks is not None:
        mk = result.marks
        dots = ", ".join(f"{n} {color}" for color, n in mk.dots.items()) or "none"
        w("## Marks read from the 2D\n")
        w(f"Pink dashes (panel-to-panel): {mk.pink} · colored dots (filler strips): {dots}\n")
        if result.plan is None:
            w("The AIS SIF doesn't list straight joints, so each pink dash adds a panel-to-panel connector. "
              "AIS 2-way posts are quoted as corners.\n")
            w("| From the 2D | Qty | Devon part |\n|---|---:|---|")
            labels = {"pink": "Pink dash: panel-to-panel connector", "filler": "Colored dot: high/low filler strip"}
            for kind, part, qty in result.plan_parts:
                w(f"| {labels[kind]} | {qty} | {part} |")
            w("")

    fin = finishes(lines)
    if fin:
        w("## AIS finishes in the design\n")
        w("Pick the matching Devon trim, fabric and worksurface colors. The calculator's TRIM field is currently "
          "left as the template value.\n")
        w("| Option | Selection | Pieces |\n|---|---|---:|")
        for g, d, q in fin:
            w(f"| {g} | {d} | {q:g} |")
        w("")

    if notes.strip():
        w("## Design notes / dictation\n")
        w(notes.strip() + "\n")

    w("## Devon line items\n")
    w("| Devon part | Description | Qty | Net ea | Net ext | From AIS |\n|---|---|---:|---:|---:|---|")
    auto = {p for p, _, _ in result.auto_added}
    for l in est.lines:
        src = ", ".join(result.sources.get(l.part, [])) or ("auto-added" if l.part in auto else "")
        w(f"| {l.part} | {l.description} | {l.qty} | {_money(l.net_each)} | {_money(l.net_ext)} | {src} |")
    w("")
    if result.auto_added:
        w("Auto-added: " + "; ".join(f"{p} ×{q} ({why})" for p, q, why in result.auto_added) + "\n")

    path.write_text("\n".join(out), encoding="utf-8")
