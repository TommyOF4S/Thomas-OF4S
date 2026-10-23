"""Load a CET bill of materials.

Supported inputs:
  * .sif  - CET "Standard Interchange Format" export (Configura SIF). Each product
            starts with PN= and carries PD= (description), QT= (quantity), TG= (tag),
            and option groups ON=/OD=/OP=/OG= (option code, description, parent, group).
  * .csv / .xlsx - any table with a part-number column and a quantity column
            (headers such as "Part Number", "Catalog", "Qty", "Quantity").
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Option:
    code: str
    description: str
    group: str


@dataclass
class BomLine:
    part: str
    description: str
    qty: float
    tag: str = ""
    list_price: float | None = None
    options: list[Option] = field(default_factory=list)

    def option_text(self) -> str:
        return " | ".join(f"{o.group}: {o.description}" for o in self.options if o.group)


def parse_sif(text: str) -> list[BomLine]:
    lines: list[BomLine] = []
    cur: BomLine | None = None
    opt: dict[str, str] = {}

    def flush_option():
        if cur is not None and opt.get("ON"):
            cur.options.append(Option(opt.get("ON", ""), opt.get("OD", ""), opt.get("OG", "")))
        opt.clear()

    for raw in text.splitlines():
        if "=" not in raw:
            continue
        key, _, val = raw.partition("=")
        key, val = key.strip(), val.strip()
        if key == "PN":
            flush_option()
            cur = BomLine(part=val, description="", qty=0)
            lines.append(cur)
        elif cur is None:
            continue  # file header (SF=, ST=, DT=, ...)
        elif key == "PD":
            cur.description = val
        elif key == "QT":
            cur.qty = float(val or 0)
        elif key == "TG":
            cur.tag = val
        elif key == "PL":
            try:
                cur.list_price = float(val)
            except ValueError:
                pass
        elif key == "ON":
            flush_option()
            opt["ON"] = val
        elif key in ("OD", "OG"):
            opt[key] = val
        elif key == "OL":
            flush_option()
    flush_option()
    return lines


_PART_HEADERS = ("part number", "part", "catalog", "catalog number", "part no", "item", "item #", "pn", "product number")
_QTY_HEADERS = ("qty", "quantity", "qt", "count")
_DESC_HEADERS = ("description", "desc", "pd", "product description")
_TAG_HEADERS = ("tag", "area", "location")


def _pick(headers: list[str], wanted: tuple[str, ...]) -> int | None:
    norm = [h.strip().lower() for h in headers]
    for w in wanted:
        if w in norm:
            return norm.index(w)
    return None


def parse_table(rows: list[list]) -> list[BomLine]:
    # Find the header row: the first row that has both a part and a quantity column.
    for i, row in enumerate(rows):
        headers = ["" if c is None else str(c) for c in row]
        p, q = _pick(headers, _PART_HEADERS), _pick(headers, _QTY_HEADERS)
        if p is not None and q is not None:
            d, t = _pick(headers, _DESC_HEADERS), _pick(headers, _TAG_HEADERS)
            break
    else:
        raise ValueError("could not find a header row with a part number and a quantity column")

    out: list[BomLine] = []
    for row in rows[i + 1 :]:
        if p >= len(row) or row[p] in (None, ""):
            continue
        try:
            qty = float(str(row[q]).replace(",", ""))
        except (ValueError, IndexError, TypeError):
            continue
        out.append(
            BomLine(
                part=str(row[p]).strip(),
                description=str(row[d]).strip() if d is not None and d < len(row) and row[d] else "",
                qty=qty,
                tag=str(row[t]).strip() if t is not None and t < len(row) and row[t] else "",
            )
        )
    return out


def load_bom(path: str | Path) -> list[BomLine]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".sif":
        return parse_sif(path.read_text(encoding="utf-8", errors="replace"))
    if suffix in (".csv", ".txt"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        return parse_table(list(csv.reader(io.StringIO(text))))
    if suffix in (".xlsx", ".xlsm"):
        import openpyxl

        ws = openpyxl.load_workbook(path, data_only=True, read_only=True).active
        return parse_table([list(r) for r in ws.iter_rows(values_only=True)])
    raise ValueError(f"unsupported BOM file type: {path.suffix} (use .sif, .csv or .xlsx)")
