"""Command line: turn a CET AIS Divi BOM into a filled-in Devon calculator.

    python -m devon_quote BOM.sif --project "Acme HQ" --ship-to 33010 \
        --delivery 4500 --stations 24 --notes dictation.txt --drawing plan.pdf
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

from .bom import load_bom
from .catalog import GRADES, load_catalog
from .mapper import Mapper, load_overrides
from .pricing import estimate
from .report import write_crosswalk, write_report
from .writer import QuoteHeader, write_quote

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OVERRIDES = ROOT / "mappings" / "overrides.csv"


def default_template() -> Path:
    found = sorted((ROOT / "templates").glob("DEVON*.xlsm"), key=lambda p: p.stat().st_mtime)
    if not found:
        sys.exit("No Devon calculator in templates/. Pass one with --template.")
    return found[-1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="devon_quote", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bom", help="CET bill of materials: .sif, .csv or .xlsx")
    ap.add_argument("--project", default="", help="project name for the quote header")
    ap.add_argument("--description", default="WORKSTATIONS", help="quote description (default: WORKSTATIONS)")
    ap.add_argument("--ship-to", default="", help="ship-to zip code")
    ap.add_argument("--grade", default="keystone", choices=[g.lower() for g in GRADES], help="Devon fabric grade")
    ap.add_argument("--trim", help="Devon trim color code (leave out to keep the template's)")
    ap.add_argument("--delivery", type=float, default=0.0, help="delivery estimate in dollars (default 0; Devon confirms)")
    ap.add_argument("--stations", type=int, help="number of workstations, for cost per station")
    ap.add_argument("--notes", help="text file with design notes or a dictation transcript")
    ap.add_argument("--drawing", action="append", default=[], help="2D plan file to reference in the review (repeatable)")
    ap.add_argument("--template", help="Devon calculator .xlsm (default: newest in templates/)")
    ap.add_argument("--overrides", default=str(DEFAULT_OVERRIDES), help="AIS -> Devon override table")
    ap.add_argument("-o", "--out-dir", default="out", help="where to write the results (default: out/)")
    args = ap.parse_args(argv)

    template = Path(args.template) if args.template else default_template()
    catalog = load_catalog(template)
    lines = load_bom(args.bom)
    if not lines:
        sys.exit(f"No parts found in {args.bom}")

    result = Mapper(catalog, load_overrides(args.overrides)).map(lines)
    grade = [g.lower() for g in GRADES].index(args.grade)

    stem = re.sub(r"[^\w.-]+", "_", args.project or Path(args.bom).stem).strip("_")
    out_dir = Path(args.out_dir)
    quote_path = out_dir / f"{stem}_Devon_Quote.xlsm"
    today = dt.date.today()
    header = QuoteHeader(
        project=args.project,
        description=args.description,
        date=f"{today.month}.{today.day}.{today:%y}",
        ship_to=args.ship_to,
        grade=grade,
        trim=args.trim,
        delivery=args.delivery,
        stations=args.stations,
    )
    write_quote(template, quote_path, catalog, result.quantities, header)

    est = estimate(catalog, result.quantities, grade, args.delivery, args.stations)
    notes = Path(args.notes).read_text(encoding="utf-8") if args.notes else ""
    report_path = out_dir / f"{stem}_review.md"
    write_report(
        report_path,
        project=args.project,
        bom_file=Path(args.bom).name,
        quote_file=quote_path.name,
        catalog=catalog,
        grade=grade,
        lines=lines,
        result=result,
        est=est,
        notes=notes,
        drawings=[Path(d).name for d in args.drawing],
    )
    crosswalk_path = out_dir / f"{stem}_crosswalk.csv"
    write_crosswalk(crosswalk_path, result)

    print(f"Devon quote:  {quote_path}")
    print(f"Review:       {report_path}")
    print(f"Crosswalk:    {crosswalk_path}")
    print(f"Estimated Devon total ${est.total:,.2f} "
          f"(product ${est.product_net:,.2f} + surcharge ${est.surcharge:,.2f} + delivery ${est.delivery:,.2f})")
    print(f"{len(result.unmapped)} unmapped, {len(result.review)} to confirm — see the review file.")
    return 0
