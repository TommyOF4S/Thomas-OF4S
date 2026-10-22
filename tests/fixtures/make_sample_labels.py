"""Write tests/fixtures/sample_plan_labels.pdf: a 2-station AIS Divi pod drawn the way CET 16 exports
a 2D with panel labels on (flipped 0.1-scale page transform, each panel a gray body with end caps,
labels as real text, the vertical ones running up the page), plus sample_labels.csv, its BOM.

The pod (inches): a back run of 42"H panels (B4230, B4242, B4230, B4242) with 66"H returns
(A6660) at x=0, 72 and 144, and 66"H fronts (A6630) on the two left returns. Heights change at the
top-left corner, the 3-way at x=72 and the top-right corner: three 39"-to-67" filler strips
(HMHL3967) in Devon terms. CET's post and worksurface tags (PF2-66, WS-30/60) are decoys.

Run: python tests/fixtures/make_sample_labels.py
"""

from pathlib import Path

K = 2.88  # points per inch, as CET scales a small pod onto a letter sheet
OX, OY = 180, 162  # pod origin on the page (top-down points)
GAP = 0.7  # half the post width, inches
SIZE = 17.2  # label height in points

# (axis, fixed, a, b, label): panels between joint coordinates a..b, inches
PANELS = [("H", 0, 0, 30, "B4230"), ("H", 0, 30, 72, "B4242"), ("H", 0, 72, 102, "B4230"), ("H", 0, 102, 144, "B4242"),
          ("V", 0, 0, 60, "A6660"), ("V", 72, 0, 60, "A6660"), ("V", 144, 0, 60, "A6660"),
          ("H", 60, 0, 30, "A6630"), ("H", 60, 72, 102, "A6630")]
POSTS = [(0, 0), (30, 0), (72, 0), (102, 0), (144, 0), (0, 60), (72, 60)]
DECOYS = [("PF2-66", "V", -12, 6), ("PF3-66", "H", 66, -12), ("PF2-66", "H", 144, -12), ("PF2-66", "H", -6, 70),
          ("WS-30/60", "V", 26, 30), ("WS-24/42", "H", 50, 20), ("SEOR", "H", 36, 64)]

EXPECTED = {"panels": 9, "labeled": 9, "counts": {"straight": 2, "l": 4, "tee": 1, "ends": 3},
            "parts": [("straight", "HMP213.34", 2), ("l", "HMA130.67", 4), ("tee", "HMA137.67", 1),
                      ("ends", "HMA128.67", 3), ("filler", "HMHL3967", 3)]}

BOM = """Part Number,Description,Qty
P-DLFRPM4230,Divi Linear Panel - NPWR - 42H x 30W,2
P-DLFRPM4242,Divi Linear Panel - NPWR - 42H x 42W,2
P-DLFRPM6630,Divi Linear Panel - NPWR - 66H x 30W,2
P-DLFRPM6660,Divi Linear Panel - NPWR - 66H x 60W,3
P-DLPF266,Divi Linear Post Filler - 2 -Way 66H,4
P-DLPF366,Divi Linear Post Filler - 3 Way - 66H,1
P-DLSEOR,Divi Linear Base - End of Run Shroud,3
"""

s = lambda v: f"{v * 10:.2f}"  # coordinates are written at 10x under the 0.1 scale


def rect(x, y, w, h, fill):
    return (f"{fill} {fill} {fill} rg {s(x)} {s(y)} m {s(x + w)} {s(y)} l {s(x + w)} {s(y + h)} l "
            f"{s(x)} {s(y + h)} l h B\n")


def panel(axis, fixed, a, b):
    """CET draws a panel as a gray body with a darker 0.73" cap at each end."""
    lo, hi = a + GAP, b - GAP
    cap = 0.73
    out = []
    for p0, p1, fill in ((lo, lo + cap, 0.8196), (lo + cap, hi - cap, 0.8627), (hi - cap, hi, 0.8196)):
        if axis == "H":
            out.append(rect(OX + p0 * K, OY + (fixed - 1) * K, (p1 - p0) * K, 2 * K, fill))
        else:
            out.append(rect(OX + (fixed - 1) * K, OY + p0 * K, 2 * K, (p1 - p0) * K, fill))
    return "".join(out)


def text(t, axis, cx, cy):
    """A label centered at (cx, cy) points. Under the flipped page, CET un-flips each label with its text matrix."""
    w = len(t) * 0.6 * SIZE
    if axis == "H":
        return f"0 g BT /F1 172 Tf 1 0 0 -1 {s(cx - w / 2)} {s(cy + 0.3 * SIZE)} Tm ({t}) Tj ET\n"
    return f"0 g BT /F1 172 Tf 0 -1 -1 0 {s(cx + 0.3 * SIZE)} {s(cy + w / 2)} Tm ({t}) Tj ET\n"  # reads up the page


def body():
    out = [panel(a, f, lo, hi) for a, f, lo, hi, _ in PANELS]
    out += [rect(OX + (x - 1) * K, OY + (y - 1) * K, 2 * K, 2 * K, 0.7686) for x, y in POSTS]
    for axis, fixed, a, b, label in PANELS:
        mid = (a + b) / 2
        if axis == "H":
            out.append(text(label, "H", OX + mid * K, OY + (fixed + (8 if fixed else -7)) * K))
        else:
            out.append(text(label, "V", OX + (fixed - 7) * K, OY + mid * K))
    for t, axis, x, y in DECOYS:
        out.append(text(t, axis, OX + x * K, OY + y * K))
    return "".join(out)


def build(path_out: Path):
    content = f"q 1 0 0 -1 0 612 cm 0.1 0 0 0.1 0 0 cm 0 0 0 RG 3 w\n{body()}Q\n"
    data = content.encode("latin-1")
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 792 612] /Contents 5 0 R /Resources << /Font << /F1 3 0 R >> >> >>",
            f"<< /Length {len(data)} >>\nstream\n{content}endstream"]
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
    here = Path(__file__).parent
    build(here / "sample_plan_labels.pdf")
    (here / "sample_labels.csv").write_text(BOM, encoding="utf-8")
