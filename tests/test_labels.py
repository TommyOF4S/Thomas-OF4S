"""Panel heights from CET's panel labels (A6660 = 66"H x 60"W) on a 2D PDF, in Python and the hosted page's JS."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from devon_quote.bom import BomLine, load_bom
from devon_quote.catalog import load_catalog
from devon_quote.mapper import Mapper
from devon_quote.plan import Rect, Shape, Word, analyze_pdf, analyze_rects, read_pdf
from devon_quote.pricing import estimate
from devon_quote.report import write_report

from test_plan import ROOT, TEMPLATE, needs_pdfjs, needs_template, _node_has

sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
from make_sample_labels import EXPECTED  # noqa: E402

PLAN = ROOT / "tests" / "fixtures" / "sample_plan_labels.pdf"
BOM = ROOT / "tests" / "fixtures" / "sample_labels.csv"


def test_reads_labels_in_reading_order():
    words = [w.text for w in read_pdf(PLAN)[3][0]]
    assert words.count("A6660") == 3 and "0666A" not in words  # vertical labels read up the page, not reversed
    res = analyze_pdf(PLAN)
    assert res.panels == EXPECTED["panels"]
    assert {k: v for k, v in res.counts.items() if v} == EXPECTED["counts"]
    assert sum(l.matched for l in res.labels) == EXPECTED["labeled"]
    assert res.pages[0]["thickness"] > 5  # drawn at a larger scale than the IFB plans


@needs_template
def test_label_heights_give_fillers_and_tall_connectors():
    res = Mapper(load_catalog(TEMPLATE)).map(load_bom(BOM), analyze_pdf(PLAN))
    assert res.plan_parts == EXPECTED["parts"]
    assert res.warnings == []
    assert len(res.height_points) == 3


@needs_pdfjs
def test_js_reads_labels():
    out = json.loads(subprocess.run(["node", str(ROOT / "tests" / "plan_harness.js"), str(PLAN)],
                                    capture_output=True, text=True, check=True).stdout)
    py = analyze_pdf(PLAN)
    assert [(l["text"], l["matched"]) for l in out["labels"]] == [(l.text, l.matched) for l in py.labels]
    key = lambda panels: sorted(tuple(p) for p in panels)
    assert sorted((j["kind"], key(j["panels"])) for j in out["joints"]) == sorted((j.kind, key(j.panels)) for j in py.joints)


@needs_template
@needs_pdfjs
def test_js_quote_with_labels_matches_python(tmp_path):
    out = tmp_path / "q.xlsx"
    p = subprocess.run(["node", str(ROOT / "tests" / "engine_harness.js"), str(TEMPLATE), str(BOM), str(out),
                        json.dumps({"plan": str(PLAN), "delivery": 0, "project": "Labels"})],
                       capture_output=True, text=True, check=True)
    js = json.loads(p.stdout)
    cat = load_catalog(TEMPLATE)
    lines = load_bom(BOM)
    res = Mapper(cat).map(lines, analyze_pdf(PLAN))
    assert js["quantities"] == res.quantities
    assert js["warnings"] == res.warnings
    rp = tmp_path / "r.md"
    write_report(rp, project="Labels", bom_file=BOM.name, quote_file="q.xlsx", catalog=cat, grade=0,
                 lines=lines, result=res, est=estimate(cat, res.quantities, 0, 0, None))
    strip = lambda t: [l for l in t.splitlines() if "overrides.csv" not in l and "save a correction" not in l]
    assert strip(js["report"]) == strip(rp.read_text(encoding="utf-8"))
    assert "Panel heights come from the CET panel labels (9 of 9 panels labeled" in js["report"]


# ---- edge cases: rectangles at 1 point per inch (panels 2" = 2 pt thick), labels 4" off their panel

T = 2.0
GRAY = (0.86, 0.86, 0.86)


def _h(x0, width, y=0.0):
    return Rect(x0 + 0.7, y - 1, x0 + width - 0.7, y + 1, GRAY)


def _v(x, width, y0=0.0):
    return Rect(x - 1, y0 + 0.7, x + 1, y0 + width - 0.7, GRAY)


def _label(text, r):
    if r.w >= r.h:
        return Word(text, (r.x0 + r.x1) / 2, r.y0 - 4)
    return Word(text, r.x0 - 4, (r.y0 + r.y1) / 2, True)


def _panel(h, w):
    return BomLine(f"P-DLFRPM{h}{w}", f"Divi Linear Panel - NPWR - {h}H x {w}W", 1)


def _red_dot(x, y):
    return Shape(x - 1.2, y - 1.2, x + 1.2, y + 1.2, (1.0, 0.0, 0.0))


A, B = _h(0, 30), _h(30, 30)  # a straight run: 30" + 30", joint at x=30
C = _v(30, 24)  # a return hanging off that joint: makes it a 3-way
D = _h(30, 42)

CASES = [
    # (name, rects, words, shapes, BOM panels, expected fillers, expected parts subset, warning snippets)
    ("2-way change", [A, B], [_label("B4230", A), _label("A6630", B)], [], [_panel(42, 30), _panel(66, 30)],
     {"HMHL3967": 1}, {"HMP213.62": 1, "HMA128.39": 1, "HMA128.67": 1}, []),
    ("unlabeled panel, BOM has one height in its width", [A, _h(30, 24)], [_label("B4230", A)], [],
     [_panel(42, 30), _panel(66, 24)], {"HMHL3967": 1}, {"HMP213.62": 1}, []),
    ("unlabeled panel, BOM has two heights in its width", [A, _h(30, 24)], [_label("B4230", A)], [],
     [_panel(42, 30), _panel(42, 24), _panel(66, 24)], {}, {}, ['1 panel(s) on the plan (24"W) have no height label']),
    ("stray label", [A, B], [_label("B4230", A), _label("A6630", B), Word("C5060", 400, 400)], [],
     [_panel(42, 30), _panel(66, 30)], {"HMHL3967": 1}, {}, ["1 panel label(s) on the plan (C5060) aren't next to"]),
    ("three heights at a 3-way", [A, B, C], [_label("B4230", A), _label("A5030", B), _label("C6624", C)], [],
     [_panel(42, 30), _panel(50, 30), _panel(66, 24)], {"HMHL3967": 1, "HMHL5367": 1}, {"HMA137.67": 1},
     ['joins panels at 39, 53, 67"H']),
    ("no Devon filler strip for 85", [A, B], [_label("B5030", A), _label("A8230", B)], [], [_panel(50, 30), _panel(82, 30)],
     {}, {"HMP213.80": 1}, ['Panels at 53" and 85" meet on page 1']),
    ("label goes to the panel of its width", [A, D], [Word("A6642", 33, -4), Word("B4230", 15, -4)], [],
     [_panel(42, 30), _panel(66, 42)], {"HMHL3967": 1}, {}, []),
    ("colored dots win over labels", [A, B], [_label("B4230", A), _label("A6630", B)], [_red_dot(30, 0)],
     [_panel(42, 30), _panel(66, 30)], {"HMHL3953": 1}, {},
     ["The colored dots give filler strips HMHL3953 x 1, but the panel labels on the plan give HMHL3967 x 1"]),
]


@needs_template
@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_label_cases(case):
    name, rects, words, shapes, lines, fillers, parts, snippets = case
    plan = analyze_rects([rects], [shapes], None, [words])
    res = Mapper(load_catalog(TEMPLATE)).map(lines, plan)
    assert {p: q for k, p, q in res.plan_parts if k == "filler"} == fillers
    for part, qty in parts.items():
        assert res.quantities.get(part) == qty, (part, res.quantities)
    for snip in snippets:
        assert any(snip in w for w in res.warnings), (snip, res.warnings)
    if not snippets:
        assert [w for w in res.warnings if "Panel sizes differ" not in w] == []

    if _node_has("jszip"):
        payload = {
            "calc": str(TEMPLATE),
            "pages": [[{"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1, "fill": list(r.fill)} for r in rects]],
            "extras": [[{"x0": s.x0, "y0": s.y0, "x1": s.x1, "y1": s.y1, "fill": list(s.fill)} for s in shapes]],
            "words": [[{"text": w.text, "x": w.x, "y": w.y, "vertical": w.vertical} for w in words]],
            "lines": [{"part": l.part, "description": l.description, "qty": l.qty} for l in lines],
        }
        out = json.loads(subprocess.run(["node", str(ROOT / "tests" / "mark_harness.js")], input=json.dumps(payload),
                                        capture_output=True, text=True, check=True).stdout)
        assert out["warnings"] == res.warnings
        assert out["quantities"] == res.quantities
