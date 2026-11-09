"""Build a local render page and capture the 3D views with headless Chromium.

usage: python3 build_renders.py <three.min.js> <workdir>
PNGs land in ../out/renders/.
"""
import json
import os
import subprocess
import sys

import geometry as g

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out", "renders")

CALLOUTS = [  # label, mark, anchor fractions within the part box (fx, fy, fz), dx, dy (px)
    ("Top", "P01", (0.25, 0.5, 1.0), -130, -30),
    ("Back", "P08", (0.04, 1.0, 0.92), -150, -10),
    ("Side L", "P02", (0.0, 0.55, 0.45), -110, 70),
    ("Side R", "P02", (0.0, 0.6, 0.6), 130, 0),
    ("Shelf 2", "P04", (0.12, 0.15, 1.0), -170, 0),
    ("Shelf 1", "P04", (0.12, 0.15, 1.0), -170, 0),
    ("Bottom deck", "P03", (0.12, 0.15, 1.0), -170, 0),
    ("Divider t3-3", "P05", (0.0, 0.4, 0.6), 150, -50),
    ("Toe kick", "P06", (0.55, 0.0, 0.5), 190, -20),
    ("Rear rail", "P07", (0.92, 0.0, 0.9), 170, -40),
    ("Door L", "P09", (0.5, 0.0, 0.3), -150, 30),
]

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>
 html,body{margin:0;height:100%;background:#ffffff;font-family:Geist,Helvetica,Arial,sans-serif}
 #v{position:absolute;inset:0}
 svg{position:absolute;inset:0;pointer-events:none}
 .b{fill:#ffffff;stroke:#2d4a6e;stroke-width:2}
 .t{font:600 15px Helvetica,Arial,sans-serif;fill:#2d4a6e;text-anchor:middle;dominant-baseline:central}
 .n{font:500 13px Helvetica,Arial,sans-serif;fill:#1a1814}
 .l{stroke:#2d4a6e;stroke-width:1.4;fill:none}
</style></head><body><div id="v"></div><svg id="o" width="1500" height="1000"></svg>
<script>__THREE__</script>
<script>__CAB__</script>
<script>
const DATA = __DATA__;
const CALLOUTS = __CALLOUTS__;
const NAMES = __NAMES__;
const cab = Cabinet3D.create(document.getElementById('v'), DATA,
  {ortho:true, instant:true, interactive:false, preserve:true, pixelRatio:2,
   palette:{bg:0xffffff}});
window.show = function(o){
  cab.setDoors(o.doors || 'closed');
  cab.setMode(o.mode);
  cab.setView(o.view);
  cab.camera.zoom = o.zoom || 1.55; cab.camera.updateProjectionMatrix();
  if (o.lift){ cab.camera.position.y += o.lift; cab.camera.updateMatrixWorld(); }
  cab.renderNow();
  const svg = document.getElementById('o'); svg.innerHTML = '';
  if (!o.callouts) return;
  let h = '';
  CALLOUTS.forEach(([label, mark, f, dx, dy]) => {
    const a = cab.partAnchor(label, f); if (!a) return;
    const bx = a[0]+dx, by = a[1]+dy;
    h += `<circle cx="${a[0]}" cy="${a[1]}" r="3" fill="#2d4a6e"/>`;
    h += `<line class="l" x1="${a[0]}" y1="${a[1]}" x2="${bx}" y2="${by}"/>`;
    h += `<circle class="b" cx="${bx}" cy="${by}" r="19"/><text class="t" x="${bx}" y="${by}">${mark}</text>`;
    const left = dx < 0;
    h += `<text class="n" x="${bx + (left?-26:26)}" y="${by+4}" text-anchor="${left?'end':'start'}">${NAMES[mark]}</text>`;
  });
  svg.innerHTML = h;
};
window.ready = true;
</script></body></html>"""


def main():
    three_path, work = sys.argv[1], sys.argv[2]
    os.makedirs(OUT, exist_ok=True)
    names = {p["mark"]: p["name"].split(" (")[0] for p in g.PARTS}
    html = (PAGE
            .replace("__THREE__", open(three_path).read())
            .replace("__CAB__", open(os.path.join(HERE, "cabinet3d.js")).read())
            .replace("__DATA__", json.dumps(g.to_json()))
            .replace("__CALLOUTS__", json.dumps(CALLOUTS))
            .replace("__NAMES__", json.dumps(names)))
    page = os.path.join(work, "render.html")
    open(page, "w").write(html)
    subprocess.run(["node", os.path.join(HERE, "render.js"), page, OUT], check=True)


if __name__ == "__main__":
    main()
