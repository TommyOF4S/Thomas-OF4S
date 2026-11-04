"""Cut list workbook (.xlsx) and CSV from geometry.py."""
import csv
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import geometry as g
from geometry import fmt

HDR_FILL = PatternFill("solid", fgColor="F3EFE7")
HDR_FONT = Font(bold=True, color="15273F")
THIN = Side(style="thin", color="D6CFBE")
EB_TEXT = {"P01": "All 4 edges", "P02": "Front, rear, notch", "P03": "Front", "P04": "Front",
           "P05": "Front", "P06": "None", "P07": "None", "P08": "None", "P09": "All 4 edges", "P10": "All 4 edges"}


def _sheet(ws, header, rows, widths):
    ws.append(header)
    for r in rows:
        ws.append(r)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for cell in ws[1]:
        cell.fill, cell.font = HDR_FILL, HDR_FONT
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        for cell in row:
            cell.border = Border(bottom=THIN)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"


def build(xlsx_path, csv_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Cut list"
    header = ["Mark", "Part", "Qty", "Length (in)", "Width (in)", "Thick (in)", "Length", "Width", "Material",
              "Edgeband", "Edgeband in/pc", "Sq ft each", "Sq ft total", "Notes"]
    rows = []
    for i, p in enumerate(g.PARTS, start=2):
        rows.append([p["mark"], p["name"], p["qty"], p["L"], p["Wd"], p["T"], fmt(p["L"]), fmt(p["Wd"]),
                     g.MATERIALS[p["mat"]]["short"], EB_TEXT[p["mark"]], p["eb_len"],
                     f"=D{i}*E{i}/144", f"=L{i}*C{i}", p["notes"]])
    _sheet(ws, header, rows, [7, 30, 6, 11, 11, 10, 9, 9, 16, 18, 13, 11, 11, 70])
    n = len(rows) + 1
    ws.append([])
    ws.append(["", "Total 1\" board (sq ft)", "", "", "", "", "", "", "", "", "", "",
               f'=SUMIF(I2:I{n},"{g.MATERIALS["M1"]["short"]}",M2:M{n})'])
    ws.append(["", "Total 1/2\" back (sq ft)", "", "", "", "", "", "", "", "", "", "",
               f'=SUMIF(I2:I{n},"{g.MATERIALS["M2"]["short"]}",M2:M{n})'])
    ws.append(["", "Edgeband (linear ft, net)", "", "", "", "", "", "", "", "", f"=SUMPRODUCT(C2:C{n},K2:K{n})/12"])
    for r in range(ws.max_row - 2, ws.max_row + 1):
        ws.cell(r, 2).font = Font(bold=True)
    for r in range(2, ws.max_row + 1):
        for col in (12, 13, 11):
            ws.cell(r, col).number_format = "0.0"

    ws2 = wb.create_sheet("Hardware")
    _sheet(ws2, ["Mark", "Item", "Qty", "Notes"],
           [[h["mark"], h["item"], h["qty"] if h["qty"] is not None else round(g.TOTAL_EB_IN / 12 * 1.1),
             h["notes"] + (" (linear ft incl. 10% waste)" if h["qty"] is None else "")] for h in g.HARDWARE],
           [7, 60, 8, 60])

    ws3 = wb.create_sheet("Materials")
    _sheet(ws3, ["Code", "Material", "Approx. lb per sq ft"],
           [[k, m["name"], m["psf"]] for k, m in g.MATERIALS.items()] + [["EB", g.EDGEBAND, ""]], [7, 80, 18])

    ws4 = wb.create_sheet("Alternates")
    _sheet(ws4, ["Mark", "Alternate", "Description", "Price per cabinet"],
           [[a["mark"], a["title"], a["desc"], ""] for a in g.ALTERNATES], [8, 20, 100, 18])

    ws5 = wb.create_sheet("Design basis")
    _sheet(ws5, ["Item", "Value"], [
        ["Overall W x D x H (in)", f"{fmt(g.W)} x {fmt(g.D)} x {fmt(g.H)}"],
        ["Bays", f"{g.COLS} columns x {g.TIERS} tiers = {g.BAYS}"],
        ["Clear bay W x H x D", f"{fmt(g.OPEN_W)} x {fmt(g.OPEN_H)} x {fmt(g.INT_D)}"],
        ["Laptop", f"{fmt(g.LAPTOP_W)} x {fmt(g.LAPTOP_D)} x {fmt(g.LAPTOP_T)}, stack of {g.STACK}"],
        ["Capacity", f"{g.CAPACITY} laptops"],
        ["Weight empty / loaded (approx.)", f"{g.TOTAL_LB:.0f} lb / {g.LOADED_LB:.0f} lb"],
    ], [34, 50])
    wb.save(xlsx_path)

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Mark", "Part", "Qty", "Length_in", "Width_in", "Thick_in", "Material", "Edgeband", "Notes"])
        for p in g.PARTS:
            w.writerow([p["mark"], p["name"], p["qty"], p["L"], p["Wd"], p["T"], g.MATERIALS[p["mat"]]["short"],
                        EB_TEXT[p["mark"]], p["notes"]])


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")
    build(os.path.join(out, "LC-60_Cut_List.xlsx"), os.path.join(out, "LC-60_Cut_List.csv"))
    print("ok")
