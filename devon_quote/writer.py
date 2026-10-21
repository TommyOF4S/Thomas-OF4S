"""Fill a copy of the official Devon calculator with quantities and project info.

The .xlsm is edited at the XML level (not re-saved through openpyxl) so Devon's macros,
formulas, formatting and links come through untouched. Excel / Google Sheets recalculate
the prices when the file is opened.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from .catalog import GRADES, Catalog

SHEET = "xl/worksheets/sheet1.xml"  # the Master sheet
WORKBOOK = "xl/workbook.xml"


@dataclass
class QuoteHeader:
    project: str = ""
    description: str = ""
    date: str = ""
    ship_to: str = ""
    dealer: str | None = None  # None keeps the template's dealer name
    grade: int = 0  # 0=Keystone, 1=Summit, 2=Aspen
    trim: str | None = None
    delivery: float | None = None
    stations: int | None = None


def _col_index(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def _cell_xml(ref: str, style: str | None, value) -> str:
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s}/>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{s}><v>{value}</v></c>'
    return f'<c r="{ref}"{s} t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'


def _set_cell(xml: str, ref: str, value) -> str:
    """Replace (or insert) one cell's value, keeping its style."""
    row = int(re.sub(r"[A-Z]+", "", ref))
    col = re.sub(r"\d+", "", ref)
    cell_re = re.compile(rf'<c r="{ref}"(?P<attrs>[^>]*?)(?:/>|>.*?</c>)', re.S)
    m = cell_re.search(xml)
    if m:
        if "<f" in m.group(0):
            raise ValueError(f"refusing to overwrite formula cell {ref}")
        style = re.search(r's="(\d+)"', m.group("attrs"))
        return xml[: m.start()] + _cell_xml(ref, style.group(1) if style else None, value) + xml[m.end():]
    row_re = re.compile(rf'<row r="{row}"[^>]*?(?:/>|>(?P<body>.*?)</row>)', re.S)
    rm = row_re.search(xml)
    if not rm:
        raise ValueError(f"row {row} not found in the calculator")
    new = _cell_xml(ref, None, value)
    if rm.group("body") is None:  # self-closing <row .../>
        opened = rm.group(0)[:-2] + ">"
        return xml[: rm.start()] + opened + new + "</row>" + xml[rm.end():]
    # Insert before the first cell that sits to the right of this column.
    body_start = rm.start("body")
    for cm in re.finditer(r'<c r="([A-Z]+)\d+"', rm.group("body")):
        if _col_index(cm.group(1)) > _col_index(col):
            pos = body_start + cm.start()
            return xml[:pos] + new + xml[pos:]
    pos = rm.end("body")
    return xml[:pos] + new + xml[pos:]


def write_quote(
    template: str | Path,
    out_path: str | Path,
    catalog: Catalog,
    quantities: dict[str, int],
    header: QuoteHeader,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, out_path)

    with zipfile.ZipFile(template) as zin:
        sheet = zin.read(SHEET).decode("utf-8")
        workbook = zin.read(WORKBOOK).decode("utf-8")
        names = zin.infolist()
        blobs = {i.filename: zin.read(i.filename) for i in names}

    # Clear any quantity left over in the template, then write ours.
    for item in catalog.items.values():
        sheet = _set_cell(sheet, f"C{item.row}", None)
    for part, qty in quantities.items():
        item = catalog.get(part)
        if item is None:
            raise KeyError(f"{part} is not in the Devon calculator")
        sheet = _set_cell(sheet, f"C{item.row}", qty)

    # Header block. B4 (Devon's quote #) and B8 (Devon's PM) are Devon's to fill in.
    fields = {
        "B4": "",
        "B6": header.project,
        "B7": header.description,
        "B8": "",
        "B9": header.date,
        "B11": header.ship_to,
        "J10": header.grade + 1,
        "B16": f"{GRADES[header.grade]}(Grade {header.grade + 1})",
    }
    if header.dealer is not None:
        fields["B5"] = header.dealer
    if header.trim is not None:
        fields["B14"] = header.trim
    if header.delivery is not None:
        fields["G444"] = header.delivery
    if header.stations is not None:
        fields["G450"] = header.stations
    for ref, val in fields.items():
        sheet = _set_cell(sheet, ref, val)

    # Drop the template's cached formula results (they belong to an old quote) and make
    # Excel recalculate every formula when the file is opened.
    sheet = re.sub(r"(<f[^>]*?(?:/>|>[^<]*</f>))<v>[^<]*</v>", r"\1", sheet)
    if "<calcPr/>" in workbook:
        workbook = workbook.replace("<calcPr/>", '<calcPr fullCalcOnLoad="1"/>')
    elif "<calcPr" in workbook and "fullCalcOnLoad" not in workbook:
        workbook = workbook.replace("<calcPr", '<calcPr fullCalcOnLoad="1"', 1)

    blobs[SHEET] = sheet.encode("utf-8")
    blobs[WORKBOOK] = workbook.encode("utf-8")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in names:
            zout.writestr(info, blobs[info.filename])
    return out_path
