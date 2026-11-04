"""LC-60 drawing set: PDF (11x17 sheets) + DXF, generated from geometry.py.

Views are recorded once in model inches and rendered to both PDF (scaled) and DXF (1:1).
"""
import datetime
import os

from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle

import geometry as g
from geometry import fmt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
FONTS = os.path.join(ROOT, "fonts")
OUT = os.path.join(ROOT, "out")
RENDERS = os.path.join(OUT, "renders")

PROJECT = "LC-60 laptop storage cabinet"
CLIENT = "To be confirmed"
DATE = "Nov 4, 2026"
REV = "0 · Issued for pricing"

# ------------------------------------------------------------------ brand
INK = HexColor("#1a1814")
STONE = HexColor("#7a7468")
STONE6 = HexColor("#555047")
NAVY = HexColor("#2d4a6e")
NAVY5 = HexColor("#466489")
NAVY8 = HexColor("#15273f")
NAVY1 = HexColor("#dde5ee")
PAPER1 = HexColor("#f3efe7")
PAPER2 = HexColor("#e8e2d4")
PAPER3 = HexColor("#d6cfbe")
WHITE = HexColor("#ffffff")

for name, file in [("Geist", "Geist_wght_400.ttf"), ("GeistSB", "Geist_wght_600.ttf"),
                   ("Mono", "Geist_Mono_wght_400.ttf"), ("MonoM", "Geist_Mono_wght_500.ttf"),
                   ("Disp", "Schibsted_Grotesk_wght_700.ttf"), ("DispSB", "Schibsted_Grotesk_wght_600.ttf")]:
    pdfmetrics.registerFont(TTFont(name, os.path.join(FONTS, file)))

PW, PH = 17 * 72, 11 * 72
M = 36                      # sheet margin
TB_W = 184                  # title block width (right strip)
AREA_R = PW - M - TB_W - 10  # right edge of drawing area

STYLES = {  # width, color, dash
    "obj": (0.85, INK, None),
    "thin": (0.4, INK, None),
    "dim": (0.3, INK, None),
    "tick": (0.9, INK, None),
    "hidden": (0.5, INK, [3, 2]),
    "center": (0.35, STONE, [10, 2, 2, 2]),
    "phantom": (0.6, NAVY, [6, 1.5, 1.5, 1.5, 1.5, 1.5]),
    "cut": (1.3, INK, None),
    "cutline": (1.0, NAVY, [12, 2, 3, 2]),
    "eb": (2.6, NAVY, None),
    "floor": (1.1, INK, None),
    "lead": (0.45, NAVY, None),
}
DXF_LAYER = {"obj": "OUTLINE", "thin": "OUTLINE", "dim": "DIM", "tick": "DIM", "hidden": "HIDDEN",
             "center": "CENTER", "phantom": "PHANTOM", "cut": "CUT", "cutline": "CENTER", "eb": "EDGEBAND",
             "floor": "OUTLINE", "lead": "DIM"}


# ------------------------------------------------------------------ view recorder
class View:
    def __init__(self, den):
        self.den = den
        self.k = 72.0 / den
        self.ops = []

    def p(self, pt):
        return pt / self.k

    def line(self, a, b, c, d, st="obj"):
        self.ops.append(("line", a, b, c, d, st))

    def poly(self, pts, st="obj", fill=None, closed=True):
        self.ops.append(("poly", list(pts), st, fill, closed))

    def rect(self, u0, v0, u1, v1, st="obj", fill=None, hatch=False):
        if hatch:
            self.ops.append(("hatch", min(u0, u1), min(v0, v1), max(u0, u1), max(v0, v1)))
        self.poly([(u0, v0), (u1, v0), (u1, v1), (u0, v1)], st, fill)

    def fill(self, u0, v0, u1, v1, color):
        self.ops.append(("poly", [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], None, color, True))

    def circle(self, u, v, r_pt, st="thin", fill=None):
        self.ops.append(("circle", u, v, self.p(r_pt), st, fill))

    def text(self, u, v, s, size=7, anchor="m", font="Geist", color=INK, dx=0, dy=0, angle=0, lift=0):
        self.ops.append(("text", u + self.p(dx), v + self.p(dy), s, size, anchor, font, color, angle, lift))

    # -- dimensions (architectural ticks), offsets in points
    def hdim(self, u1, u2, v_from, off, txt=None, v_from2=None, size=6.5):
        vd = v_from + self.p(off)
        sgn = 1 if off > 0 else -1
        for u, vf in ((u1, v_from), (u2, v_from if v_from2 is None else v_from2)):
            self.line(u, vf + sgn * self.p(2), u, vd + sgn * self.p(3), "dim")
        self.line(u1 - self.p(3), vd, u2 + self.p(3), vd, "dim")
        for u in (u1, u2):
            self.line(u - self.p(2), vd - self.p(2), u + self.p(2), vd + self.p(2), "tick")
        t = txt or fmt(abs(u2 - u1))
        w = pdfmetrics.stringWidth(t, "MonoM", size)
        span = abs(u2 - u1) * self.k
        if w + 4 <= span:
            self.text((u1 + u2) / 2, vd, t, size, "m", "MonoM", lift=2)
        else:  # too tight: set the text just outside the far tick
            d = 1 if u2 >= u1 else -1
            self.text(u2 + d * self.p(w / 2 + 5), vd, t, size, "m", "MonoM", lift=2)

    def vdim(self, v1, v2, u_from, off, txt=None, u_from2=None, size=6.5):
        ud = u_from + self.p(off)
        sgn = 1 if off > 0 else -1
        for v, uf in ((v1, u_from), (v2, u_from if u_from2 is None else u_from2)):
            self.line(uf + sgn * self.p(2), v, ud + sgn * self.p(3), v, "dim")
        self.line(ud, v1 - self.p(3), ud, v2 + self.p(3), "dim")
        for v in (v1, v2):
            self.line(ud - self.p(2), v - self.p(2), ud + self.p(2), v + self.p(2), "tick")
        t = txt or fmt(abs(v2 - v1))
        w = pdfmetrics.stringWidth(t, "MonoM", size)
        if w + 4 <= abs(v2 - v1) * self.k:
            self.text(ud, (v1 + v2) / 2, t, size, "m", "MonoM", angle=90, lift=2)
        else:
            d = 1 if v2 >= v1 else -1
            self.text(ud, v2 + d * self.p(w / 2 + 5), t, size, "m", "MonoM", angle=90, lift=2)

    def hchain(self, us, v_from, off, **kw):
        for a, b in zip(us, us[1:]):
            self.hdim(a, b, v_from, off, **kw)

    def vchain(self, vs, u_from, off, **kw):
        for a, b in zip(vs, vs[1:]):
            self.vdim(a, b, u_from, off, **kw)

    def leader(self, u, v, dx, dy, s, size=6.5, anchor=None, font="Geist", color=INK):
        """Leader from model point (u,v) to a note offset (dx,dy) points away."""
        u2, v2 = u + self.p(dx), v + self.p(dy)
        self.line(u, v, u2, v2, "lead")
        self.circle(u, v, 1.1, "lead", fill=NAVY)
        anchor = anchor or ("l" if dx >= 0 else "r")
        lines = s.split("\n")
        for i, ln in enumerate(lines):
            self.text(u2, v2, ln, size, anchor, font, color, dx=(3 if anchor == "l" else -3),
                      dy=-2.4 - i * (size + 1.5) + (len(lines) - 1) * (size + 1.5) / 2)

    def elev(self, u, v, s, side=1):
        """Elevation marker: small triangle on a level line, with label."""
        L = self.p(46)
        u2 = u + side * L
        self.line(u, v, u2, v, "dim")
        tri = self.p(3.2)
        uu = u + side * self.p(8)
        self.poly([(uu - tri, v + tri * 1.4), (uu + tri, v + tri * 1.4), (uu, v)], "dim", fill=NAVY)
        self.text(u2, v, s, 6.3, "l" if side > 0 else "r", "MonoM", NAVY, dx=3 * side, dy=-2.2)


# ------------------------------------------------------------------ PDF rendering
def set_style(c, st):
    w, col, dash = STYLES[st]
    c.setLineWidth(w)
    c.setStrokeColor(col)
    c.setDash(dash or [])
    c.setLineCap(0)
    c.setLineJoin(0)


def draw_text(c, x, y, s, size, anchor, font, color, angle=0, lift=0, space=0):
    c.saveState()
    c.setFillColor(color)
    c.setFont(font, size)
    c.translate(x, y)
    if angle:
        c.rotate(angle)
    w = pdfmetrics.stringWidth(s, font, size) + space * max(len(s) - 1, 0)
    x0 = {"l": 0, "m": -w / 2, "r": -w}[anchor]
    c.drawString(x0, lift, s, charSpace=space) if space else c.drawString(x0, lift, s)
    c.restoreState()


def render_view(c, view, ox, oy):
    k = view.k
    X = lambda u: ox + u * k
    Y = lambda v: oy + v * k
    # fills first, then hatches, then lines, then text
    for op in view.ops:
        if op[0] == "poly" and op[3] is not None:
            _, pts, st, fill, closed = op
            path = c.beginPath()
            path.moveTo(X(pts[0][0]), Y(pts[0][1]))
            for u, v in pts[1:]:
                path.lineTo(X(u), Y(v))
            path.close()
            c.setFillColor(fill)
            c.drawPath(path, stroke=0, fill=1)
    for op in view.ops:
        if op[0] == "hatch":
            _, u0, v0, u1, v1 = op
            c.saveState()
            path = c.beginPath()
            path.rect(X(u0), Y(v0), (u1 - u0) * k, (v1 - v0) * k)
            c.clipPath(path, stroke=0, fill=0)
            c.setLineWidth(0.3)
            c.setStrokeColor(STONE6)
            c.setDash([])
            x0, x1 = sorted((X(u0), X(u1)))
            y0, y1 = sorted((Y(v0), Y(v1)))
            s = 3.2
            t = -(y1 - y0)
            while t < (x1 - x0):
                c.line(x0 + t, y0, x0 + t + (y1 - y0), y1)
                t += s
            c.restoreState()
    for op in view.ops:
        kind = op[0]
        if kind == "line":
            _, a, b, cc, d, st = op
            set_style(c, st)
            c.line(X(a), Y(b), X(cc), Y(d))
        elif kind == "poly" and op[2] is not None:
            _, pts, st, fill, closed = op
            set_style(c, st)
            path = c.beginPath()
            path.moveTo(X(pts[0][0]), Y(pts[0][1]))
            for u, v in pts[1:]:
                path.lineTo(X(u), Y(v))
            if closed:
                path.close()
            c.drawPath(path, stroke=1, fill=0)
        elif kind == "circle":
            _, u, v, r, st, fill = op
            set_style(c, st)
            if fill is not None:
                c.setFillColor(fill)
            c.circle(X(u), Y(v), r * k, stroke=1, fill=1 if fill is not None else 0)
    c.setDash([])
    for op in view.ops:
        if op[0] == "text":
            _, u, v, s, size, anchor, font, color, angle, lift = op
            draw_text(c, X(u), Y(v), s, size, anchor, font, color, angle, lift)


# ------------------------------------------------------------------ DXF (R12) writer
class Dxf:
    LAYERS = {"OUTLINE": (7, "CONTINUOUS"), "HIDDEN": (8, "DASHED"), "CENTER": (5, "CENTER"),
              "PHANTOM": (5, "PHANTOM"), "DIM": (3, "CONTINUOUS"), "TEXT": (7, "CONTINUOUS"),
              "CUT": (1, "CONTINUOUS"), "EDGEBAND": (4, "CONTINUOUS"), "SHEET": (9, "CONTINUOUS")}

    def __init__(self):
        self.e = []

    def line(self, x1, y1, x2, y2, layer):
        self.e.append(f"0\nLINE\n8\n{layer}\n10\n{x1:.4f}\n20\n{y1:.4f}\n30\n0\n11\n{x2:.4f}\n21\n{y2:.4f}\n31\n0\n")

    def circle(self, x, y, r, layer):
        self.e.append(f"0\nCIRCLE\n8\n{layer}\n10\n{x:.4f}\n20\n{y:.4f}\n30\n0\n40\n{r:.4f}\n")

    def text(self, x, y, h, s, layer="TEXT", rot=0, align="l"):
        s = s.replace("°", "%%d")
        a = {"l": 0, "m": 1, "r": 2}[align]
        rec = f"0\nTEXT\n8\n{layer}\n10\n{x:.4f}\n20\n{y:.4f}\n30\n0\n40\n{h:.4f}\n1\n{s}\n50\n{rot}\n"
        if a:
            rec += f"72\n{a}\n11\n{x:.4f}\n21\n{y:.4f}\n31\n0\n"
        self.e.append(rec)

    def save(self, path):
        lt = {"CONTINUOUS": [], "DASHED": [0.25, -0.125], "CENTER": [1.25, -0.25, 0.25, -0.25],
              "PHANTOM": [1.25, -0.25, 0.25, -0.25, 0.25, -0.25]}
        out = ["0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1009\n9\n$INSUNITS\n70\n1\n0\nENDSEC\n",
               "0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLTYPE\n70\n%d\n" % len(lt)]
        for name, pat in lt.items():
            out.append(f"0\nLTYPE\n2\n{name}\n70\n0\n3\n{name}\n72\n65\n73\n{len(pat)}\n40\n{sum(abs(p) for p in pat):.4f}\n"
                       + "".join(f"49\n{p}\n" for p in pat))
        out.append("0\nENDTAB\n0\nTABLE\n2\nLAYER\n70\n%d\n" % len(self.LAYERS))
        for name, (col, ltype) in self.LAYERS.items():
            out.append(f"0\nLAYER\n2\n{name}\n70\n0\n62\n{col}\n6\n{ltype}\n")
        out.append("0\nENDTAB\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n")
        out.extend(self.e)
        out.append("0\nENDSEC\n0\nEOF\n")
        with open(path, "w", newline="\r\n") as f:
            f.write("".join(out))


def dxf_view(dxf, view, ox, oy, title=None):
    """Write a view to DXF at 1:1 (model inches) offset by (ox, oy)."""
    for op in view.ops:
        kind = op[0]
        if kind == "line":
            _, a, b, c, d, st = op
            dxf.line(ox + a, oy + b, ox + c, oy + d, DXF_LAYER[st])
        elif kind == "poly" and op[2] is not None:
            _, pts, st, fill, closed = op
            seq = pts + ([pts[0]] if closed else [])
            for (a, b), (c, d) in zip(seq, seq[1:]):
                dxf.line(ox + a, oy + b, ox + c, oy + d, DXF_LAYER[st])
        elif kind == "circle":
            _, u, v, r, st, fill = op
            dxf.circle(ox + u, oy + v, r, DXF_LAYER[st])
        elif kind == "text":
            _, u, v, s, size, anchor, font, color, angle, lift = op
            h = size / view.k * 0.72
            if angle:
                dxf.text(ox + u - lift / view.k, oy + v, h, s, rot=angle, align=anchor)
            else:
                dxf.text(ox + u, oy + v + lift / view.k, h, s, align=anchor)
    if title:
        dxf.text(ox, oy - 8, 1.2, title)


# ------------------------------------------------------------------ sheet furniture
SHEETS = []  # (number, title) filled as sheets are drawn


def eyebrow(c, x, y, s, color=NAVY, size=6.5, anchor="l"):
    draw_text(c, x, y, s.upper(), size, anchor, "MonoM", color, space=size * 0.22)


def wordmark(c, x, y, size):
    c.setFont("Disp", size)
    for ch, col in (("OF", INK), ("4", NAVY5), ("S", INK)):
        c.setFillColor(col)
        c.drawString(x, y, ch)
        x += pdfmetrics.stringWidth(ch, "Disp", size)


def title_block(c, num, title, scale, idx, total):
    x0, x1 = PW - M - TB_W, PW - M
    c.setStrokeColor(INK)
    c.setLineWidth(0.8)
    c.setDash([])
    c.rect(M - 12, M - 12, PW - 2 * M + 24, PH - 2 * M + 24)  # sheet border
    c.setLineWidth(0.6)
    c.line(x0, M - 12, x0, PH - M + 12)
    pad = 12
    tx = x0 + pad
    y = PH - M - 16
    wordmark(c, tx, y - 6, 24)
    y -= 24
    draw_text(c, tx, y, "Office Furniture 4 Sale", 8.5, "l", "GeistSB", INK)
    y -= 11
    draw_text(c, tx, y, "1790 W 8th Ave, Hialeah, FL 33010", 7, "l", "Geist", STONE6)
    y -= 9.5
    draw_text(c, tx, y, "+1 305 889 3364 · officefurniture4sale.com", 7, "l", "Geist", STONE6)
    y -= 14
    c.setStrokeColor(PAPER3)
    c.setLineWidth(0.6)
    c.line(x0, y, x1, y)

    def field(label, value, y, size=8.5, font="Geist", wrap=TB_W - 2 * pad):
        y -= 14
        eyebrow(c, tx, y, label, NAVY, 5.8)
        y -= 12
        for ln in wrap_text(value, font, size, wrap):
            draw_text(c, tx, y, ln, size, "l", font, INK)
            y -= size + 2.5
        return y - 2

    y = field("Project", PROJECT, y, 9.5, "GeistSB")
    y = field("Client", CLIENT, y)
    y = field("Drawing", title, y, 9.5, "GeistSB")
    y = field("Scale", scale, y)
    y = field("Date", DATE, y)
    y = field("Revision", REV, y)
    y = field("Units", "Inches. Use written dimensions; do not scale.", y, 7.5)
    y = field("Status", "For quotation. Fabricator submits shop drawings and finish samples "
                        "for approval before production.", y, 7.5)
    # revision table
    y -= 6
    c.setStrokeColor(PAPER3)
    c.line(x0, y, x1, y)
    y -= 13
    eyebrow(c, tx, y, "Rev · Date · Description", NAVY, 5.8)
    y -= 12
    draw_text(c, tx, y, "0 · 11/04/26 · Issued for pricing", 7, "l", "Mono", INK)
    # sheet number block
    c.setFillColor(PAPER1)
    c.rect(x0, M - 12, TB_W, 74, stroke=0, fill=1)
    c.setStrokeColor(INK)
    c.line(x0, M + 62, x1, M + 62)
    eyebrow(c, tx, M + 48, "Sheet", NAVY, 5.8)
    draw_text(c, tx, M + 12, num, 30, "l", "Disp", INK)
    draw_text(c, x1 - pad, M + 14, f"{idx} of {total}", 8, "r", "Mono", STONE6)


def wrap_text(s, font, size, width):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(t, font, size) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def paragraph(c, x, y, s, width, size=8, font="Geist", color=INK, leading=None):
    leading = leading or size * 1.42
    for ln in wrap_text(s, font, size, width):
        draw_text(c, x, y, ln, size, "l", font, color)
        y -= leading
    return y


def view_label(c, x, y, n, title, scale):
    c.setStrokeColor(INK)
    c.setLineWidth(0.8)
    c.setDash([])
    c.setFillColor(WHITE)
    c.circle(x + 9, y + 3, 9, stroke=1, fill=1)
    draw_text(c, x + 9, y, str(n), 9, "m", "DispSB", INK)
    draw_text(c, x + 24, y + 1, title, 11, "l", "DispSB", INK)
    w = pdfmetrics.stringWidth(title, "DispSB", 11)
    c.setLineWidth(0.6)
    c.line(x + 24, y - 4, x + 24 + max(w, 120), y - 4)
    if scale:
        eyebrow(c, x + 24, y - 14, scale, STONE6, 6)


def sheet_heading(c, eyebrow_txt, title):
    eyebrow(c, M, PH - M - 6, eyebrow_txt)
    draw_text(c, M, PH - M - 30, title, 20, "l", "Disp", INK)


def place_image(c, path, x, y, w, h, crop=True):
    im = Image.open(path).convert("RGB")
    if crop:
        bg = Image.new("RGB", im.size, (255, 255, 255))
        from PIL import ImageChops
        bbox = ImageChops.difference(im, bg).getbbox()
        if bbox:
            pad = 30
            bbox = (max(bbox[0] - pad, 0), max(bbox[1] - pad, 0), min(bbox[2] + pad, im.width),
                    min(bbox[3] + pad, im.height))
            im = im.crop(bbox)
    r = min(w / im.width, h / im.height)
    dw, dh = im.width * r, im.height * r
    c.drawImage(ImageReader(im), x + (w - dw) / 2, y + (h - dh) / 2, dw, dh)
    return dw, dh


# ------------------------------------------------------------------ views
T, W, D, H = g.T, g.W, g.D, g.H
B = g.BASE_H
SX = [0, T] + sum([[g.divider_x(i), g.divider_x(i) + T] for i in range(g.COLS - 1)], []) + [W - T, W]
SZ = [0, B, B + T] + sum([[g.shelf_z(i), g.shelf_z(i) + T] for i in range(g.TIERS - 1)], []) + [g.SIDE_H, H]


def front_elevation(loaded=False, dims=True, marks=True):
    v = View(5)
    v.line(-2, 0, W + 2, 0, "floor")
    # openings tint (back panel seen through)
    for t in range(g.TIERS):
        for col in range(g.COLS):
            x0, z0 = g.col_x(col), g.tier_floor(t)
            v.fill(x0, z0, x0 + g.OPEN_W, z0 + g.OPEN_H, PAPER1)
    v.fill(T, 0, W - T, B, PAPER3)
    v.rect(0, g.SIDE_H, W, H)                       # top
    for x in (0, W - T):                             # sides
        v.rect(x, 0, x + T, g.SIDE_H)
        v.line(x, B, x + T, B, "thin")              # toe-notch shoulder
    v.rect(T, 0, W - T, B)                           # toe kick (recessed)
    v.rect(T, B, W - T, B + T)                       # bottom deck
    for i in range(g.TIERS - 1):
        z = g.shelf_z(i)
        v.rect(T, z, W - T, z + T)
    for t in range(g.TIERS):
        for i in range(g.COLS - 1):
            x = g.divider_x(i)
            v.rect(x, g.tier_floor(t), x + T, g.tier_floor(t) + g.OPEN_H)
    for t in range(g.TIERS):
        for col in range(g.COLS):
            x0, z0 = g.col_x(col), g.tier_floor(t)
            if loaded:
                lx = x0 + (g.OPEN_W - g.LAPTOP_W) / 2
                for k in range(g.STACK):
                    zz = z0 + k * g.LAPTOP_T
                    v.rect(lx, zz, lx + g.LAPTOP_W, zz + g.LAPTOP_T - 0.08, "phantom", fill=NAVY1)
                v.text(x0 + g.OPEN_W / 2, z0 + g.STACK_H + 0.75, f"{'ABCD'[col]}{t + 1}  ·  5 laptops",
                       6.2, "m", "MonoM", NAVY, dy=-2)
            else:
                v.text(x0 + 0.35, z0 + g.OPEN_H - 0.35, f"{'ABCD'[col]}{t + 1}", 6.5, "l", "MonoM", NAVY, dy=-6)
    if dims:
        v.hchain(SX, 0, -16)
        v.hdim(0, W, 0, -36)
        v.vchain(SZ, 0, -16)
        v.vdim(0, H, 0, -38)
        v.elev(W, H, f'TOP  +{fmt(H)} AFF')
        for t in range(g.TIERS):
            v.elev(W, g.tier_floor(t), f'BAY FLOOR  +{fmt(g.tier_floor(t))}')
        v.elev(W, 0, "FIN. FLOOR  0\"")
    if marks:
        # section A-A, vertical through column B, looking left
        xa = g.col_x(1) + g.OPEN_W / 2
        v.line(xa, -4.2, xa, H + 3, "cutline")
        for zz in (H + 3, -4.2):
            v.circle(xa, zz + (1.0 if zz > 0 else -1.0), 8, "obj", fill=WHITE)
            v.text(xa, zz + (1.0 if zz > 0 else -1.0), "A", 8.5, "m", "DispSB", dy=-3)
            v.poly([(xa - 0.5, zz), (xa - 2.2, zz + 0.6), (xa - 2.2, zz - 0.6)], "obj", fill=INK)
            v.text(xa - 2.4, zz, "A-102", 5.6, "r", "MonoM", STONE6, dy=-2)
        # section B-B, horizontal through tier 1, looking down
        zb = g.tier_floor(0) + g.OPEN_H * 0.62
        v.line(-3.0, zb, W + 3.0, zb, "cutline")
        for xx in (-3.0, W + 3.0):
            off = -1.0 if xx < 0 else 1.0
            v.circle(xx + off, zb, 8, "obj", fill=WHITE)
            v.text(xx + off, zb, "B", 8.5, "m", "DispSB", dy=-3)
            v.poly([(xx, zb - 0.5), (xx - 0.6, zb - 2.2), (xx + 0.6, zb - 2.2)], "obj", fill=INK)
            v.text(xx, zb - 2.6, "A-103", 5.6, "m", "MonoM", STONE6, dy=-6)
    return v


def section_a():
    """Section A-A through column B, looking left. u = depth (0 front), v = height."""
    v = View(5)
    v.line(-4, 0, D + 3, 0, "floor")
    # beyond: left side panel outline, divider faces in each bay
    v.poly([(y, z) for y, z in g.SIDE_PROFILE], "thin")
    for t in range(g.TIERS):
        z0 = g.tier_floor(t)
        v.fill(0, z0, g.INT_D, z0 + g.OPEN_H, PAPER1)
        v.rect(0, z0, g.INT_D, z0 + g.OPEN_H, "thin")
        y0 = g.LAPTOP_Y0
        for k in range(g.STACK):
            zz = z0 + k * g.LAPTOP_T
            v.rect(y0, zz, y0 + g.LAPTOP_D, zz + g.LAPTOP_T - 0.08, "phantom")
    # cut members
    v.rect(0, g.SIDE_H, D, H, "cut", hatch=True)                      # top
    v.rect(0, B, g.INT_D, B + T, "cut", hatch=True)                   # bottom deck
    for i in range(g.TIERS - 1):
        z = g.shelf_z(i)
        v.rect(0, z, g.INT_D, z + T, "cut", hatch=True)
    v.rect(g.INT_D, B, D, g.SIDE_H, "cut", hatch=True)                 # back
    v.rect(g.KICK_SETBACK, 0, g.KICK_SETBACK + T, B, "cut", hatch=True)  # toe kick
    v.rect(g.INT_D - T, 0, g.INT_D, B, "cut", hatch=True)             # rear rail
    # wall
    v.line(D + 0.25, -0.5, D + 0.25, H + 2, "hidden")
    v.text(D + 0.25, B + 6, "WALL (BY OTHERS)", 5.6, "l", "MonoM", STONE6, angle=90, lift=3)
    # dims
    v.hdim(0, D, H, 30)
    v.hchain([0, g.INT_D, D], H, 14)
    v.hchain([0, g.KICK_SETBACK, g.KICK_SETBACK + T], 0, -14)
    v.hchain([g.INT_D - T, g.INT_D], 0, -14)
    v.hchain([0, g.LAPTOP_Y0, g.LAPTOP_Y0 + g.LAPTOP_D, g.INT_D], 0, -32)
    v.vchain(SZ, 0, -16)
    v.vdim(0, H, 0, -38)
    z0 = g.tier_floor(g.TIERS - 1)
    v.vchain([z0, z0 + g.STACK_H, z0 + g.OPEN_H], D, 34)
    v.leader(12, g.tier_floor(1) + 2.2, 4.5 * v.k + 40, 0, "Stack of 5 laptops\n10\" x 14\" x 1-1/2\" each", 6.3)
    v.leader(D - 0.25, g.tier_floor(0) + 4, 40, 6, "1/2\" back panel\nin 1/2\" x 1/2\" rabbet", 6.3)
    v.text(g.KICK_SETBACK + T + 0.3, B / 2, "P06 toe kick", 5.8, "l", "MonoM", STONE6, dy=-2)
    v.text(g.INT_D - T - 0.3, B / 2, "P07 rear rail", 5.8, "r", "MonoM", STONE6, dy=-2)
    return v


def side_elevation():
    """Exterior right side. u = depth (0 front at left), v = height."""
    v = View(5)
    v.line(-4, 0, D + 4, 0, "floor")
    v.poly([(y, z) for y, z in g.SIDE_PROFILE], "obj", fill=PAPER2)
    v.rect(0, g.SIDE_H, D, H)
    # hidden: deck, shelves, kick, rail, rabbet
    v.rect(0, B, g.INT_D, B + T, "hidden")
    for i in range(g.TIERS - 1):
        v.rect(0, g.shelf_z(i), g.INT_D, g.shelf_z(i) + T, "hidden")
    v.rect(g.KICK_SETBACK, 0, g.KICK_SETBACK + T, B, "hidden")
    v.rect(g.INT_D - T, 0, g.INT_D, B, "hidden")
    v.line(D - g.BACK_T, 0, D - g.BACK_T, g.SIDE_H, "hidden")
    for y in g.GLIDE_Y:
        v.line(y, 0, y, 1.2, "center")
        v.rect(y - 0.6, -0.375, y + 0.6, 0, "thin", fill=PAPER3)
    v.hdim(0, D, H, 16)
    v.hchain([0, g.KICK_SETBACK, D], 0, -16)
    v.hchain([g.KICK_SETBACK, g.GLIDE_Y[0], g.GLIDE_Y[1], D], 0, -32)
    v.vchain([0, B, g.SIDE_H, H], D, 16)
    v.vdim(0, H, D, 36)
    v.leader(g.KICK_SETBACK / 2, B / 2, -30, 18, "Toe-kick\nnotch", 6.3)
    v.leader(g.GLIDE_Y[1], -0.2, 12, -50, "Leveling glide H01 (2 per side)", 6.3)
    v.leader(D - g.BACK_T, 26, -50, 20, "Rabbet for back\n(hidden)", 6.3)
    v.text(D / 2, 20, "SIDE PANEL P02", 6.5, "m", "MonoM", STONE6)
    v.text(D / 2, 18.4, "exposed face", 6.3, "m", "Geist", STONE6)
    return v


def bay_detail():
    """One bay, front view at 1:4."""
    v = View(5)
    ow, oh = g.OPEN_W, g.OPEN_H
    v.fill(0, 0, ow, oh, PAPER1)
    v.rect(-T, -T, 0, oh + T, "obj", fill=WHITE)          # divider / side left
    v.rect(ow, -T, ow + T, oh + T, "obj", fill=WHITE)      # divider right
    v.rect(-T, -T, ow + T, 0, "obj", fill=WHITE)           # shelf below
    v.rect(-T, oh, ow + T, oh + T, "obj", fill=WHITE)      # shelf above
    lx = (ow - g.LAPTOP_W) / 2
    for k in range(g.STACK):
        zz = k * g.LAPTOP_T
        v.rect(lx, zz, lx + g.LAPTOP_W, zz + g.LAPTOP_T - 0.06, "phantom", fill=NAVY1)
        v.text(lx + g.LAPTOP_W / 2, zz + g.LAPTOP_T / 2, f"Laptop {k + 1}", 6, "m", "MonoM", NAVY, dy=-2)
    v.hchain([0, lx, lx + g.LAPTOP_W, ow], -T, -14)
    v.hdim(0, ow, -T, -32, txt=f'{fmt(ow)} clear')
    v.vchain([0, g.STACK_H, oh], ow + T, 16)
    v.vdim(0, g.LAPTOP_T, -T, -14)
    v.vdim(0, oh, -T, -32, txt=f'{fmt(oh)} clear')
    return v


def top_plan():
    """Top plan. u = x, v = depth with FRONT at the bottom (v = D - y)."""
    v = View(5)
    v.line(-3, D + 0.25, W + 3, D + 0.25, "hidden")
    v.text(-3, D + 0.25, "WALL (BY OTHERS)", 5.6, "l", "MonoM", STONE6, dy=3)
    v.rect(0, 0, W, D, "obj", fill=PAPER2)
    # edge band on all 4 edges
    e = v.p(1.6)
    v.rect(e, e, W - e, D - e, "eb")
    # hidden below: sides, dividers
    for x in (T, W - T):
        v.line(x, 0, x, D, "hidden")
    for i in range(g.COLS - 1):
        x = g.divider_x(i)
        v.rect(x, 0, x + T, g.INT_D, "hidden")
    v.text(W / 2, D / 2, "TOP P01  ·  1\" TFM  ·  EDGEBAND ALL 4 EDGES", 7, "m", "MonoM", INK, dy=-2.5)
    v.text(W / 2, -0.2, "FRONT", 6.2, "m", "MonoM", NAVY, dy=-18)
    v.hdim(0, W, D, 14)
    v.vdim(0, D, 0, -16)
    return v


def plan_section_b():
    """Plan section B-B through tier 1, looking down. FRONT at the bottom."""
    v = View(5)
    yv = lambda y: y   # model y -> view v (front at bottom)
    v.fill(T, yv(g.INT_D), W - T, yv(0), PAPER1)            # bottom deck below
    v.rect(T, yv(g.KICK_SETBACK + T), W - T, yv(g.KICK_SETBACK), "hidden")   # toe kick below deck
    v.rect(T, yv(g.INT_D), W - T, yv(g.INT_D - T), "hidden")                 # rear rail
    # cut: sides with rabbet, dividers, back
    for x0, inner in ((0, T), (W - T, W - T)):
        rab = g.BACK_T if x0 == 0 else -g.BACK_T
        pts = [(x0, yv(0)), (x0 + T, yv(0)), (x0 + T, yv(D))] if x0 == 0 else \
              [(x0 + T, yv(0)), (x0, yv(0)), (x0, yv(D))]
        if x0 == 0:
            poly = [(0, yv(0)), (T, yv(0)), (T, yv(g.INT_D)), (T - g.BACK_T, yv(g.INT_D)),
                    (T - g.BACK_T, yv(D)), (0, yv(D))]
            v.ops.append(("hatch", 0, yv(D), T - g.BACK_T, yv(0)))
            v.ops.append(("hatch", T - g.BACK_T, yv(g.INT_D), T, yv(0)))
        else:
            poly = [(W, yv(0)), (W - T, yv(0)), (W - T, yv(g.INT_D)), (W - T + g.BACK_T, yv(g.INT_D)),
                    (W - T + g.BACK_T, yv(D)), (W, yv(D))]
            v.ops.append(("hatch", W - T + g.BACK_T, yv(D), W, yv(0)))
            v.ops.append(("hatch", W - T, yv(g.INT_D), W - T + g.BACK_T, yv(0)))
        v.poly(poly, "cut")
    for i in range(g.COLS - 1):
        x = g.divider_x(i)
        v.rect(x, yv(g.INT_D), x + T, yv(0), "cut", hatch=True)
    v.rect(T - g.BACK_T, yv(D), W - T + g.BACK_T, yv(g.INT_D), "cut", hatch=True)
    # laptop footprints
    for col in range(g.COLS):
        x0 = g.col_x(col) + (g.OPEN_W - g.LAPTOP_W) / 2
        v.rect(x0, yv(g.LAPTOP_Y0 + g.LAPTOP_D), x0 + g.LAPTOP_W, yv(g.LAPTOP_Y0), "phantom", fill=NAVY1)
        v.text(x0 + g.LAPTOP_W / 2, yv(g.LAPTOP_Y0 + g.LAPTOP_D / 2), f"{'ABCD'[col]}1", 8, "m", "DispSB", NAVY, dy=4)
        v.text(x0 + g.LAPTOP_W / 2, yv(g.LAPTOP_Y0 + g.LAPTOP_D / 2), "10\" x 14\" laptop", 6, "m", "MonoM", NAVY, dy=-8)
    v.text(W / 2, -0.2, "FRONT", 6.2, "m", "MonoM", NAVY, dy=-40)
    v.hchain(SX, 0, -14)
    v.hdim(0, W, 0, -30)
    v.vchain([0, g.LAPTOP_Y0, g.LAPTOP_Y0 + g.LAPTOP_D, g.INT_D], W, 16)
    v.vdim(0, D, W, 40)
    c0 = g.col_x(0) + (g.OPEN_W - g.LAPTOP_W) / 2
    v.hchain([T, c0, c0 + g.LAPTOP_W, T + g.OPEN_W], D, 12)
    v.leader(T - g.BACK_T / 2, yv(D - 0.2), -24, 16, "1/2\" x 1/2\" rabbet", 6.3)
    return v


# --- part detail views (1:8)
def part_rect(mark, L, Wd, eb_edges, extra=None, den=8, label_dims=True):
    v = View(den)
    v.rect(0, 0, L, Wd, "obj", fill=PAPER2)
    e = v.p(1.8)
    if "L1" in eb_edges:   # front long edge = bottom in view
        v.line(0, e, L, e, "eb")
    if "L2" in eb_edges:
        v.line(0, Wd - e, L, Wd - e, "eb")
    if "W1" in eb_edges:
        v.line(e, 0, e, Wd, "eb")
    if "W2" in eb_edges:
        v.line(L - e, 0, L - e, Wd, "eb")
    if extra:
        extra(v)
    if label_dims:
        v.hdim(0, L, 0, -14)
        v.vdim(0, Wd, 0, -14)
    return v


def part_side():
    v = View(8)
    prof = [(y, z) for y, z in g.SIDE_PROFILE]
    v.poly(prof, "obj", fill=PAPER2)
    e = v.p(1.8)
    v.line(e, B, e, g.SIDE_H, "eb")                 # front edge
    v.line(g.KICK_SETBACK - e, 0, g.KICK_SETBACK - e, B, "eb")   # notch vertical
    v.line(0, B + e, g.KICK_SETBACK, B + e, "eb")   # notch horizontal
    v.line(D - e, 0, D - e, g.SIDE_H, "eb")         # rear edge
    v.line(D - g.BACK_T, 0, D - g.BACK_T, g.SIDE_H, "hidden")
    # inside-face locations of mating parts (phantom)
    v.rect(0, B, g.INT_D, B + T, "phantom")
    for i in range(g.TIERS - 1):
        v.rect(0, g.shelf_z(i), g.INT_D, g.shelf_z(i) + T, "phantom")
    v.rect(g.KICK_SETBACK, 0, g.KICK_SETBACK + T, B, "phantom")
    v.rect(g.INT_D - T, 0, g.INT_D, B, "phantom")
    for y in g.GLIDE_Y:
        v.line(y, -0.8, y, 1.2, "center")
    v.hdim(0, D, g.SIDE_H, 14)
    v.hchain([0, g.KICK_SETBACK, D], 0, -14)
    v.hchain([g.KICK_SETBACK, g.GLIDE_Y[0], g.GLIDE_Y[1], D], 0, -28)
    v.vdim(0, g.SIDE_H, 0, -38)
    v.vchain([0, B, B + T] + sum([[g.shelf_z(i), g.shelf_z(i) + T] for i in range(g.TIERS - 1)], []) + [g.SIDE_H],
             0, -16, size=5.8)
    v.leader(D - g.BACK_T, g.SIDE_H - 4, 22, 8, "1/2\" x 1/2\" rabbet,\nfull height, inside face", 6)
    v.leader(g.INT_D / 2, g.shelf_z(1) + T / 2, 100, 14, "Mating parts shown\nphantom (drill locations)", 6)
    return v


def rabbet_detail():
    v = View(2)   # 1:2
    # plan view corner of left side + back panel
    v.poly([(0, 0), (1.0, 0), (1.0, 2.0), (0.5, 2.0), (0.5, 2.5), (0, 2.5)], "cut")
    v.ops.append(("hatch", 0, 0, 0.5, 2.5))
    v.ops.append(("hatch", 0.5, 0, 1.0, 2.0))
    v.rect(0.5, 2.0, 2.6, 2.5, "cut", hatch=True)
    v.rect(1.0, 0.6, 2.6, 2.0, "thin", fill=PAPER1)
    v.hchain([0, 0.5, 1.0], 2.5, 14)
    v.vchain([0, 2.0, 2.5], 0, -14)
    v.text(0.25, 1.0, "SIDE P02", 6, "m", "MonoM", INK, angle=90, lift=-2)
    v.text(1.8, 2.25, "BACK P08", 6, "m", "MonoM", INK, dy=-2)
    v.text(1.8, 1.3, "bay", 6.5, "m", "Geist", STONE6, dy=-2)
    v.leader(0.75, 2.25, 80, 34, "#6 x 5/8\" screw\n@ 6\" o.c.", 6)
    return v


def doors_elevation():
    v = View(8)
    d = g.DOOR_GAP
    v.line(-3, 0, W + 3, 0, "floor")
    v.rect(0, g.SIDE_H, W, H)
    for x in (0, W - T):
        v.rect(x, 0, x + T, B)
    v.rect(T, 0, W - T, B, "obj", fill=PAPER3)
    for i in range(g.COLS):
        x0 = i * W / g.COLS + d / 2
        z0 = B + d / 2
        v.rect(x0, z0, x0 + g.DOOR_W, z0 + g.DOOR_H, "obj", fill=NAVY1)
        hinge_left = i in (0, 2)
        hx = x0 + (0.9 if hinge_left else g.DOOR_W - 0.9)
        for hz in (z0 + 3, z0 + g.DOOR_H - 3):
            v.rect(hx - 0.35, hz - 1, hx + 0.35, hz + 1, "thin")
        px = x0 + (g.DOOR_W - 1.5 if hinge_left else 1.5)
        v.line(px, z0 + g.DOOR_H - 9, px, z0 + g.DOOR_H - 5, "obj")
        v.circle(px, z0 + g.DOOR_H - 2.5, 3, "obj")
        # swing triangle
        sx = x0 + (g.DOOR_W if hinge_left else 0)
        hxe = x0 + (0 if hinge_left else g.DOOR_W)
        v.line(sx, z0, hxe, z0 + g.DOOR_H / 2, "hidden")
        v.line(hxe, z0 + g.DOOR_H / 2, sx, z0 + g.DOOR_H, "hidden")
    v.hchain([0, W / 4, W / 2, 3 * W / 4, W], 0, -14)
    v.vchain([0, B, g.SIDE_H, H], W, 14)
    return v


# ------------------------------------------------------------------ sheet builders
class SheetSet:
    def __init__(self, path):
        self.c = canvas.Canvas(path, pagesize=(PW, PH))
        self.c.setTitle(f"{PROJECT} · drawing set for quotation")
        self.c.setAuthor("Office Furniture 4 Sale")
        self.c.setSubject("Custom casework RFQ")
        self.pages = []
        self.dxf = Dxf()
        self.dxf_y = 0

    def add(self, num, title, scale, fn):
        self.pages.append((num, title, scale, fn))

    def build(self):
        total = len(self.pages)
        for i, (num, title, scale, fn) in enumerate(self.pages, 1):
            fn(self, self.c)
            title_block(self.c, num, title, scale, i, total)
            self.c.showPage()
        self.c.save()

    def to_dxf(self, view, title, x):
        dxf_view(self.dxf, view, x, self.dxf_y, title)


def sheet_cover(S, c):
    eyebrow(c, M, PH - M - 6, "Custom casework · request for quotation")
    draw_text(c, M, PH - M - 44, "LC-60 laptop storage cabinet", 34, "l", "Disp", INK)
    paragraph(c, M, PH - M - 66, f'Sixty laptops in twelve open bays of five. {fmt(W)} wide, {fmt(D)} deep, '
              f'{fmt(H)} tall. Fixed shelves, 1" panels throughout, 4" toe-kick base.', 470, 11, "Geist", STONE6, 15)
    # design basis
    y = PH - M - 118
    eyebrow(c, M, y, "Design basis")
    y -= 8
    rows = [
        ("Laptop footprint", f'{fmt(g.LAPTOP_W)} x {fmt(g.LAPTOP_D)}, {fmt(g.LAPTOP_T)} thick'),
        ("Stack limit", f'{g.STACK} laptops = {fmt(g.STACK_H)} tall'),
        ("Capacity", f'{g.CAPACITY} laptops = {g.BAYS} stacks (required {g.LAPTOPS})'),
        ("Layout", f'{g.COLS} columns x {g.TIERS} tiers = {g.BAYS} bays'),
        ("Clear bay", f'{fmt(g.OPEN_W)} W x {fmt(g.OPEN_H)} H x {fmt(g.INT_D)} D'),
        ("Clearance per stack", '1/2" each side, 1-1/2" above, 3/4" front and back'),
        ("Overall size", f'{fmt(W)} W x {fmt(D)} D x {fmt(H)} H'),
        ("Panels", '1" sides, top, deck, shelves, dividers. 1/2" back'),
        ("Base", f'{fmt(B)} toe kick, recessed {fmt(g.KICK_SETBACK)}; first bay floor at {fmt(g.FLOOR1_Z)}'),
        ("Weight (approx.)", f'{g.TOTAL_LB:.0f} lb empty, {g.LOADED_LB:.0f} lb loaded at 5 lb per laptop'),
    ]
    for k_, val in rows:
        y -= 17
        c.setStrokeColor(PAPER3)
        c.setLineWidth(0.5)
        c.line(M, y - 5, M + 440, y - 5)
        draw_text(c, M, y, k_, 8.5, "l", "GeistSB", INK)
        draw_text(c, M + 130, y, val, 8.5, "l", "Mono", INK)
    # general notes
    y -= 34
    eyebrow(c, M, y, "General notes")
    notes = [
        "All dimensions are finished sizes in inches. Overall height is floor to top of top, glides at minimum.",
        "Board: 1\" industrial particleboard, 45 lb density minimum, thermally fused laminate both faces. "
        "Back: 1/2\" MDF, TFM both faces. Color by owner, to be confirmed.",
        "Edgeband: 3 mm PVC on every exposed edge, color-matched. See cut list A-401.",
        "Joinery: 8 mm dowels plus confirmat screws, factory assembled. Knock-down cam fittings acceptable "
        "if stated in the quote.",
        "Shelves are fixed and carried by dividers every 12\". Minimum 50 lb per bay.",
        "Glides add about 3/8\". If 35\" is a hard maximum, cut toe kick, rear rail and notch to 3-5/8\".",
        "Anchor to the wall with the anti-tip kit (H06). Loaded weight is about 475 lb.",
        "Confirm laptop size against an owner sample before cutting.",
    ]
    y -= 6
    for i, n in enumerate(notes, 1):
        y -= 13
        draw_text(c, M, y, f"{i}.", 8, "l", "MonoM", NAVY)
        y = paragraph(c, M + 16, y, n, 424, 8, "Geist", INK, 11) + 11 - 2
    # image
    place_image(c, os.path.join(RENDERS, "iso_loaded.png"), 500, 300, AREA_R - 500, 390)
    eyebrow(c, 520, 284, "Isometric · shown loaded with 60 laptops", STONE6, 6)
    # sheet index
    x = 520
    y = 236
    eyebrow(c, x, y, "Sheet index")
    y -= 6
    col2 = x + 230
    for i, (num, title, scale, fn) in enumerate(S.pages):
        xx = x if i < 6 else col2
        yy = y - 15 * ((i % 6) + 1)
        draw_text(c, xx, yy, num, 8, "l", "MonoM", NAVY)
        draw_text(c, xx + 44, yy, title, 8, "l", "Geist", INK)


def sheet_front(S, c):
    sheet_heading(c, "Elevations", "Front elevation")
    v = front_elevation()
    ox, oy = 150, 165
    render_view(c, v, ox, oy)
    view_label(c, ox - 40, 70, 1, "Front elevation", "Scale 1:5")
    # key notes
    x = ox + W * v.k - 280
    S.to_dxf(v, "FRONT ELEVATION", 0)


def sheet_sections(S, c):
    sheet_heading(c, "Sections and details", "Section A-A, side elevation, bay detail")
    v1 = section_a()
    render_view(c, v1, 95, 150)
    view_label(c, 55, 70, 2, "Section A-A", "Scale 1:5 · see A-101")
    v2 = side_elevation()
    render_view(c, v2, 470, 150)
    view_label(c, 440, 70, 3, "Right side elevation", "Scale 1:5 · left side mirror")
    v3 = bay_detail()
    render_view(c, v3, 800, 500)
    view_label(c, 760, 420, 4, "Typical bay", "Scale 1:5")
    y = 360
    eyebrow(c, 760, y, "Fit check")
    for s in [f"Stack {fmt(g.STACK_H)} in a {fmt(g.OPEN_H)} bay leaves {fmt(g.OPEN_H - g.STACK_H)} to lift the top laptop.",
              f"{fmt((g.OPEN_W - g.LAPTOP_W) / 2)} each side for fingers and rubber feet.",
              f"{fmt(g.LAPTOP_D)} laptop in {fmt(g.INT_D)} depth: {fmt(g.INT_D - g.LAPTOP_D)} spare."]:
        y -= 14
        y = paragraph(c, 760, y, s, 220, 7.5, "Geist", INK, 10.5) + 10.5 - 4
    S.dxf_y = -60
    S.to_dxf(v1, "SECTION A-A", 0)
    S.to_dxf(v2, "RIGHT SIDE ELEVATION", 40)
    S.to_dxf(v3, "TYPICAL BAY", 80)


def sheet_plans(S, c):
    sheet_heading(c, "Plans", "Top plan and plan section B-B")
    v1 = top_plan()
    render_view(c, v1, 160, 470)
    view_label(c, 120, 420, 5, "Top plan", "Scale 1:5")
    v2 = plan_section_b()
    render_view(c, v2, 160, 120)
    view_label(c, 120, 52, 6, "Plan section B-B", "Scale 1:5 · through tier 1, looking down")
    S.dxf_y = -110
    S.to_dxf(v1, "TOP PLAN", 0)
    S.to_dxf(v2, "PLAN SECTION B-B", 70)


def sheet_loaded(S, c):
    sheet_heading(c, "Capacity", "Front elevation, loaded")
    v = front_elevation(loaded=True, dims=False, marks=False)
    v.hchain([0, W], 0, -16)
    v.vchain([0, H], 0, -16)
    ox, oy = 110, 165
    render_view(c, v, ox, oy)
    view_label(c, ox - 40, 70, 7, "Front elevation, loaded", "Scale 1:5")
    # capacity table
    x, y = 840, 640
    eyebrow(c, x, y, "Bay schedule")
    y -= 10
    c.setFont("MonoM", 7)
    hdr = ["Bay", "Tier floor", "Laptops"]
    xs = [x, x + 40, x + 104]
    for i, h in enumerate(hdr):
        draw_text(c, xs[i], y - 10, h.upper(), 6, "l", "MonoM", STONE6)
    y -= 16
    for t in range(g.TIERS - 1, -1, -1):
        for col in range(g.COLS):
            y -= 13
            c.setStrokeColor(PAPER3)
            c.setLineWidth(0.4)
            c.line(x, y - 4, x + 140, y - 4)
            draw_text(c, xs[0], y, f"{'ABCD'[col]}{t + 1}", 7.5, "l", "MonoM", NAVY)
            draw_text(c, xs[1], y, f'+{fmt(g.tier_floor(t))}', 7.5, "l", "Mono", INK)
            draw_text(c, xs[2], y, str(g.STACK), 7.5, "l", "Mono", INK)
    y -= 18
    draw_text(c, xs[0], y, "Total", 8.5, "l", "GeistSB", INK)
    draw_text(c, xs[2], y, str(g.CAPACITY), 8.5, "l", "MonoM", INK)
    y -= 26
    paragraph(c, x, y, "Bay IDs run A to D left to right, 1 to 3 bottom to top. Optional ID plates are ALT-5.",
              140, 7.5, "Geist", STONE6, 10.5)


def sheet_3d(S, c):
    sheet_heading(c, "3D views", "Isometric views")
    half = (AREA_R - M - 20) / 2
    place_image(c, os.path.join(RENDERS, "iso_empty.png"), M, 330, half, 360)
    eyebrow(c, M, 330, "Front isometric · empty", STONE6, 6)
    place_image(c, os.path.join(RENDERS, "iso_loaded.png"), M + half + 20, 330, half, 360)
    eyebrow(c, M + half + 20, 330, "Front isometric · loaded, 60 laptops", STONE6, 6)
    place_image(c, os.path.join(RENDERS, "rear_iso.png"), M, 50, half, 260)
    eyebrow(c, M, 50, "Rear isometric · back panel and rear rail", STONE6, 6)
    place_image(c, os.path.join(RENDERS, "iso_doors.png"), M + half + 20, 50, half, 260)
    eyebrow(c, M + half + 20, 50, "Alternate ALT-1 · lockable doors (phantom)", STONE6, 6)


def sheet_exploded(S, c):
    sheet_heading(c, "Assembly", "Exploded isometric")
    place_image(c, os.path.join(RENDERS, "exploded.png"), M, 50, 700, 640)
    x, y = 770, 640
    eyebrow(c, x, y, "Part legend")
    y -= 8
    for p in g.PARTS:
        y -= 26
        draw_text(c, x, y, p["mark"], 9, "l", "DispSB", NAVY)
        draw_text(c, x + 34, y, p["name"].split(" (")[0], 8.5, "l", "GeistSB", INK)
        draw_text(c, x + 34, y - 11, f'Qty {p["qty"]} · {fmt(p["L"])} x {fmt(p["Wd"])} x {fmt(p["T"])}', 7.2, "l",
                  "Mono", STONE6)
    y -= 34
    eyebrow(c, x, y, "Assembly sequence")
    seq = ["Band edges; drill per A-301/A-302.", "Sides to bottom deck, toe kick, rear rail.",
           "Tier 1 dividers, then shelf 1.", "Tier 2 dividers, then shelf 2.", "Tier 3 dividers, then top.",
           "Square up; fit back into rabbets.", "Glides; anti-tip kit on site."]
    for i, s in enumerate(seq, 1):
        y -= 13
        draw_text(c, x, y, f"{i}.", 7.5, "l", "MonoM", NAVY)
        draw_text(c, x + 14, y, s, 7.5, "l", "Geist", INK)


def eb_legend(c, x, y):
    c.setStrokeColor(NAVY)
    c.setLineWidth(2.6)
    c.setDash([])
    c.line(x, y + 3, x + 22, y + 3)
    draw_text(c, x + 28, y, "Edgeband, 3 mm PVC", 7.5, "l", "Geist", INK)
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.6)
    c.setDash([6, 1.5, 1.5, 1.5, 1.5, 1.5])
    c.line(x + 150, y + 3, x + 172, y + 3)
    c.setDash([])
    draw_text(c, x + 178, y, "Mating part location", 7.5, "l", "Geist", INK)
    c.setStrokeColor(INK)
    c.setLineWidth(0.5)
    c.setDash([3, 2])
    c.line(x + 300, y + 3, x + 322, y + 3)
    c.setDash([])
    draw_text(c, x + 328, y, "Hidden", 7.5, "l", "Geist", INK)


def part_title(c, x, y, mark):
    p = g.PART_BY_MARK[mark]
    draw_text(c, x, y, mark, 10, "l", "DispSB", NAVY)
    draw_text(c, x + 32, y, p["name"], 10, "l", "DispSB", INK)
    eyebrow(c, x + 32, y - 12, f'Qty {p["qty"]} · {fmt(p["T"])} thick · {g.MATERIALS[p["mat"]]["short"]} · scale 1:8',
            STONE6, 5.8)


def sheet_parts1(S, c):
    sheet_heading(c, "Part details", "Top, side, bottom deck, shelf")
    eb_legend(c, 590, PH - M - 26)
    v = part_rect("P01", W, D, ["L1", "L2", "W1", "W2"])
    v.text(W / 2, D / 2, "FRONT EDGE AT BOTTOM", 6, "m", "MonoM", STONE6, dy=-2)
    render_view(c, v, 80, 520)
    part_title(c, 80, 520 + D * v.k + 18, "P01")

    def shelf_marks(vv):
        for i in range(g.COLS - 1):
            x = g.divider_x(i) - T
            vv.rect(x, 0, x + T, g.INT_D, "phantom")
        vv.hchain([0] + [g.divider_x(i) - T + s for i in range(g.COLS - 1) for s in (0, T)] + [g.INT_W],
                  g.INT_D, 12, size=5.6)
    v3 = part_rect("P03", g.INT_W, g.INT_D, ["L1"], extra=shelf_marks)
    render_view(c, v3, 80, 300)
    part_title(c, 80, 300 + g.INT_D * v3.k + 44, "P03")
    v4 = part_rect("P04", g.INT_W, g.INT_D, ["L1"], extra=shelf_marks)
    render_view(c, v4, 80, 80)
    part_title(c, 80, 80 + g.INT_D * v4.k + 44, "P04")
    v2 = part_side()
    render_view(c, v2, 690, 140)
    part_title(c, 640, 140 + g.SIDE_H * v2.k + 44, "P02")
    draw_text(c, 690, 100, "Shown: right side, viewed from outside. Left side is the mirror.", 7, "l", "Geist", STONE6)
    v5 = rabbet_detail()
    render_view(c, v5, 830, 600)
    view_label(c, 760, 545, 8, "Rabbet", "Plan detail, scale 1:2")
    S.dxf_y = -170
    for vv, t, x in ((v, "P01 TOP", 0), (v2, "P02 SIDE (R, OUTSIDE)", 60), (v3, "P03 BOTTOM DECK", 90),
                     (v4, "P04 FIXED SHELF", 150), (v5, "RABBET DETAIL", 210)):
        S.to_dxf(vv, t, x)


def sheet_parts2(S, c):
    sheet_heading(c, "Part details", "Divider, toe kick, rear rail, back panel")
    eb_legend(c, 590, PH - M - 26)

    def back_marks(vv):
        x0 = T - g.BACK_T
        for zc in [B + T / 2] + [g.shelf_z(i) + T / 2 for i in range(g.TIERS - 1)]:
            vv.line(0, zc - B, g.INT_W + 2 * g.BACK_T, zc - B, "center")
        for t in range(g.TIERS):
            for i in range(g.COLS - 1):
                xc = g.divider_x(i) + T / 2 - x0
                vv.line(xc, g.tier_floor(t) - B, xc, g.tier_floor(t) + g.OPEN_H - B, "center")
        vv.hchain([0] + [g.divider_x(i) + T / 2 - x0 for i in range(g.COLS - 1)] + [g.INT_W + 2 * g.BACK_T],
                  g.SIDE_H - B, 12, size=5.6)
        vv.vchain([0, T / 2, g.shelf_z(0) + T / 2 - B, g.shelf_z(1) + T / 2 - B, g.SIDE_H - B],
                  g.INT_W + 2 * g.BACK_T, 14, size=5.6)
        vv.text((g.INT_W + 2 * g.BACK_T) / 2, 2.0, "SCREW LINES SHOWN AS CENTERLINES · VIEWED FROM INSIDE", 5.8, "m",
                "MonoM", STONE6)
    v8 = part_rect("P08", g.INT_W + 2 * g.BACK_T, g.SIDE_H - B, [], extra=back_marks)
    render_view(c, v8, 80, 370)
    part_title(c, 80, 370 + (g.SIDE_H - B) * v8.k + 34, "P08")
    v6 = part_rect("P06", g.INT_W, B, [])
    render_view(c, v6, 80, 220)
    part_title(c, 80, 220 + B * v6.k + 18, "P06")
    v7 = part_rect("P07", g.INT_W, B, [])
    render_view(c, v7, 80, 90)
    part_title(c, 80, 90 + B * v7.k + 18, "P07")
    v5 = part_rect("P05", g.INT_D, g.OPEN_H, ["W1"])
    v5.text(0.3, g.OPEN_H / 2, "FRONT", 5.8, "m", "MonoM", NAVY, angle=90, lift=-12)
    render_view(c, v5, 680, 520)
    part_title(c, 640, 520 + g.OPEN_H * v5.k + 18, "P05")
    x, y = 640, 470
    eyebrow(c, x, y, "Joinery and machining")
    items = [
        "Dividers: two 8 mm dowels each end into shelf or deck, glued. Align in one vertical line per column.",
        "Top, deck, shelves, toe kick and rear rail to sides: dowels plus 7 x 50 mm confirmat screws, "
        "3 per joint (2 at kick and rail). Cap exposed heads.",
        "Back panel: screwed into rabbets and along the centerlines shown, #6 x 5/8\" at 6\" o.c.",
        "Toe kick and rear rail are not edgebanded. Toe kick face in black or dark laminate if available.",
        "Glides: threaded inserts in side bottom edges at the locations on A-301.",
        "Tolerances: parts +/- 1/32\". Assembled carcass square within 1/16\" on diagonals.",
    ]
    for s in items:
        y -= 14
        draw_text(c, x, y, "·", 9, "l", "MonoM", NAVY)
        y = paragraph(c, x + 10, y, s, 330, 7.6, "Geist", INK, 10.5) + 10.5 - 4
    S.dxf_y = -230
    for vv, t, xx in ((v5, "P05 DIVIDER", 0), (v6, "P06 TOE KICK", 30), (v7, "P07 REAR RAIL", 90),
                      (v8, "P08 BACK PANEL (INSIDE FACE)", 150)):
        S.to_dxf(vv, t, xx)


def table(c, x, y, data, col_w, font_size=7.2, hdr_bg=PAPER1, zebra=False, total_row=False):
    st = ParagraphStyle("c", fontName="Geist", fontSize=font_size, leading=font_size * 1.3, textColor=INK)
    sth = ParagraphStyle("h", fontName="MonoM", fontSize=5.8, leading=7.5, textColor=STONE6)
    rows = []
    for i, r in enumerate(data):
        rows.append([Paragraph(str(cell).upper() if i == 0 else str(cell), sth if i == 0 else st) for cell in r])
    t = Table(rows, colWidths=col_w)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), hdr_bg),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, PAPER3),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if total_row:
        style += [("LINEABOVE", (0, -1), (-1, -1), 0.8, INK)]
    t.setStyle(TableStyle(style))
    w, h = t.wrapOn(c, sum(col_w), 1000)
    t.drawOn(c, x, y - h)
    return y - h


def cut_rows():
    rows = [["Mark", "Part", "Qty", "Length", "Width", "Thk", "Matl", "Edgeband", "Notes", "Sq ft"]]
    for p in g.PARTS:
        eb = {"P01": "All 4 edges", "P02": "Front, rear, notch", "P03": "Front", "P04": "Front",
              "P05": "Front", "P06": "None", "P07": "None", "P08": "None"}[p["mark"]]
        rows.append([p["mark"], p["name"], p["qty"], fmt(p["L"]), fmt(p["Wd"]), fmt(p["T"]), p["mat"], eb, p["notes"],
                     f'{p["sqft_total"]:.1f}'])
    return rows


def sheet_cutlist(S, c):
    sheet_heading(c, "Bill of materials", "Cut list, hardware and materials")
    y = PH - M - 52
    eyebrow(c, M, y, "Cut list · finished sizes, including edgeband")
    y = table(c, M, y - 8, cut_rows(), [32, 120, 26, 44, 44, 30, 32, 76, 492, 40])
    y -= 22
    eyebrow(c, M, y, "Hardware")
    hw = [["Mark", "Item", "Qty", "Notes"]]
    for h in g.HARDWARE:
        q = h["qty"] if h["qty"] is not None else f'{g.TOTAL_EB_IN / 12 * 1.1:.0f} LF'
        hw.append([h["mark"], h["item"], q, h["notes"]])
    y2 = table(c, M, y - 8, hw, [32, 250, 48, 230])
    # materials summary on the right
    x = M + 590
    eyebrow(c, x, y, "Material summary")
    m1 = sum(p["sqft_total"] for p in g.PARTS if p["mat"] == "M1")
    m2 = sum(p["sqft_total"] for p in g.PARTS if p["mat"] == "M2")
    summ = [["Code", "Material", "Net area", "Est. sheets"],
            ["M1", g.MATERIALS["M1"]["name"], f"{m1:.1f} sf", "2 @ 49\" x 97\""],
            ["M2", g.MATERIALS["M2"]["name"], f"{m2:.1f} sf", "1 @ 49\" x 97\""],
            ["EB", g.EDGEBAND, f"{g.TOTAL_EB_IN / 12:.1f} LF", f"{g.TOTAL_EB_IN / 12 * 1.1:.0f} LF w/ 10%"],
            ["", "Weight, empty / loaded (approx.)", f"{g.TOTAL_LB:.0f} lb", f"{g.LOADED_LB:.0f} lb"]]
    y3 = table(c, x, y - 8, summ, [30, 190, 60, 82], total_row=True)
    paragraph(c, x, y3 - 14, "Sheet counts are a nesting estimate for quoting. Fabricator to optimize. "
              "Color: by owner, to be confirmed. Quote standard TFM colors at no upcharge.", 360, 7.2, "Geist", STONE6, 10)


def sheet_rfq(S, c):
    sheet_heading(c, "Quotation", "Alternates and quote request")
    v = doors_elevation()
    render_view(c, v, 90, 380)
    view_label(c, 60, 320, 9, "ALT-1 lockable doors", "Front elevation, scale 1:8")
    y = 290
    eyebrow(c, M, y, "Alternates · price each separately, per cabinet")
    y -= 4
    for a in g.ALTERNATES:
        y -= 16
        draw_text(c, M, y, a["mark"], 8, "l", "MonoM", NAVY)
        draw_text(c, M + 50, y, a["title"], 8.5, "l", "GeistSB", INK)
        y = paragraph(c, M + 50, y - 11, a["desc"], 380, 7.5, "Geist", INK, 10) + 10 - 2
    x = 600
    y = PH - M - 62
    eyebrow(c, x, y, "Please quote")
    asks = [
        "Unit price for the base cabinet as drawn, at quantities of 1, 2 and 5.",
        "Each alternate (ALT-1 to ALT-5) as a separate add per cabinet.",
        "Freight to 1790 W 8th Ave, Hialeah, FL 33010, and whether it ships assembled or knock-down.",
        "Lead time from shop-drawing approval.",
        "Standard laminate colors available at no upcharge, and edgeband match.",
        "Warranty terms.",
        "Any change you recommend for cost or strength (for example 3/4\" dividers). Price it as a "
        "voluntary alternate; do not substitute in the base price.",
    ]
    for i, s in enumerate(asks, 1):
        y -= 14
        draw_text(c, x, y, f"{i}.", 8, "l", "MonoM", NAVY)
        y = paragraph(c, x + 16, y, s, 360, 8, "Geist", INK, 11) + 11 - 3
    y -= 24
    eyebrow(c, x, y, "Open items · owner to confirm before release")
    opens = [
        "Exact laptop model and size, with or without a protective case.",
        "Will laptops charge inside the cabinet? If yes, see ALT-2 and ALT-3.",
        "Doors and locks required? (ALT-1)",
        "Is 35\" a hard maximum (under a window or counter)? Glides add about 3/8\".",
        "Wall-mounted location, or freestanding with a finished back?",
        "Laminate color and number of cabinets.",
    ]
    for s in opens:
        y -= 14
        draw_text(c, x, y, "·", 9, "l", "MonoM", NAVY)
        y = paragraph(c, x + 12, y, s, 360, 8, "Geist", INK, 11) + 11 - 3
    y -= 24
    eyebrow(c, x, y, "Contact")
    y -= 15
    draw_text(c, x, y, "Office Furniture 4 Sale · +1 305 889 3364", 8.5, "l", "Geist", INK)
    draw_text(c, x, y - 12, "officefurniture4sale.com", 8.5, "l", "Geist", INK)
    S.dxf_y = -290
    S.to_dxf(v, "ALT-1 DOORS", 0)


def build(pdf_path, dxf_path):
    S = SheetSet(pdf_path)
    S.add("A-001", "Cover, design basis, notes", "As noted", sheet_cover)
    S.add("A-101", "Front elevation", "1:5 at 11 x 17", sheet_front)
    S.add("A-102", "Section A-A, side elevation, bay", "1:5 at 11 x 17", sheet_sections)
    S.add("A-103", "Top plan, plan section B-B", "1:5 at 11 x 17", sheet_plans)
    S.add("A-104", "Front elevation, loaded", "1:5 at 11 x 17", sheet_loaded)
    S.add("A-201", "Isometric views", "Not to scale", sheet_3d)
    S.add("A-202", "Exploded isometric", "Not to scale", sheet_exploded)
    S.add("A-301", "Part details 1", "1:8, 1:2 at 11 x 17", sheet_parts1)
    S.add("A-302", "Part details 2", "1:8 at 11 x 17", sheet_parts2)
    S.add("A-401", "Cut list and hardware", "None", sheet_cutlist)
    S.add("A-501", "Alternates, quote request", "1:8 at 11 x 17", sheet_rfq)
    S.build()
    S.dxf.save(dxf_path)
    return S


def parts_dxf(path):
    """Flat part outlines at 1:1 for CNC nesting, one of each unique part."""
    dx = Dxf()
    x = 0
    y = 0
    for p in g.PARTS:
        if p["mark"] == "P02":
            pts = [(yy, zz) for yy, zz in g.SIDE_PROFILE]
            seq = pts + [pts[0]]
            for (a, b), (cc, d) in zip(seq, seq[1:]):
                dx.line(x + a, y + b, x + cc, y + d, "OUTLINE")
            dx.line(x + g.D - g.BACK_T, y, x + g.D - g.BACK_T, y + g.SIDE_H, "HIDDEN")
            w_, h_ = g.D, g.SIDE_H
        else:
            w_, h_ = p["L"], p["Wd"]
            for (a, b), (cc, d) in [((0, 0), (w_, 0)), ((w_, 0), (w_, h_)), ((w_, h_), (0, h_)), ((0, h_), (0, 0))]:
                dx.line(x + a, y + b, x + cc, y + d, "OUTLINE")
        dx.text(x, y - 1.2, 0.8, f'{p["mark"]} {p["name"]}  QTY {p["qty"]}  T={fmt(p["T"])}  {p["mat"]}')
        x += w_ + 6
        if x > 120:
            x = 0
            y -= 45
    dx.save(path)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    build(os.path.join(OUT, "LC-60_Drawing_Set.pdf"), os.path.join(OUT, "LC-60_Drawings.dxf"))
    parts_dxf(os.path.join(OUT, "LC-60_Parts_CNC.dxf"))
    print("ok")
