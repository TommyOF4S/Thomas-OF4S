"""Drag-and-drop page for the Devon quote builder.

    python -m devon_quote serve [--port 8765] [--no-browser]

Runs only on this computer (127.0.0.1); files never leave it. Results are saved in out/.
Uses the Python standard library only.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import re
import threading
import traceback
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from .catalog import GRADES, load_catalog
from .report import finishes
from .service import ROOT, TEMPLATES, QuoteOptions, build_quote, find_template, safe_stem

WEB = Path(__file__).resolve().parent / "web"
OUT = ROOT / "out"
MAX_BODY = 50 * 1024 * 1024


def _status() -> dict:
    tpl = find_template()
    if tpl is None:
        return {"template": None}
    try:
        cat = load_catalog(tpl)
    except Exception as e:  # a broken file in templates/ shouldn't take the page down
        return {"template": tpl.name, "error": str(e)}
    return {"template": tpl.name, "title": cat.title, "items": len(cat.items), "grades": list(GRADES)}


def _decode(upload: dict | None, what: str) -> tuple[str, bytes]:
    if not upload or not upload.get("data"):
        raise ValueError(f"Missing {what}.")
    name = Path(upload.get("name") or what).name
    data = upload["data"].split(",", 1)[-1]  # accept data: URLs too
    return name, base64.b64decode(data)


def _save_template(body: dict) -> dict:
    name, data = _decode(body.get("file"), "Devon calculator")
    if not name.lower().endswith(".xlsm"):
        raise ValueError("The Devon calculator should be the .xlsm file Devon sends.")
    if not name.upper().startswith("DEVON"):
        name = "DEVON_" + name
    TEMPLATES.mkdir(exist_ok=True)
    tmp = TEMPLATES / (name + ".uploading")
    tmp.write_bytes(data)
    try:
        load_catalog(tmp)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"That file doesn't look like a Devon calculator: {e}")
    tmp.replace(TEMPLATES / name)
    return _status()


def _num(v, cast):
    if v in (None, ""):
        return None
    return cast(str(v).replace(",", "").replace("$", ""))


def _build(body: dict) -> dict:
    name, data = _decode(body.get("bom"), "CET bill of materials")
    if Path(name).suffix.lower() not in (".sif", ".csv", ".txt", ".xlsx", ".xlsm"):
        raise ValueError("The bill of materials should be a CET .sif export, or a .csv/.xlsx with part numbers and quantities.")
    project = (body.get("project") or "").strip()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    job = f"{safe_stem(project or Path(name).stem)}_{stamp}"
    job_dir = OUT / job
    job_dir.mkdir(parents=True, exist_ok=True)
    bom_path = job_dir / name
    bom_path.write_bytes(data)
    plan_pdfs, plan_images = [], []
    for up in body.get("plans") or []:
        pname, pdata = _decode(up, "2D plan")
        if pname.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
            ppath = job_dir / ("plan_" + pname)
            ppath.write_bytes(pdata)
            (plan_pdfs if pname.lower().endswith(".pdf") else plan_images).append(str(ppath))

    grade = (body.get("grade") or "keystone").lower()
    if grade not in [g.lower() for g in GRADES]:
        raise ValueError(f"Unknown fabric grade: {grade}")
    opts = QuoteOptions(
        project=project,
        description=(body.get("description") or "WORKSTATIONS").strip(),
        ship_to=(body.get("ship_to") or "").strip(),
        grade=grade,
        trim=(body.get("trim") or "").strip() or None,
        delivery=_num(body.get("delivery"), float) or 0.0,
        stations=_num(body.get("stations"), int),
        notes=body.get("notes") or "",
        drawings=[Path(d).name for d in body.get("drawings") or []],
        plan_pdfs=plan_pdfs,
        plan_images=plan_images,
    )
    out = build_quote(bom_path, opts, job_dir)
    est, res = out.estimate, out.result
    auto = {p for p, _, _ in res.auto_added}

    def row(m):
        return {
            "part": m.source.part,
            "description": m.source.description,
            "qty": m.source.qty,
            "devon": [p for p, _ in m.targets],
            "note": m.note,
        }

    files = {k: f"/download/{job}/{p.name}" for k, p in
             (("quote", out.quote_path), ("report", out.report_path), ("crosswalk", out.crosswalk_path))}
    return {
        "job": job,
        "saved_to": str(job_dir),
        "template": out.catalog.title,
        "grade": GRADES[out.grade],
        "bom": {"name": name, "lines": len(out.lines), "pieces": sum(l.qty for l in out.lines)},
        "estimate": {
            "list": est.list_total,
            "product": est.product_net,
            "surcharge": est.surcharge,
            "surcharge_rate": out.catalog.surcharge_rate,
            "delivery": est.delivery,
            "total": est.total,
            "per_station": est.per_station,
            "stations": est.stations,
            "weight": est.weight,
        },
        "warnings": res.warnings,
        "plan": None if res.plan is None else {
            "panels": res.plan.panels,
            "counts": {k: res.plan.counts[k] for k in ("straight", "l", "tee", "cross", "ends", "angled", "other")},
            "height_changes": len(res.plan.height_changes),
            "parts": [{"kind": k, "part": p, "qty": q} for k, p, q in res.plan_parts],
        },
        "unmapped": [row(m) for m in res.unmapped],
        "review": [row(m) for m in res.review],
        "lines": [
            {
                "part": l.part,
                "description": l.description,
                "qty": l.qty,
                "net_each": l.net_each,
                "net_ext": l.net_ext,
                "from": res.sources.get(l.part) or (["auto-added"] if l.part in auto else []),
            }
            for l in est.lines
        ],
        "finishes": [{"group": g, "selection": d, "pieces": q} for g, d, q in finishes(out.lines)],
        "files": files,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "DevonQuote/1"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200):
        self._send(status, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])
        if path in ("/", "/index.html"):
            return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if path == "/api/status":
            return self._json(_status())
        m = re.fullmatch(r"/download/([\w.-]+)/([^/]+)", path)
        if m:
            f = (OUT / m.group(1) / m.group(2)).resolve()
            if f.is_file() and OUT.resolve() in f.parents:
                ctype = {".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12", ".md": "text/markdown; charset=utf-8",
                         ".csv": "text/csv; charset=utf-8"}.get(f.suffix, "application/octet-stream")
                return self._send(200, f.read_bytes(), ctype, {"Content-Disposition": f'attachment; filename="{f.name}"'})
        self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json({"error": "Those files are too large."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/quote":
                return self._json(_build(body))
            if self.path == "/api/template":
                return self._json(_save_template(body))
            return self._json({"error": "Not found"}, 404)
        except (ValueError, FileNotFoundError, KeyError) as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": f"Something went wrong: {e}"}, 500)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="devon_quote serve", description="Open the Devon quote builder page.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    args = ap.parse_args(argv)

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Devon quote builder running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
