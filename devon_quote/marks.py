"""Find the designer's marks in a 2D image (PNG/JPG, or a PDF page without vector panels).

Designers mark the CET 2D before exporting it:
  * a pink dash on each panel-to-panel joint (Devon HMP213);
  * a colored dot where the panel height changes; the color picks the high/low filler strip
    (plan.DOT_COLORS: red 3953, blue 3967, yellow 4753, green 4767, purple 5367).

Pixels are sorted into those colors, touching pixels of one color are grouped, and each group
is judged by shape: a long thin pink group is a dash, a round solid group of dot size is a dot.
Groups are dropped when they are part of a bigger patch of the same color (the hole of a letter in
a yellow callout), a chain of equal dots (a dotted dimension line), or the pinkish blurred edge of
something red. A mark must sit on the drawing (panel lines around it) to count.

This is the same algorithm as imageMarks() in web/engine.js; tests/test_marks.py checks they
agree pixel for pixel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MARK_CLASSES = (None, "pink", "red", "blue", "yellow", "green", "purple")
MAX_SIDE = 4000  # larger images are scaled down first


def _round(v: float) -> int:
    """JavaScript Math.round (halves round up), so both implementations agree."""
    return math.floor(v + 0.5)


@dataclass
class Mark:
    kind: str  # "dash" or "dot"
    color: str
    x: float
    y: float
    size: float
    on_panel: bool


@dataclass
class ImageMarks:
    dashes: list[Mark] = field(default_factory=list)
    dots: list[Mark] = field(default_factory=list)
    width: int = 0
    height: int = 0
    source: str = ""


def classify(rgb: np.ndarray) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(np.int32) for i in range(3))
    cls = np.zeros(r.shape, np.uint8)
    # order matters only where tests overlap; same order as pixelClass() in engine.js
    rules = [
        (1, (r > 204) & (b > 115) & (g < 204) & (r - g > 51)),
        (2, (r > 153) & (g < 102) & (b < 102)),
        (3, (b > 128) & (r < 102) & (g < 128)),
        (4, (r > 153) & (g > 153) & (b < 102)),
        (5, (g > 115) & (r < 102) & (b < 102)),
        (6, (r > 101) & (r < 205) & (g < 80) & (b > 115)),
    ]
    for value, mask in reversed(rules):
        cls[mask] = value
    return cls


def image_marks(rgba: np.ndarray) -> ImageMarks:
    """rgba: H x W x 4 uint8 array."""
    H, W = rgba.shape[:2]
    L = max(W, H)
    d_min = max(6, _round(0.004 * L))
    d_max = max(d_min + 1, _round(0.04 * L))
    len_min, len_max = d_min, max(d_min + 1, _round(0.08 * L))

    a = rgba[..., 3].astype(np.int32)
    w = 255 * (255 - a)
    rgb = np.stack([(rgba[..., i].astype(np.int32) * a + w) // 255 for i in range(3)], axis=-1)
    cls = classify(rgb)
    mx_, mn_ = rgb.max(axis=-1), rgb.min(axis=-1)
    ink = ((mx_ < 235) & (mx_ - mn_ < 30)).astype(np.int64)
    S = np.zeros((H + 1, W + 1), np.float64)
    S[1:, 1:] = ink.cumsum(0).cumsum(1)

    def ink_in(x0, y0, x1, y1):
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W - 1, x1), min(H - 1, y1)
        if x1 < x0 or y1 < y0:
            return 0.0, 0
        total = S[y1 + 1, x1 + 1] - S[y0, x1 + 1] - S[y1 + 1, x0] + S[y0, x0]
        return float(total), (x1 - x0 + 1) * (y1 - y0 + 1)

    flat_cls = cls.ravel().tolist()
    flat_ink = ink.ravel().tolist()
    seen = bytearray(W * H)
    comps = []
    for i0 in np.flatnonzero(cls).tolist():  # index order, like the JS scan
        if seen[i0]:
            continue
        c = flat_cls[i0]
        stack = [i0]
        seen[i0] = 1
        n = 0
        minx, maxx, miny, maxy = W, -1, H, -1
        sx = sy = sxx = syy = sxy = 0
        dark_own = red_next = 0
        while stack:
            i = stack.pop()
            y, x = divmod(i, W)
            n += 1
            sx += x
            sy += y
            sxx += x * x
            syy += y * y
            sxy += x * y
            dark_own += flat_ink[i]
            if x < minx:
                minx = x
            if x > maxx:
                maxx = x
            if y < miny:
                miny = y
            if y > maxy:
                maxy = y
            for dy in (-1, 0, 1):
                yy = y + dy
                if yy < 0 or yy >= H:
                    continue
                for dx in (-1, 0, 1):
                    xx = x + dx
                    if xx < 0 or xx >= W or (dx == 0 and dy == 0):
                        continue
                    j = yy * W + xx
                    if not seen[j] and flat_cls[j] == c:
                        seen[j] = 1
                        stack.append(j)
                    elif c == 1 and flat_cls[j] == 2:
                        red_next += 1
        bw, bh = maxx - minx + 1, maxy - miny + 1
        if max(bw, bh) < min(d_min, len_min) or max(bw, bh) > max(d_max, len_max) * 1.5:
            continue
        mx, my = sx / n, sy / n
        cxx = sxx / n - mx * mx + 1 / 12
        cyy = syy / n - my * my + 1 / 12
        cxy = sxy / n - mx * my
        tr, det = cxx + cyy, cxx * cyy - cxy * cxy
        disc = math.sqrt(max(0.0, tr * tr / 4 - det))
        l1, l2 = tr / 2 + disc, max(tr / 2 - disc, 1e-9)
        if c == 1 and red_next > 0.2 * n:
            continue
        comps.append(dict(c=c, n=n, bw=bw, bh=bh, mx=mx, my=my, elong=math.sqrt(l1 / l2),
                          length=math.sqrt(12 * l1), fill=n / (bw * bh), dark_own=dark_own))

    dashes, dots = [], []
    for k in comps:
        if k["c"] == 1:
            if k["elong"] >= 1.8 and len_min <= k["length"] <= len_max:
                dashes.append(dict(kind="dash", color="pink", x=k["mx"], y=k["my"], size=k["length"],
                                   dark_own=k["dark_own"], n=k["n"]))
        else:
            size = max(k["bw"], k["bh"])
            round_ = k["elong"] <= 1.6 and k["fill"] >= 0.6
            if round_ and d_min <= size <= d_max:
                dots.append(dict(kind="dot", color=MARK_CLASSES[k["c"]], x=k["mx"], y=k["my"], size=size,
                                 dark_own=k["dark_own"], n=k["n"]))

    # Dotted lines (dimension leaders) are chains of look-alike dots: group dots of one color and
    # similar size that sit within three sizes of each other; a group of three or more is a line.
    parent = list(range(len(dots)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a_ in enumerate(dots):
        for j in range(i + 1, len(dots)):
            b_ = dots[j]
            if b_["color"] != a_["color"]:
                continue
            ratio = b_["size"] / a_["size"]
            if ratio < 0.7 or ratio > 1.43:
                continue
            if math.hypot(b_["x"] - a_["x"], b_["y"] - a_["y"]) <= 3 * max(a_["size"], b_["size"]):
                parent[find(i)] = find(j)
    group_size = {}
    for i in range(len(dots)):
        group_size[find(i)] = group_size.get(find(i), 0) + 1
    chained = {i for i in range(len(dots)) if group_size[find(i)] >= 3}

    def embedded(m, c):
        R, cx, cy = _round(1.5 * m["size"]), _round(m["x"]), _round(m["y"])
        y0, y1, x0, x1 = max(0, cy - R), min(H - 1, cy + R), max(0, cx - R), min(W - 1, cx + R)
        box = cls[y0:y1 + 1, x0:x1 + 1]
        area = box.size
        same = int((box == c).sum())
        return (same - m["n"]) / max(1, area - m["n"]) >= 0.15

    kept = [m for i, m in enumerate(dots) if i not in chained and not embedded(m, MARK_CLASSES.index(m["color"]))]
    kept_dashes = [m for m in dashes if not embedded(m, 1)]

    def out(m):
        R = _round(1.5 * m["size"])
        d, area = ink_in(_round(m["x"]) - R, _round(m["y"]) - R, _round(m["x"]) + R, _round(m["y"]) + R)
        on_panel = (d - m["dark_own"]) / area >= 0.05
        r10 = lambda v: _round(v * 10) / 10
        return Mark(m["kind"], m["color"], r10(m["x"]), r10(m["y"]), r10(m["size"]), on_panel)

    return ImageMarks([out(m) for m in kept_dashes], [out(m) for m in kept], W, H)


def _fit(img):
    from PIL import Image

    img = img.convert("RGBA")
    if max(img.size) > MAX_SIDE:
        s = MAX_SIDE / max(img.size)
        img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    return np.asarray(img)


def read_marks(path: str | Path) -> list[ImageMarks]:
    """Marks in an image file, or in each page of a PDF rendered to an image."""
    path = Path(path)
    out = []
    if path.suffix.lower() == ".pdf":
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages[:20]):
                scale = min(4.0, MAX_SIDE / max(page.width, page.height))
                img = page.to_image(resolution=72 * scale).original
                res = image_marks(_fit(img))
                res.source = f"{path.name} p{i + 1}"
                out.append(res)
    else:
        from PIL import Image

        with Image.open(path) as img:
            res = image_marks(_fit(img))
        res.source = path.name
        out.append(res)
    return out


@dataclass
class MarksSummary:
    pink: int = 0
    dots: dict[str, int] = field(default_factory=dict)
    off_panel: int = 0
    images: list[ImageMarks] = field(default_factory=list)

    @property
    def any(self) -> bool:
        return bool(self.pink or self.dots)


def summarize(images: list[ImageMarks]) -> MarksSummary:
    s = MarksSummary(images=images)
    for im in images:
        for d in im.dashes:
            if d.on_panel:
                s.pink += 1
            else:
                s.off_panel += 1
        for d in im.dots:
            if d.on_panel:
                s.dots[d.color] = s.dots.get(d.color, 0) + 1
            else:
                s.off_panel += 1
    return s
