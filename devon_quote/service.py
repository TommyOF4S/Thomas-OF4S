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
    delivery: float = 0.0
    stations: int | None = None
    notes: str = ""
    drawings: list[str] = field(default_factory=list)


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

    result = Mapper(catalog, load_overrides(overrides)).map(lines)
    grade = [g.lower() for g in GRADES].index(opts.grade.lower())

    out_dir = Path(out_dir)
    stem = safe_stem(opts.project or Path(bom_path).stem)
    today = dt.date.today()
    header = QuoteHeader(
        project=opts.project,
        description=opts.description,
        date=f"{today.month}.{today.day}.{today:%y}",
        ship_to=opts.ship_to,
        grade=grade,
        trim=opts.trim,
        delivery=opts.delivery,
        stations=opts.stations,
    )
    quote_path = write_quote(template, out_dir / f"{stem}_Devon_Quote.xlsm", catalog, result.quantities, header)

    est = estimate(catalog, result.quantities, grade, opts.delivery, opts.stations)
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
