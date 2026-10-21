"""Read panel joints straight off a CET 2D plan exported as PDF.

CET draws each panel as a thin gray-filled outline (about 2" thick at drawing scale) and
leaves a small gap at each post. So the joints can be measured instead of guessed:

  * find the panels: the group of filled, neutral-gray, thin rectangles whose lengths
    match standard panel widths (24", 30", 36", 42", 48", 60", ...) at that thickness;
  * gather panel ends that sit within two panel-thicknesses of each other into a joint;
  * classify each joint by how many panels meet there and at what angle:
      2 in a straight line (180 degrees) -> panel-to-panel connector (Devon HMP213)
      2 at 90 degrees                    -> 2-way corner (HMA130)
      3                                  -> 3-way (HMA137)
      4                                  -> 4-way (HMC132)
      a lone end                         -> finished end (HMA128)

The same algorithm is ported to JavaScript in web/engine.js for the hosted page;
tests/test_plan.py checks both against tests/fixtures/sample_plan.pdf.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

STD_WIDTHS = (12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72)
PANEL_INCHES = 2.0  # drawn panel thickness
POST_GAP = 1.4  # inches between the drawn ends of two panels at a post
WIDTH_TOLERANCE = 1.5
JOIN_FACTOR = 2.0  # ends closer than this many panel thicknesses form one joint
KINDS = ("straight", "l", "tee", "cross", "ends", "angled", "other")


@dataclass
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float
    fill: tuple[float, float, float] | None  # None = not filled

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@dataclass
class Joint:
    kind: str
    x: float
    y: float
    page: int


@dataclass
class PlanResult:
    counts: Counter = field(default_factory=Counter)  # straight, l, tee, cross, ends, angled, other
    widths: Counter = field(default_factory=Counter)  # nominal panel width -> count
    joints: list[Joint] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)  # per page: panels found, thickness

    @property
    def panels(self) -> int:
        return sum(self.widths.values())


def _neutral_gray(fill) -> bool:
    if not fill:
        return False
    r, g, b = fill[:3]
    return max(r, g, b) - min(r, g, b) < 0.02 and 0.5 < r < 0.97


def nominal_width(length: float, thickness: float) -> int | None:
    implied = length / thickness * PANEL_INCHES + POST_GAP
    best = min(STD_WIDTHS, key=lambda s: abs(implied - s))
    return best if abs(implied - best) <= WIDTH_TOLERANCE else None


def find_panels(rects: list[Rect]) -> tuple[list[Rect], float | None]:
    """The panel rectangles on one page, and their drawn thickness."""
    groups: dict[tuple, list[Rect]] = defaultdict(list)
    for r in rects:
        t, length = min(r.w, r.h), max(r.w, r.h)
        if 0.05 <= t <= 5 and length >= 3 * t and _neutral_gray(r.fill):
            groups[(round(t, 2), tuple(round(c, 2) for c in r.fill[:3]))].append(r)
    best, best_fit = None, 0
    for key, rs in groups.items():
        fit = sum(1 for r in rs if nominal_width(max(r.w, r.h), key[0]))
        if fit >= 2 and fit / len(rs) >= 0.9 and fit > best_fit:
            best, best_fit = key, fit
    if best is None:
        return [], None
    t = best[0]
    return [r for r in groups[best] if nominal_width(max(r.w, r.h), t)], t


def joints_on_page(panels: list[Rect], thickness: float, page: int) -> list[Joint]:
    ends = []  # (x, y, unit direction pointing out of the panel, panel index)
    for i, r in enumerate(panels):
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        if r.w >= r.h:
            a, b = (r.x0, cy), (r.x1, cy)
        else:
            a, b = (cx, r.y0), (cx, r.y1)
        for e, o in ((a, b), (b, a)):
            dx, dy = e[0] - o[0], e[1] - o[1]
            n = math.hypot(dx, dy) or 1
            ends.append((e[0], e[1], dx / n, dy / n, i))

    parent = list(range(len(ends)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    tol = JOIN_FACTOR * thickness
    for i in range(len(ends)):
        for j in range(i + 1, len(ends)):
            if ends[i][4] != ends[j][4] and math.hypot(ends[i][0] - ends[j][0], ends[i][1] - ends[j][1]) <= tol:
                parent[find(i)] = find(j)

    groups: dict[int, list] = defaultdict(list)
    for i, e in enumerate(ends):
        groups[find(i)].append(e)

    out = []
    for g in sorted(groups.values(), key=lambda g: (round(g[0][1], 1), round(g[0][0], 1))):
        x = sum(e[0] for e in g) / len(g)
        y = sum(e[1] for e in g) / len(g)
        n = len(g)
        if n == 1:
            kind = "ends"
        elif n == 2:
            dot = g[0][2] * g[1][2] + g[0][3] * g[1][3]
            kind = "straight" if dot < -0.95 else "l" if abs(dot) < 0.15 else "angled"
        elif n == 3:
            kind = "tee"
        elif n == 4:
            kind = "cross"
        else:
            kind = "other"
        out.append(Joint(kind, round(x, 2), round(y, 2), page))
    return out


def analyze_rects(pages: list[list[Rect]]) -> PlanResult:
    res = PlanResult()
    for p, rects in enumerate(pages):
        panels, t = find_panels(rects)
        res.pages.append({"page": p + 1, "panels": len(panels), "thickness": t})
        if not panels:
            continue
        for r in panels:
            res.widths[nominal_width(max(r.w, r.h), t)] += 1
        js = joints_on_page(panels, t, p + 1)
        res.joints.extend(js)
        res.counts.update(j.kind for j in js)
    return res


def pdf_rects(path: str | Path) -> list[list[Rect]]:
    import pdfplumber

    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            rects = []
            for r in page.rects:
                fill = r.get("non_stroking_color") if r.get("fill") else None
                if fill is not None:
                    if isinstance(fill, (int, float)):
                        fill = (float(fill),) * 3
                    elif len(fill) == 1:
                        fill = (float(fill[0]),) * 3
                    elif len(fill) == 3:
                        fill = tuple(float(c) for c in fill)
                    else:
                        fill = None  # CMYK and patterns: not a CET panel fill
                rects.append(Rect(r["x0"], r["top"], r["x1"], r["bottom"], fill))
            pages.append(rects)
    return pages


def analyze_pdf(path: str | Path) -> PlanResult:
    return analyze_rects(pdf_rects(path))
