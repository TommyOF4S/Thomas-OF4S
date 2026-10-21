"""Write tests/fixtures/sample_plan.pdf: a small plan drawn the way CET 16 draws a 2D
(panels as gray-filled outlines 2" thick, a flipped 0.1-scale page transform), with
known joints. Run: python tests/fixtures/make_sample_plan.py

Page 1 (0.285 pt per inch):
  spine y=0: 0-60, 60-120, 120-162, 162-186; up panels at x=0, 60, 120; down panel at x=60
    -> (0,0) L, (60,0) cross, (120,0) T, (162,0) straight; free ends at (186,0), (0,24),
       (60,24), (60,-24), (120,24)
  separate run y=100: 0-24, 24-48, 48-72 -> 2 straight joints, 2 free ends
  plus decoys: worksurfaces, pedestal outlines, a thick gray box, text
  height-change marks: a red dot (HMHL3953) on the straight joint at (162,0), a yellow dot
  (HMHL4753) on the straight joint at (48,100), and a black blob away from any joint (ignored)
Page 2 (0.335 pt per inch): one L of two 24" panels -> 1 L, 2 free ends

Totals across both pages are in EXPECTED.
"""

from pathlib import Path

EXPECTED = {"straight": 3, "l": 2, "tee": 1, "cross": 1, "ends": 9, "panels": 13,
            "widths": {24: 10, 42: 1, 60: 2},
            "height_changes": [("straight", "red"), ("straight", "yellow")]}
MARKS = [(162, 0, (1, 0, 0)), (48, 100, (1, 1, 0))]  # joint (inches on page 1) and dot color
DECOY = (100, 40, (0, 0, 0))  # a black blob nowhere near a joint, like CET's chair bases

GAP = 0.7  # half the post width, inches


def panel(axis, fixed, a, b, k):
    """Rectangle (x, y, w, h) in points for a panel between joint coords a..b."""
    lo, hi = a + GAP, b - GAP
    if axis == "H":
        return (lo * k, (fixed - 1) * k, (hi - lo) * k, 2 * k)
    return ((fixed - 1) * k, lo * k, 2 * k, (hi - lo) * k)


def path(x, y, w, h, fill, paint="B"):
    s = lambda v: f"{v * 10:.2f}"  # coordinates are written at 10x under a 0.1 cm
    pts = f"{s(x)} {s(y)} m {s(x + w)} {s(y)} l {s(x + w)} {s(y + h)} l {s(x)} {s(y + h)} l h"
    color = f"{fill[0]} {fill[1]} {fill[2]} rg " if fill else ""
    return f"{color}{pts} {paint}\n"


def dot(cx, cy, r, rgb):
    """A filled circle (four Bezier arcs), as CET draws a 2D circle."""
    s = lambda v: f"{v * 10:.2f}"
    c = 0.5523 * r
    return (f"{rgb[0]} {rgb[1]} {rgb[2]} rg {s(cx + r)} {s(cy)} m "
            f"{s(cx + r)} {s(cy + c)} {s(cx + c)} {s(cy + r)} {s(cx)} {s(cy + r)} c "
            f"{s(cx - c)} {s(cy + r)} {s(cx - r)} {s(cy + c)} {s(cx - r)} {s(cy)} c "
            f"{s(cx - r)} {s(cy - c)} {s(cx - c)} {s(cy - r)} {s(cx)} {s(cy - r)} c "
            f"{s(cx + c)} {s(cy - r)} {s(cx + r)} {s(cy - c)} {s(cx + r)} {s(cy)} c h f\n")


def page1(k=0.285, ox=100, oy=150):
    out = []
    panels = [("H", 0, 0, 60), ("H", 0, 60, 120), ("H", 0, 120, 162), ("H", 0, 162, 186),
              ("V", 0, 0, 24), ("V", 60, 0, 24), ("V", 60, -24, 0), ("V", 120, 0, 24),
              ("H", 100, 0, 24), ("H", 100, 24, 48), ("H", 100, 48, 72)]
    gray = (0.8627, 0.8627, 0.8627)
    for axis, fixed, a, b in panels:
        x, y, w, h = panel(axis, fixed, a, b, k)
        out.append(path(ox + x, oy + y, w, h, gray))
    # posts at joints (small gray squares, a different gray)
    for jx, jy in ((0, 0), (60, 0), (120, 0), (162, 0), (24, 100), (48, 100)):
        out.append(path(ox + (jx - 1) * k, oy + (jy - 1) * k, 2 * k, 2 * k, (0.7686, 0.7686, 0.7686)))
    # decoys: worksurfaces, stroke-only pedestal outlines, a thick gray box
    out.append(path(ox + 2 * k, oy + 2 * k, 56 * k, 24 * k, (0.9412, 0.9412, 0.7843), "f"))
    out.append(path(ox + 64 * k, oy + 2 * k, 54 * k, 24 * k, (0.9412, 0.9412, 0.7843), "f"))
    for i in range(4):
        out.append(path(ox + (10 + 15 * i) * k, oy + 40 * k, 1.25 * k, 24 * k, None, "S"))
    out.append(path(ox + 200 * k, oy + 10 * k, 30 * k, 7 * k, (0.784, 0.784, 0.784)))
    for jx, jy, rgb in MARKS + [DECOY]:
        out.append(dot(ox + jx * k, oy + jy * k, 3 * k, rgb))
    return "".join(out)


def page2(k=0.335, ox=120, oy=200):
    gray = (0.8627, 0.8627, 0.8627)
    out = []
    for axis, fixed, a, b in (("H", 0, 0, 24), ("V", 0, 0, 24)):
        x, y, w, h = panel(axis, fixed, a, b, k)
        out.append(path(ox + x, oy + y, w, h, gray))
    return "".join(out)


def content(body, label):
    return (f"q 1 0 0 -1 0 612 cm 0.1 0 0 0.1 0 0 cm 0 0 0 RG 5 w\n{body}Q\n"
            f"BT /F1 9 Tf 40 580 Td ({label}) Tj ET\n")


def build(path_out: Path):
    pages = [content(page1(), "Sample plan page 1"), content(page2(), "Sample plan page 2")]
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None,
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for body in pages:
        data = body.encode("latin-1")
        objs.append(f"<< /Length {len(data)} >>\nstream\n{body}endstream")
        content_id = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 792 612] /Contents {content_id} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path_out.write_bytes(out)


if __name__ == "__main__":
    build(Path(__file__).with_name("sample_plan.pdf"))
