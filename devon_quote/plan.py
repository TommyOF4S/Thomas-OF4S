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

Height changes can't be seen in a 2D, so the designer marks them on the CET plan: a red
dot on the joint and a label beside it with the two heights ("47/53", "47-53", "47 to 53").
Each mark becomes a change-of-height connector kit plus the matching high/low filler strip.

The same algorithm is ported to JavaScript in web/engine.js for the hosted page;
tests/test_plan.py checks both against tests/fixtures/sample_plan.pdf.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

STD_WIDTHS = (12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72)
PANEL_INCHES = 2.0  # drawn panel thickness
POST_GAP = 1.4  # inches between the drawn ends of two panels at a post
WIDTH_TOLERANCE = 1.5
JOIN_FACTOR = 2.0  # ends closer than this many panel thicknesses form one joint
KINDS = ("straight", "l", "tee", "cross", "ends", "angled", "other")
MARK_JOINT_FACTOR = 6.0  # a red dot within this many panel thicknesses of a joint marks it
MARK_LABEL_FACTOR = 60.0  # its label is the nearest height pair within this many thicknesses
MARK_MAX_FACTOR = 20.0  # dots bigger than this many thicknesses are not marks
HEIGHT_PAIR = re.compile(r"(\d{2})\s*(?:\"|in\.?|''|”)?\s*(?:/|-|–|to|>|→|x)\s*(\d{2})", re.I)


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
class Shape:
    """Any filled path (rectangle, circle, polygon): its bounding box and fill."""
    x0: float
    y0: float
    x1: float
    y1: float
    fill: tuple[float, float, float] | None


@dataclass
class Word:
    text: str
    x: float  # center
    y: float


@dataclass
class HeightChange:
    x: float
    y: float
    page: int
    joint: str | None  # kind of joint the dot sits on (None: not on a joint)
    heights: tuple[int, int] | None  # as written on the label, e.g. (47, 53)
    label: str


@dataclass
class PlanResult:
    counts: Counter = field(default_factory=Counter)  # straight, l, tee, cross, ends, angled, other
    widths: Counter = field(default_factory=Counter)  # nominal panel width -> count
    joints: list[Joint] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)  # per page: panels found, thickness
    height_changes: list[HeightChange] = field(default_factory=list)

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


def _is_red(fill) -> bool:
    return bool(fill) and fill[0] > 0.6 and fill[1] < 0.4 and fill[2] < 0.4


def height_marks(shapes: list[Shape], words: list[Word], joints: list[Joint], t: float, page: int) -> list[HeightChange]:
    """Red dots the designer put on joints where the panel height changes, with their labels."""
    labels = []
    for w in words:
        m = HEIGHT_PAIR.search(w.text)
        if m:
            labels.append((w, (int(m.group(1)), int(m.group(2)))))
    out = []
    for s in shapes:
        w, h = s.x1 - s.x0, s.y1 - s.y0
        if not _is_red(s.fill) or max(w, h) > MARK_MAX_FACTOR * t or min(w, h) <= 0 or not 0.5 <= w / h <= 2:
            continue
        x, y = (s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2
        near = min(joints, key=lambda j: math.hypot(j.x - x, j.y - y), default=None)
        joint = near.kind if near and math.hypot(near.x - x, near.y - y) <= MARK_JOINT_FACTOR * t else None
        lab = min(labels, key=lambda l: math.hypot(l[0].x - x, l[0].y - y), default=None)
        if lab and math.hypot(lab[0].x - x, lab[0].y - y) > MARK_LABEL_FACTOR * t:
            lab = None
        out.append(HeightChange(round(x, 2), round(y, 2), page, joint, lab[1] if lab else None, lab[0].text if lab else ""))
    return out


def analyze_rects(pages: list[list[Rect]], extras: list[tuple[list[Shape], list[Word]]] | None = None) -> PlanResult:
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
        if extras:
            shapes, words = extras[p]
            res.height_changes.extend(height_marks(shapes, words, js, t, p + 1))
    return res


def _rgb(obj):
    fill = obj.get("non_stroking_color") if obj.get("fill") else None
    if fill is None:
        return None
    if isinstance(fill, (int, float)):
        return (float(fill),) * 3
    if len(fill) == 1:
        return (float(fill[0]),) * 3
    if len(fill) == 3:
        return tuple(float(c) for c in fill)
    return None  # CMYK and patterns: not a CET panel fill


def read_pdf(path: str | Path) -> tuple[list[list[Rect]], list[tuple[list[Shape], list[Word]]]]:
    import pdfplumber

    pages, extras = [], []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append([Rect(r["x0"], r["top"], r["x1"], r["bottom"], _rgb(r)) for r in page.rects])
            shapes = [Shape(o["x0"], o["top"], o["x1"], o["bottom"], _rgb(o))
                      for o in list(page.rects) + list(page.curves) if o.get("fill")]
            words = [Word(w["text"], (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2)
                     for w in page.extract_words(keep_blank_chars=True)]
            extras.append((shapes, words))
    return pages, extras


def analyze_pdf(path: str | Path) -> PlanResult:
    return analyze_rects(*read_pdf(path))
