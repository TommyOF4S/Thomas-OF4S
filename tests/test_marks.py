"""Reading pink dashes and colored dots from 2D images, in Python and in the hosted page's JS."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from devon_quote.bom import BomLine, load_bom
from devon_quote.catalog import load_catalog
from devon_quote.mapper import Mapper
from devon_quote.marks import MarksSummary, image_marks, read_marks, summarize
from devon_quote.pricing import estimate
from devon_quote.report import write_report
from devon_quote.service import find_template

ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / "tests" / "fixtures" / "sample_marks.png"
SAMPLE = ROOT / "tests" / "fixtures" / "sample_ais_divi.sif"
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
from make_sample_marks import EXPECTED  # noqa: E402

TEMPLATE = find_template()
needs_template = pytest.mark.skipif(TEMPLATE is None, reason="put the Devon calculator .xlsm in templates/")


def _node_has(mod):
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", f"require('{mod}')"], capture_output=True).returncode == 0


needs_node = pytest.mark.skipif(not shutil.which("node"), reason="needs node")


def _summary(s):
    return {"pink": s.pink, "dots": s.dots, "off_panel": s.off_panel}


def test_reads_sample_marks():
    res = read_marks(IMAGE)
    assert _summary(summarize(res)) == EXPECTED


def test_survives_jpeg_and_scaling(tmp_path):
    img = Image.open(IMAGE).convert("RGB")
    img.save(tmp_path / "m.jpg", quality=80)
    assert _summary(summarize(read_marks(tmp_path / "m.jpg"))) == EXPECTED
    img.resize((img.width * 2, img.height * 2), Image.LANCZOS).save(tmp_path / "big.png")
    assert _summary(summarize(read_marks(tmp_path / "big.png"))) == EXPECTED


def test_plain_drawing_has_no_marks():
    img = Image.open(IMAGE).convert("RGBA")
    a = np.asarray(img).copy()
    # paint every saturated pixel white: what's left is the drawing and the decoys' black parts
    sat = a[..., :3].max(-1).astype(int) - a[..., :3].min(-1).astype(int) > 60
    a[sat] = (255, 255, 255, 255)
    s = summarize([image_marks(a)])
    assert s.pink == 0 and s.dots == {}


@needs_node
@pytest.mark.parametrize("scale", [1, 2])
def test_js_matches_python_pixel_for_pixel(tmp_path, scale):
    img = Image.open(IMAGE).convert("RGBA")
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    raw = tmp_path / "m.rgba"
    raw.write_bytes(img.tobytes())
    out = json.loads(subprocess.run(["node", str(ROOT / "tests" / "marks_harness.js"), str(raw), str(img.width), str(img.height)],
                                    capture_output=True, text=True, check=True).stdout)
    py = image_marks(np.asarray(img))
    as_list = lambda ms: [(m.kind, m.color, m.x, m.y, m.size, m.on_panel) for m in ms]
    js_list = lambda ms: [(m["kind"], m["color"], m["x"], m["y"], m["size"], m["onPanel"]) for m in ms]
    assert js_list(out["marks"]["dashes"]) == as_list(py.dashes)
    assert js_list(out["marks"]["dots"]) == as_list(py.dots)
    s = out["summary"]
    assert {"pink": s["pink"], "dots": s["dots"], "off_panel": s["offPanel"]} == EXPECTED


def _two_way_lines(n):
    return [BomLine("P-DLFRPM5024", "Divi Linear Panel - NPWR - 50H x 24W", 10),
            BomLine("P-DLPF250", "Divi Linear Post Filler - 2 -Way 50H", n),
            BomLine("P-DLPF350", "Divi Linear Post Filler - 3 Way - 50H", 1)]


@needs_template
def test_pink_dashes_add_panel_to_panel_connectors():
    # AIS lists no part for straight joints: 2-way posts stay corners and each pink dash adds an HMP213
    cat = load_catalog(TEMPLATE)
    marks = MarksSummary(pink=5, dots={"red": 2, "purple": 1})
    res = Mapper(cat).map(_two_way_lines(7), None, marks)
    q = res.quantities
    assert q["HMP213.48"] == 5 and q["HMA130.53"] == 7
    assert q["HMA137.53"] == 1
    assert q["HMHL3953"] == 2 and q["HMHL5367"] == 1
    assert res.warnings == []


@needs_template
def test_no_marks_quotes_no_panel_to_panel_connectors():
    cat = load_catalog(TEMPLATE)
    res = Mapper(cat).map(_two_way_lines(7), None, MarksSummary())
    assert res.quantities["HMA130.53"] == 7 and "HMP213.48" not in res.quantities
    assert any("doesn't list straight panel-to-panel joints" in w for w in res.warnings)


@needs_template
@pytest.mark.skipif(not (shutil.which("node") and _node_has("jszip")), reason="needs node with jszip")
def test_js_quote_with_image_marks_matches_python(tmp_path):
    marks = summarize(read_marks(IMAGE))
    out = tmp_path / "q.xlsx"
    js = json.loads(subprocess.run(
        ["node", str(ROOT / "tests" / "engine_harness.js"), str(TEMPLATE), str(SAMPLE), str(out),
         json.dumps({"marks": {"pink": marks.pink, "dots": marks.dots, "offPanel": marks.off_panel}, "project": "Marks"})],
        capture_output=True, text=True, check=True).stdout)
    cat = load_catalog(TEMPLATE)
    lines = load_bom(SAMPLE)
    res = Mapper(cat).map(lines, None, marks)
    assert js["quantities"] == res.quantities
    assert js["warnings"] == res.warnings
    rp = tmp_path / "r.md"
    write_report(rp, project="Marks", bom_file=SAMPLE.name, quote_file="q.xlsx", catalog=cat, grade=0,
                 lines=lines, result=res, est=estimate(cat, res.quantities, 0, 0, None))
    strip = lambda t: [l for l in t.splitlines() if "overrides.csv" not in l and "save a correction" not in l]
    assert strip(js["report"]) == strip(rp.read_text(encoding="utf-8"))
