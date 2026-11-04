"""Regenerate the whole LC-60 package from geometry.py.

usage: python3 build.py [path/to/three.min.js]
  three.min.js (r128) is only needed to refresh the 3D renders; without it the existing
  PNGs in out/renders are reused.
Outputs land in ../out:
  LC-60_Drawing_Set.pdf   11-sheet drawing set for quotation (11 x 17)
  LC-60_Drawings.dxf      all orthographic views and part details at 1:1 (inches)
  LC-60_Parts_CNC.dxf     flat part outlines at 1:1 for nesting
  LC-60_Cut_List.xlsx/csv cut list, hardware, materials, alternates
  sheets/A-xxx.png        sheet images (for the web viewer)
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out")
sys.path.insert(0, HERE)

import cutlist  # noqa: E402
import drawings  # noqa: E402


def main():
    os.makedirs(os.path.join(OUT, "sheets"), exist_ok=True)
    if len(sys.argv) > 1:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, os.path.join(HERE, "build_renders.py"), sys.argv[1], tmp], check=True)
    pdf = os.path.join(OUT, "LC-60_Drawing_Set.pdf")
    S = drawings.build(pdf, os.path.join(OUT, "LC-60_Drawings.dxf"))
    drawings.parts_dxf(os.path.join(OUT, "LC-60_Parts_CNC.dxf"))
    cutlist.build(os.path.join(OUT, "LC-60_Cut_List.xlsx"), os.path.join(OUT, "LC-60_Cut_List.csv"))
    # sheet images
    tmp_prefix = os.path.join(OUT, "sheets", "_p")
    subprocess.run(["pdftoppm", "-r", "130", "-png", pdf, tmp_prefix], check=True)
    files = sorted(f for f in os.listdir(os.path.join(OUT, "sheets")) if f.startswith("_p"))
    for f, (num, *_rest) in zip(files, S.pages):
        os.replace(os.path.join(OUT, "sheets", f), os.path.join(OUT, "sheets", f"{num}.png"))
    build_viewer(S)
    print("built", len(S.pages), "sheets")


def build_viewer(S):
    import html
    import json
    import geometry as g
    from geometry import fmt
    esc = html.escape
    t = open(os.path.join(HERE, "viewer_template.html")).read()
    sheets = [(num, title) for num, title, *_ in S.pages]
    btns = "".join(f'<button data-sheet="{n}" aria-current="false"><span>{n}</span><em>{esc(tt)}</em></button>'
                   for n, tt in sheets)
    cut = "".join(
        f'<tr><td class="m">{p["mark"]}</td><td>{esc(p["name"])}</td><td class="n">{p["qty"]}</td>'
        f'<td class="n">{esc(fmt(p["L"]))}</td><td class="n">{esc(fmt(p["Wd"]))}</td><td class="n">{esc(fmt(p["T"]))}</td>'
        f'<td class="n">{p["mat"]}</td><td>{cutlist.EB_TEXT[p["mark"]]}</td><td class="note">{esc(p["notes"])}</td></tr>'
        for p in g.PARTS)
    m1 = sum(p["sqft_total"] for p in g.PARTS if p["mat"] == "M1")
    m2 = sum(p["sqft_total"] for p in g.PARTS if p["mat"] == "M2")
    totals = (f'{sum(p["qty"] for p in g.PARTS)} pieces · M1 {m1:.1f} sq ft (about two 49" x 97" sheets) · '
              f'M2 {m2:.1f} sq ft · edgeband {g.TOTAL_EB_IN / 12:.0f} LF net')
    hw = "".join(
        f'<tr><td class="m">{h["mark"]}</td><td>{esc(h["item"])}</td>'
        f'<td class="n">{h["qty"] if h["qty"] is not None else f"{g.TOTAL_EB_IN / 12 * 1.1:.0f} LF"}</td>'
        f'<td class="note">{esc(h["notes"])}</td></tr>' for h in g.HARDWARE)
    alts = "".join(f'<li><span>{a["mark"]}</span><div><b>{esc(a["title"])}</b><p>{esc(a["desc"])}</p></div></li>'
                   for a in g.ALTERNATES)
    t = (t.replace("__SHEET_BUTTONS__", btns).replace("__CUT_ROWS__", cut).replace("__CUT_TOTALS__", esc(totals))
          .replace("__HW_ROWS__", hw).replace("__ALT_ROWS__", alts).replace("__EMPTY_LB__", f"{g.TOTAL_LB:.0f}")
          .replace("__CAB__", open(os.path.join(HERE, "cabinet3d.js")).read())
          .replace("__DATA__", json.dumps(g.to_json())).replace("__SHEETS__", json.dumps(sheets)))
    open(os.path.join(OUT, "viewer.html"), "w").write(t)


if __name__ == "__main__":
    main()
