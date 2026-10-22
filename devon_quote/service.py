"""One call that turns a BOM into all the outputs. Used by the CLI and the web page."""

from __future__ import annotations

import datetime as dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .bom import BomLine, load_bom
from .catalog import GRADES, Catalog, load_catalog
from .mapper import MapResult, Mapper, load_overrides
from .marks import MarksSummary, read_marks, summarize
from .plan import PlanResult, analyze_pdf
from .pricing import Estimate, estimate
from .report import write_crosswalk, write_report
from .writer import QuoteHeader, write_quote

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
DEFAULT_OVERRIDES = ROOT / "mappings" / "overrides.csv"


def find_template() -> Path | None:
    found = sorted(TEMPLATES.glob("DEVON*.xlsm"), key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


@dataclass
class QuoteOptions:
    project: str = ""
    description: str = "WORKSTATIONS"
    ship_to: str = ""
    grade: str = "keystone"
    trim: str | None = None
    delivery: float | None = None  # None: estimated from the order weight
    divi50: int = 53  # Devon height for 50" AIS panels: 53 or 47
    stations: int | None = None
    notes: str = ""
    drawings: list[str] = field(default_factory=list)
    plan_pdfs: list[str] = field(default_factory=list)  # CET 2D plans as PDF, read for joints
    plan_images: list[str] = field(default_factory=list)  # 2D plans as PNG/JPG, read for pink dashes and colored dots


@dataclass
class QuoteOutput:
    quote_path: Path
    report_path: Path
    crosswalk_path: Path
    catalog: Catalog
    lines: list[BomLine]
    result: MapResult
    estimate: Estimate
    grade: int


def read_plans(paths: list[str]) -> PlanResult | None:
    """Joints from every PDF plan given (pages add up). None when no panels were found."""
    total = None
    for path in paths:
        res = analyze_pdf(path)
        if total is None:
            total = res
        else:
            total.counts.update(res.counts)
            total.widths.update(res.widths)
            total.joints.extend(res.joints)
            total.pages.extend(res.pages)
            total.height_changes.extend(res.height_changes)
            total.pink_dashes.extend(res.pink_dashes)
            total.labels.extend(res.labels)
    return total if total is not None and total.panels else None


def read_image_marks(images: list[str], pdfs: list[str], plan: PlanResult | None) -> MarksSummary | None:
    """Pink dashes and colored dots in the 2D images, and in PDF pages whose vector drawing carries no marks."""
    found = []
    for path in images:
        found += read_marks(path)
    if pdfs and (plan is None or not (plan.pink_dashes or plan.height_changes)):
        for path in pdfs:
            found += read_marks(path)
    return summarize(found) if found else None


def safe_stem(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name).strip("_") or "quote"


def build_quote(
    bom_path: str | Path,
    opts: QuoteOptions,
    out_dir: str | Path,
    template: str | Path | None = None,
    overrides: str | Path | None = DEFAULT_OVERRIDES,
) -> QuoteOutput:
    template = Path(template) if template else find_template()
    if template is None:
        raise FileNotFoundError("No Devon calculator found. Put DEVON_OFFICIAL_CALC_*.xlsm in templates/.")
    catalog = load_catalog(template)
    lines = load_bom(bom_path)
    if not lines:
        raise ValueError(f"No parts found in {Path(bom_path).name}")

    plan = read_plans(opts.plan_pdfs)
    marks = read_image_marks(opts.plan_images, opts.plan_pdfs, plan)
    result = Mapper(catalog, load_overrides(overrides), divi50=opts.divi50).map(lines, plan, marks)
    grade = [g.lower() for g in GRADES].index(opts.grade.lower())

    out_dir = Path(out_dir)
    stem = safe_stem(opts.project or Path(bom_path).stem)
    today = dt.date.today()
    est = estimate(catalog, result.quantities, grade, opts.delivery, opts.stations)
    header = QuoteHeader(
        project=opts.project,
        description=opts.description,
        date=f"{today.month}.{today.day}.{today:%y}",
        ship_to=opts.ship_to,
        grade=grade,
        trim=opts.trim,
        delivery=est.delivery,
        stations=opts.stations,
    )
    quote_path = write_quote(template, out_dir / f"{stem}_Devon_Quote.xlsm", catalog, result.quantities, header)

    report_path = out_dir / f"{stem}_review.md"
    write_report(
        report_path,
        project=opts.project,
        bom_file=Path(bom_path).name,
        quote_file=quote_path.name,
        catalog=catalog,
        grade=grade,
        lines=lines,
        result=result,
        est=est,
        notes=opts.notes,
        drawings=opts.drawings,
    )
    crosswalk_path = out_dir / f"{stem}_crosswalk.csv"
    write_crosswalk(crosswalk_path, result)
    return QuoteOutput(quote_path, report_path, crosswalk_path, catalog, lines, result, est, grade)
