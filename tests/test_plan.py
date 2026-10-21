"""Reading panel joints off a CET 2D plan (PDF), in Python and in the hosted page's JS."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from devon_quote.bom import BomLine, load_bom
from devon_quote.catalog import load_catalog
from devon_quote.mapper import Mapper
from devon_quote.plan import Rect, Shape, Word, analyze_pdf, analyze_rects, nominal_width
from devon_quote.pricing import estimate
from devon_quote.report import write_report
from devon_quote.service import find_template

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "tests" / "fixtures" / "sample_plan.pdf"
SAMPLE = ROOT / "tests" / "fixtures" / "sample_ais_divi.sif"
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
from make_sample_plan import EXPECTED  # noqa: E402


def _node_has(mod):
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", f"require('{mod}')"], capture_output=True).returncode == 0


needs_pdfjs = pytest.mark.skipif(not (_node_has("pdfjs-dist/legacy/build/pdf.js") and _node_has("jszip")),
                                 reason="needs node with pdfjs-dist@3 and jszip on NODE_PATH")
TEMPLATE = find_template()
needs_template = pytest.mark.skipif(TEMPLATE is None, reason="put the Devon calculator .xlsm in templates/")


def check_expected(counts, widths, panels):
    for k in ("straight", "l", "tee", "cross", "ends"):
        assert counts[k] == EXPECTED[k], k
    assert counts.get("angled", 0) == 0 and counts.get("other", 0) == 0
    assert {int(k): v for k, v in widths.items()} == EXPECTED["widths"]
    assert panels == EXPECTED["panels"]


def test_python_reads_sample_plan():
    res = analyze_pdf(PLAN)
    check_expected(res.counts, res.widths, res.panels)
    assert [(h.joint, h.heights, h.label) for h in res.height_changes] == EXPECTED["height_changes"]
    assert [p["thickness"] for p in res.pages] == [0.57, 0.67]  # two drawing scales, detected per page


@needs_pdfjs
def test_js_reads_sample_plan():
    out = json.loads(subprocess.run(["node", str(ROOT / "tests" / "plan_harness.js"), str(PLAN)],
                                    capture_output=True, text=True, check=True).stdout)
    check_expected(out["counts"], out["widths"], out["panels"])
    assert [(h["joint"], tuple(h["heights"]), h["label"]) for h in out["heightChanges"]] == EXPECTED["height_changes"]


def test_nominal_widths():
    assert nominal_width(6.44, 0.57) == 24
    assert nominal_width(11.55, 0.57) == 42
    assert nominal_width(16.66, 0.57) == 60
    assert nominal_width(9.0, 0.57) is None


def test_corner_from_raw_rects():
    t = 0.57
    gray = (0.86, 0.86, 0.86)
    # a 24" panel along x whose right end meets the bottom end of a 24" panel along y
    rects = [Rect(0, 0, 6.44, t, gray), Rect(6.6, -6.0, 6.6 + t, 0.3, gray)]
    res = analyze_rects([rects])
    assert res.panels == 2 and res.counts["l"] == 1 and res.counts["ends"] == 2


@needs_template
def test_plan_replaces_post_counts():
    cat = load_catalog(TEMPLATE)
    lines = load_bom(SAMPLE)
    plan = analyze_pdf(PLAN)
    res = Mapper(cat).map(lines, plan)
    q = res.quantities
    # 3 straight joints, 2 of them marked as height changes: the kits replace their connectors
    assert q["HMP213.48"] == 1 and q["HMA224.48"] == 2 and q["HMHL4753"] == 1 and q["HMHL3953"] == 1
    assert q["HMA130.53"] == 2 and q["HMA137.53"] == 1
    assert q["HMC132.48"] == 1 and q["HMA128.53"] == 9
    posts = [m for m in res.mappings if m.source.part.startswith(("P-DLPF", "P-DLSEOR"))]
    assert posts and all(m.targets == [] and m.status == "ok" for m in posts)
    assert any("same revision" in w for w in res.warnings)  # sample plan != sample BOM
    # without a plan nothing changes
    assert "HMP213.48" not in Mapper(cat).map(lines).quantities


@needs_template
def test_plan_matching_bom_has_no_revision_warning():
    cat = load_catalog(TEMPLATE)
    lines = [BomLine("P-DLFRPM5024", "Divi Linear Panel - NPWR - 50H x 24W", 10),
             BomLine("P-DLFRPM5042", "Divi Linear Panel - NPWR - 50H x 42W", 1),
             BomLine("P-DLFRPM5060", "Divi Linear Panel - NPWR - 50H x 60W", 2),
             BomLine("P-DLPF250", "Divi Linear Post Filler - 2 -Way 50H", 5),
             BomLine("P-DLPF350", "Divi Linear Post Filler - 3 Way - 50H", 1),
             BomLine("P-DLPF450", "Divi Linear Post Filler - 4 Way - 50H", 1),
             BomLine("P-DLSEOR", "Divi Linear Base - End of Run Shroud", 9)]
    res = Mapper(cat).map(lines, analyze_pdf(PLAN))
    assert res.warnings == []


@needs_template
@needs_pdfjs
def test_js_quote_with_plan_matches_python(tmp_path):
    out = tmp_path / "q.xlsx"
    p = subprocess.run(["node", str(ROOT / "tests" / "engine_harness.js"), str(TEMPLATE), str(SAMPLE), str(out),
                        json.dumps({"plan": str(PLAN), "delivery": 0, "project": "Plan"})],
                       capture_output=True, text=True, check=True)
    js = json.loads(p.stdout)
    cat = load_catalog(TEMPLATE)
    lines = load_bom(SAMPLE)
    res = Mapper(cat).map(lines, analyze_pdf(PLAN))
    assert js["quantities"] == res.quantities
    assert js["warnings"] == res.warnings
    assert [m[:3] for m in js["mappings"]] == [[m.source.part, m.status, m.note] for m in res.mappings]
    rp = tmp_path / "r.md"
    write_report(rp, project="Plan", bom_file=SAMPLE.name, quote_file="q.xlsx", catalog=cat, grade=0,
                 lines=lines, result=res, est=estimate(cat, res.quantities, 0, 0, None))
    strip = lambda t: [l for l in t.splitlines() if "overrides.csv" not in l and "save a correction" not in l]
    assert strip(js["report"]) == strip(rp.read_text(encoding="utf-8"))


# ---- height-change marks: edge cases, checked in Python and (when Node is set up) in JS

T = 0.57
GRAY = (0.86, 0.86, 0.86)
RED = (1.0, 0.0, 0.0)


def _run(y=0.0):
    """Two 24" panels in a straight line along x at height y: joint near x=6.88, two free ends."""
    return [Rect(0, y, 6.44, y + T, GRAY), Rect(6.86, y, 13.3, y + T, GRAY)]


def _corner():
    return [Rect(20, 0, 26.44, T, GRAY), Rect(26.6, -6.0, 26.6 + T, 0.3, GRAY)]


def _dot(x, y, r=0.6):
    return Shape(x - r, y - r, x + r, y + r, RED)


CASES = [
    # (name, rects, shapes, words, bom heights (Divi), expected parts, expected warning snippets)
    ("labeled on straight", _run(), [_dot(6.65, 0.28)], [Word("47/53", 9, 3)], [50], {"HMA224.48": 1, "HMHL4753": 1}, []),
    ("no label, two BOM heights", _run(), [_dot(6.65, 0.28)], [], [50, 42], {"HMA224.48": 1, "HMHL4753": 1}, ["no height label; used the BOM's two heights"]),
    ("no label, one BOM height", _run(), [_dot(6.65, 0.28)], [], [50], {}, ["no height label like 47/53, so it was not quoted"]),
    ("not on a joint", _run(), [_dot(30, 30)], [Word("47/53", 31, 31)], [50], {}, ["isn't on a panel joint"]),
    ("no filler made", _run(), [_dot(6.65, 0.28)], [Word("39 to 85", 9, 3)], [50], {"HMA224.80": 1}, ["no filler strip for 39\" to 85\""]),
    ("on a corner", _corner(), [_dot(26.9, 0.28)], [Word("47-53", 29, 3)], [50], {"HMA224.48": 1, "HMHL4753": 1}, ["sits on a corner"]),
    ("same height", _run(), [_dot(6.65, 0.28)], [Word("50/53", 9, 3)], [50], {}, ["both heights are 53\"H"]),
]


def _lines(heights):
    out = []
    for h in heights:
        out.append(BomLine(f"P-DLFRPM{h}24", f"Divi Linear Panel - NPWR - {h}H x 24W", 2))
    return out


@needs_template
@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_height_marks(case, tmp_path):
    name, rects, shapes, words, heights, parts, snippets = case
    cat = load_catalog(TEMPLATE)
    plan = analyze_rects([rects], [(shapes, words)])
    res = Mapper(cat).map(_lines(heights), plan)
    got = {p: q for k, p, q in res.plan_parts if k in ("change_height", "filler")}
    assert got == parts
    for snip in snippets:
        assert any(snip in w for w in res.warnings), (snip, res.warnings)

    if _node_has("jszip"):
        payload = {
            "calc": str(TEMPLATE),
            "pages": [[{"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1, "fill": list(r.fill) if r.fill else None} for r in rects]],
            "extras": [[[{"x0": s.x0, "y0": s.y0, "x1": s.x1, "y1": s.y1, "fill": list(s.fill)} for s in shapes],
                        [{"text": w.text, "x": w.x, "y": w.y} for w in words]]],
            "lines": [{"part": l.part, "description": l.description, "qty": l.qty} for l in _lines(heights)],
        }
        out = json.loads(subprocess.run(["node", str(ROOT / "tests" / "mark_harness.js")], input=json.dumps(payload),
                                        capture_output=True, text=True, check=True).stdout)
        assert out["warnings"] == res.warnings
        assert out["quantities"] == res.quantities
