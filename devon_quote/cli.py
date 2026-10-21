"""Command line: turn a CET AIS Divi BOM into a filled-in Devon calculator.

    python -m devon_quote BOM.sif --project "Acme HQ" --ship-to 33010 \
        --delivery 4500 --stations 24 --notes dictation.txt --drawing plan.pdf

    python -m devon_quote serve        # open the drag-and-drop page instead
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .catalog import GRADES
from .service import DEFAULT_OVERRIDES, QuoteOptions, build_quote


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "serve":
        from .server import main as serve

        return serve(argv[1:])

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

    opts = QuoteOptions(
        project=args.project,
        description=args.description,
        ship_to=args.ship_to,
        grade=args.grade,
        trim=args.trim,
        delivery=args.delivery,
        stations=args.stations,
        notes=Path(args.notes).read_text(encoding="utf-8") if args.notes else "",
        drawings=[Path(d).name for d in args.drawing],
    )
    try:
        out = build_quote(args.bom, opts, args.out_dir, args.template, args.overrides)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(str(e))

    est, result = out.estimate, out.result
    print(f"Devon quote:  {out.quote_path}")
    print(f"Review:       {out.report_path}")
    print(f"Crosswalk:    {out.crosswalk_path}")
    print(f"Estimated Devon total ${est.total:,.2f} "
          f"(product ${est.product_net:,.2f} + surcharge ${est.surcharge:,.2f} + delivery ${est.delivery:,.2f})")
    print(f"{len(result.unmapped)} unmapped, {len(result.review)} to confirm — see the review file.")
    return 0
