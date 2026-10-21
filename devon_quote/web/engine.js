/* Devon quote engine, JavaScript port of the devon_quote Python package
 * (catalog.py, bom.py, mapper.py, writer.py, pricing.py, report.py) for the
 * hosted page. tests/test_engine_parity.py runs it under Node against the
 * same fixture and checks it gives the same quote as Python.
 *
 * Needs a JSZip-compatible `zipLib` passed to loadCalculator / writeQuote.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DevonEngine = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const GRADES = ["Keystone", "Summit", "Aspen"];
  const SHEET = "xl/worksheets/sheet1.xml";
  const WORKBOOK = "xl/workbook.xml";

  // ---------------------------------------------------------------- xml helpers
  const ENT = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'" };
  const unescapeXml = (s) =>
    s.replace(/&(amp|lt|gt|quot|apos);|&#(\d+);|&#x([0-9a-f]+);/gi, (m, n, d, h) =>
      n ? ENT[m] : String.fromCodePoint(d ? +d : parseInt(h, 16)));
  const escapeXml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  function parseSharedStrings(xml) {
    const out = [];
    if (!xml) return out;
    const re = /<si>([\s\S]*?)<\/si>/g;
    let m;
    while ((m = re.exec(xml))) {
      let text = "";
      const t = /<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g;
      let tm;
      while ((tm = t.exec(m[1]))) text += tm[1];
      out.push(unescapeXml(text));
    }
    return out;
  }

  /** All cells of the sheet: {A26: {value, formula, hasFormula}} plus rows -> refs. */
  function parseCells(xml, sst) {
    const cells = {};
    const re = /<c r="([A-Z]+\d+)"([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g;
    let m;
    while ((m = re.exec(xml))) {
      const [, ref, attrs, inner = ""] = m;
      const t = (attrs.match(/\st="([^"]+)"/) || [])[1];
      const fm = inner.match(/<f[^>]*?(?:\/>|>([\s\S]*?)<\/f>)/);
      const vm = inner.match(/<v>([\s\S]*?)<\/v>/);
      let value = null;
      if (t === "s" && vm) value = sst[+vm[1]];
      else if (t === "inlineStr") {
        const im = inner.match(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/);
        value = im ? unescapeXml(im[1]) : "";
      } else if (t === "str" && vm) value = unescapeXml(vm[1]);
      else if (vm && vm[1] !== "") value = Number(vm[1]);
      cells[ref] = { value, formula: fm ? unescapeXml(fm[1] || "") : null, hasFormula: !!fm };
    }
    return cells;
  }

  // ---------------------------------------------------------------- catalog
  function num(v) {
    return typeof v === "number" && !Number.isNaN(v) ? v : null;
  }

  function gradeCol(cell, lPrice) {
    if (!cell) return lPrice;
    if (!cell.hasFormula && num(cell.value) !== null) return cell.value;
    if (cell.hasFormula && lPrice !== null) {
      const m = (cell.formula || "").replace(/^=/, "").match(/^\s*L(\d+)\s*(?:\+\s*([\d.]+))?\s*$/);
      if (m) return lPrice + Number(m[2] || 0);
      if (num(cell.value) !== null) return cell.value; // shared formula: use the cached result
    }
    return lPrice;
  }

  function buildCatalog(sheetXml, sstXml) {
    const sst = parseSharedStrings(sstXml);
    const cells = parseCells(sheetXml, sst);
    const val = (ref) => (cells[ref] ? cells[ref].value : null);
    const rows = Object.keys(cells).map((r) => +r.replace(/^[A-Z]+/, ""));
    const maxRow = Math.max(...rows);

    let firstRow = null, lastRow = null, surchargeRate = 0;
    for (let r = 1; r <= maxRow; r++) {
      const a = val("A" + r);
      if (a === "PRODUCT NUMBER" && r > 20) firstRow = r + 1;
      else if (typeof a === "string" && a.startsWith("SUB-TOTAL: PRODUCT ONLY")) lastRow = r - 1;
      else if (a === "SURCHARGE") {
        const g = cells["G" + r];
        const m = String((g && (g.formula || g.value)) || "").match(/\*\s*([\d.]+)\s*$/);
        surchargeRate = m ? Number(m[1]) : 0;
      }
    }
    if (firstRow === null || lastRow === null) throw new Error("That file doesn't look like a Devon calculator (no product list on the Master sheet).");

    const items = {};
    const order = [];
    let section = "";
    for (let r = firstRow; r <= lastRow; r++) {
      let a = val("A" + r), b = val("B" + r);
      if (typeof a !== "string" || !a.trim()) continue;
      a = a.trim();
      if (a.startsWith("-->>") || a.startsWith(">>")) continue;
      if (!(typeof b === "string" && b.trim())) { section = a; continue; }
      if (items[a]) continue;
      const d = cells["D" + r];
      const lPrice = num(val("L" + r));
      let gradePrices = null, fixed = null;
      if (d && d.hasFormula && lPrice !== null) {
        gradePrices = [lPrice, gradeCol(cells["M" + r], lPrice), gradeCol(cells["N" + r], lPrice)];
      } else {
        fixed = d && !d.hasFormula ? num(d.value) || 0 : 0;
      }
      items[a] = { part: a, description: b.trim(), row: r, section, weight: num(val("I" + r)) || 0, gradePrices, fixed };
      order.push(a);
    }
    return {
      items,
      order,
      netMultiplier: num(val("F18")) || 0.3,
      surchargeRate,
      title: String(val("A3") || ""),
      firstRow,
      lastRow,
      has: (p) => Object.prototype.hasOwnProperty.call(items, p),
    };
  }

  function listPrice(item, grade) {
    return item.gradePrices ? item.gradePrices[grade] : item.fixed || 0;
  }

  async function loadCalculator(zipLib, bytes) {
    const zip = await zipLib.loadAsync(bytes);
    const sheet = zip.file(SHEET), sst = zip.file("xl/sharedStrings.xml");
    if (!sheet) throw new Error("That file doesn't look like a Devon calculator (no Master sheet).");
    const catalog = buildCatalog(await sheet.async("string"), sst ? await sst.async("string") : "");
    return { zip, bytes, catalog };
  }

  // ---------------------------------------------------------------- BOM
  function parseSif(text) {
    const lines = [];
    let cur = null;
    let opt = {};
    const flush = () => {
      if (cur && opt.ON) cur.options.push({ code: opt.ON || "", description: opt.OD || "", group: opt.OG || "" });
      opt = {};
    };
    for (const raw of text.split(/\r\n|\r|\n/)) {
      const i = raw.indexOf("=");
      if (i < 0) continue;
      const key = raw.slice(0, i).trim(), v = raw.slice(i + 1).trim();
      if (key === "PN") {
        flush();
        cur = { part: v, description: "", qty: 0, tag: "", options: [] };
        lines.push(cur);
      } else if (!cur) continue;
      else if (key === "PD") cur.description = v;
      else if (key === "QT") cur.qty = Number(v || 0);
      else if (key === "TG") cur.tag = v;
      else if (key === "ON") { flush(); opt.ON = v; }
      else if (key === "OD" || key === "OG") opt[key] = v;
      else if (key === "OL") flush();
    }
    flush();
    return lines;
  }

  const PART_H = ["part number", "part", "catalog", "catalog number", "part no", "item", "item #", "pn", "product number"];
  const QTY_H = ["qty", "quantity", "qt", "count"];
  const DESC_H = ["description", "desc", "pd", "product description"];
  const TAG_H = ["tag", "area", "location"];
  const pick = (headers, wanted) => {
    const norm = headers.map((h) => String(h ?? "").trim().toLowerCase());
    for (const w of wanted) { const i = norm.indexOf(w); if (i >= 0) return i; }
    return null;
  };

  function parseTable(rows) {
    let p = null, q = null, d = null, t = null, start = -1;
    for (let i = 0; i < rows.length; i++) {
      p = pick(rows[i], PART_H); q = pick(rows[i], QTY_H);
      if (p !== null && q !== null) { d = pick(rows[i], DESC_H); t = pick(rows[i], TAG_H); start = i; break; }
    }
    if (start < 0) throw new Error("Couldn't find a header row with a part number and a quantity column.");
    const out = [];
    for (const row of rows.slice(start + 1)) {
      if (p >= row.length || row[p] == null || row[p] === "") continue;
      const qty = Number(String(row[q] ?? "").replace(/,/g, ""));
      if (row[q] == null || row[q] === "" || Number.isNaN(qty)) continue;
      out.push({
        part: String(row[p]).trim(),
        description: d !== null && row[d] ? String(row[d]).trim() : "",
        qty,
        tag: t !== null && row[t] ? String(row[t]).trim() : "",
        options: [],
      });
    }
    return out;
  }

  function parseCsv(text) {
    const rows = [];
    let row = [], field = "", quoted = false;
    text = text.replace(/^﻿/, "");
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
        else if (c === '"') quoted = false;
        else field += c;
      } else if (c === '"') quoted = true;
      else if (c === ",") { row.push(field); field = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(field); rows.push(row); row = []; field = "";
      } else field += c;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    return rows;
  }

  /** First sheet of an .xlsx as rows of values. */
  async function xlsxRows(zipLib, bytes) {
    const zip = await zipLib.loadAsync(bytes);
    const wb = await zip.file("xl/workbook.xml").async("string");
    const rels = await zip.file("xl/_rels/workbook.xml.rels").async("string");
    const rid = (wb.match(/<sheet [^>]*r:id="([^"]+)"/) || [])[1];
    const target = (rels.match(new RegExp(`Id="${rid}"[^>]*Target="([^"]+)"`)) || rels.match(new RegExp(`Target="([^"]+)"[^>]*Id="${rid}"`)) || [])[1];
    const path = target ? "xl/" + target.replace(/^\/?xl\//, "").replace(/^\//, "") : "xl/worksheets/sheet1.xml";
    const sstFile = zip.file("xl/sharedStrings.xml");
    const cells = parseCells(await zip.file(path).async("string"), parseSharedStrings(sstFile ? await sstFile.async("string") : ""));
    const rows = [];
    for (const [ref, c] of Object.entries(cells)) {
      const col = ref.replace(/\d+/g, ""), r = +ref.replace(/[A-Z]+/g, "");
      let ci = 0;
      for (const ch of col) ci = ci * 26 + ch.charCodeAt(0) - 64;
      (rows[r - 1] ||= [])[ci - 1] = c.value;
    }
    return Array.from(rows, (r) => Array.from(r || [], (v) => (v === undefined ? null : v)));
  }

  async function parseBom(zipLib, name, bytes) {
    const ext = (name.match(/\.[^.]+$/) || [""])[0].toLowerCase();
    if (ext === ".sif") return parseSif(new TextDecoder().decode(bytes));
    if (ext === ".csv" || ext === ".txt") return parseTable(parseCsv(new TextDecoder().decode(bytes)));
    if (ext === ".xlsx" || ext === ".xlsm") return parseTable(await xlsxRows(zipLib, bytes));
    throw new Error(`Unsupported BOM file type ${ext || "(none)"}. Use a CET .sif, .csv or .xlsx.`);
  }

  // ---------------------------------------------------------------- mapper
  const DEVON_HEIGHTS = [39, 47, 53, 67, 85];
  const CONNECTOR_CODES = { 39: ["39", "34"], 47: ["47", "42"], 53: ["53", "48"], 67: ["67", "62"], 85: ["85", "80"] };
  const HEIGHT_TOLERANCE = 6;

  function connector(kind, height) {
    const [a, b] = CONNECTOR_CODES[height];
    return {
      "2way": `HMA130.${a}`, "3way": `HMA137.${a}`, "4way": `HMC132.${b}`, inline: `HMP213.${b}`,
      change_height: `HMA224.${b}`, finished_end: `HMA128.${a}`, wall_start: `HMA199.${b}`,
    }[kind];
  }

  function devonHeight(h) {
    for (const d of DEVON_HEIGHTS) {
      if (h <= d) return [d, d - h > HEIGHT_TOLERANCE ? `AIS ${h}"H rounds up to Devon ${d}"H` : ""];
    }
    return [85, `AIS ${h}"H is taller than any Devon panel; used 85"H`];
  }

  const PANEL = /^P-DL([A-Z]+?)(\d{2})(\d{2})$/;
  const POST = /^P-DLPF([234])(\d{2})$/;
  const WS = /^W-WS(\d{2})(\d{2})$/;
  const CANT = /^WPS-UNCT(\d{2})([LRS])$/;
  const WIDTH = /(\d{2})\s*(?:"|in\b|W\b)/i;

  function powered(desc) {
    const d = desc.toUpperCase();
    if (/\bNPWR\b|NON-?POWER/.test(d)) return false;
    if (/\bPWR\b|POWERED/.test(d)) return true;
    return null;
  }

  function globToRegex(pat) {
    let re = "";
    for (let i = 0; i < pat.length; i++) {
      const c = pat[i];
      if (c === "*") re += ".*";
      else if (c === "?") re += ".";
      else if (c === "[") {
        const j = pat.indexOf("]", i + 1);
        if (j < 0) re += "\\[";
        else { let body = pat.slice(i + 1, j); if (body[0] === "!") body = "^" + body.slice(1); re += "[" + body.replace(/\\/g, "\\\\") + "]"; i = j; }
      } else re += c.replace(/[.+^${}()|\\\]]/g, "\\$&");
    }
    return new RegExp("^" + re + "$");
  }

  const M = (source, targets, status, note = "", rule = "") => ({ source, targets, status, note, rule });

  function makeMapper(catalog, overrides = []) {
    const ovs = overrides
      .filter((o) => o.ais_part && String(o.ais_part).trim())
      .map((o) => ({
        pattern: String(o.ais_part).trim().toUpperCase(),
        devon: String(o.devon_part || "").trim(),
        ratio: Number(o.ratio || 1) || 1,
        note: String(o.note || "").trim(),
      }));
    ovs.forEach((o) => (o.re = globToRegex(o.pattern)));
    let runHeight = null;
    const has = (p) => catalog.has(p);

    const rules = [
      function override(line) {
        const pn = line.part.toUpperCase();
        let hits = ovs.filter((o) => o.re.test(pn));
        if (!hits.length) return null;
        const exact = hits.filter((o) => o.pattern === pn);
        if (exact.length) hits = exact;
        const targets = hits.filter((o) => o.devon).map((o) => [o.devon, o.ratio]);
        const notes = hits.filter((o) => o.note).map((o) => o.note).join("; ");
        if (!targets.length) return M(line, [], "ok", notes || "no Devon equivalent needed (override)", "override");
        const missing = targets.map((t) => t[0]).filter((t) => !has(t));
        if (missing.length) return M(line, targets, "review", `override points at ${missing.join(", ")}, which is not in the Devon calculator`, "override");
        return M(line, targets, "ok", notes, "override");
      },

      function panel(line) {
        const pn = line.part.toUpperCase();
        const m = pn.match(PANEL);
        if (!m || pn.startsWith("P-DLPF") || pn.startsWith("P-DLSEOR")) return null;
        const kind = m[1], h = +m[2], w = +m[3];
        const desc = line.description;
        let [height, hnote] = devonHeight(h);
        const notes = hnote ? [hnote] : [];
        let pw = powered(desc);
        if (pw === null) { pw = false; notes.push("could not tell if this panel is powered; quoted non-powered"); }
        const glass = desc.toUpperCase().includes("GLASS") || kind.startsWith("QG") || kind.startsWith("G");
        let family;
        if (glass) {
          if (height === 39 || height === 47) { notes.push(`Devon glass-stacker panels start at 53"H; used 53"H`); height = 53; }
          family = "HM51";
          if (!kind.startsWith("QG")) notes.push('AIS full/partial glass panel quoted as Devon panel + 14" glass stacker');
        } else family = "HM01";
        const part = `${family}.${height}${String(w).padStart(2, "0")}` + (pw ? ".P4" : "");
        if (!has(part)) return M(line, [], "unmapped", `no Devon ${height}"H x ${w}"W ${pw ? "powered " : ""}${glass ? "glass " : ""}panel (${part})`, "panel");
        return M(line, [[part, 1]], notes.length ? "review" : "ok", notes.join("; "), "panel");
      },

      function post(line) {
        const pn = line.part.toUpperCase();
        const m = pn.match(POST);
        if (m) {
          const ways = +m[1];
          const [height, hnote] = devonHeight(+m[2]);
          if (ways === 2) {
            const note = `AIS 2-way post covers both straight runs and L-corners; Devon uses ${connector("inline", height)} for straight panel-to-panel joints. Check the plan.`;
            return M(line, [[connector("2way", height), 1]], "review", [hnote, note].filter(Boolean).join("; "), "post");
          }
          return M(line, [[connector(ways === 3 ? "3way" : "4way", height), 1]], hnote ? "review" : "ok", hnote, "post");
        }
        const d = line.description.toUpperCase();
        if (pn === "P-DLSEOR" || d.includes("END OF RUN")) {
          const height = runHeight || 53;
          return M(line, [[connector("finished_end", height), 1]], "review", `finished end quoted at ${height}"H (the main panel height in this BOM)`, "post");
        }
        if (d.includes("WALL START")) {
          const height = runHeight || 53;
          return M(line, [[connector("wall_start", height), 1]], "review", `wall start quoted at ${height}"H`, "post");
        }
        return null;
      },

      function electrical(line) {
        if (!line.part.toUpperCase().startsWith("E-")) return null;
        const d = line.description.toUpperCase();
        if (d.includes("FEED")) {
          if (d.includes("CEILING")) return M(line, [["BE-CELFD", 1]], "ok", "", "electrical");
          if (d.includes("POLE")) return M(line, [["BE-PP12", 1]], "ok", "", "electrical");
          if (d.includes("SIDE")) return M(line, [["BE-SDFD1", 1]], "review", "AIS side-mounted base infeed quoted as Devon side feed (BE-SDFD1); use BE-ENDFD if it feeds the end of the run", "electrical");
          return M(line, [["BE-ENDFD", 1]], "review", "AIS base infeed quoted as Devon end feed", "electrical");
        }
        if (d.includes("OUTLET") || d.includes("RECEPTACLE") || d.includes("DUPLEX")) {
          const m = d.match(/(?:LINE|CIRCUIT|CKT)\s*(\d)/);
          const n = m ? +m[1] : 1;
          if (n > 4) return M(line, [["BE-REC4", 1]], "review", `AIS circuit ${n} has no Devon equivalent (4-circuit system); used circuit 4`, "electrical");
          const note = m ? "" : "circuit not stated; used circuit 1";
          return M(line, [[`BE-REC${n}`, 1]], note ? "review" : "ok", note, "electrical");
        }
        if (d.includes("JUMPER")) {
          return M(line, [], "review", "Devon P4 panels connect power panel-to-panel, so AIS jumpers are not quoted; add a BE-xxJU pass-thru for each non-powered panel that sits between powered panels", "electrical");
        }
        if (d.includes("DATA")) return M(line, [["BE01439-C", 1]], "review", "AIS data plate quoted as Devon data window", "electrical");
        return null;
      },

      function worksurface(line) {
        const m = line.part.toUpperCase().match(WS);
        if (!m) return null;
        const depth = +m[1], width = +m[2];
        const part = `WS${depth}${String(width).padStart(2, "0")}`;
        if (has(part)) return M(line, [[part, 1]], "ok", "", "worksurface");
        const sizes = catalog.order
          .filter((p) => new RegExp(`^WS${depth}\\d\\d$`).test(p) && +p.slice(4) >= width)
          .map((p) => +p.slice(4)).sort((a, b) => a - b);
        if (sizes.length) {
          const bigger = `WS${depth}${String(sizes[0]).padStart(2, "0")}`;
          return M(line, [[bigger, 1], ["MIS-002", 1]], "review", `no Devon ${depth}x${width}; quoted ${bigger} with custom-cut up-charge`, "worksurface");
        }
        return M(line, [], "unmapped", `no Devon ${depth}x${width} worksurface`, "worksurface");
      },

      function support(line) {
        const pn = line.part.toUpperCase();
        const m = pn.match(CANT);
        if (m) {
          const size = +m[1] >= 22 ? "22" : "16";
          if (m[2] === "S") return M(line, [[`HMP226.${size}`, 1]], "ok", "", "support");
          return M(line, [[size === "22" ? "HMP225.22" : "HMP165.16", 0.5]], "ok", "", "support");
        }
        const d = line.description.toUpperCase();
        if (pn === "WPS-FP" || d.includes("FLAT PLATE")) return M(line, [["ACC-105", 1]], "ok", "", "support");
        if (pn.startsWith("WPS-VC")) {
          let part = has(pn.slice(4)) ? pn.slice(4) : null;
          if (has("WPS-" + pn.slice(4))) part = "WPS-" + pn.slice(4);
          if (part) return M(line, [[part, 1]], "ok", "", "support");
        }
        if (d.includes("CORNER BRACKET")) return M(line, [["HMP455.01-L", 0.5], ["HMP455.01-R", 0.5]], "review", "corner brackets split evenly left/right", "support");
        return null;
      },

      function storage(line) {
        const d = line.description.toUpperCase(), pn = line.part.toUpperCase();
        if (d.includes("PEDESTAL") || pn.startsWith("S-PED")) {
          let part;
          if (d.includes("MOBILE") || pn.includes("MOB")) part = "ECO-MOB BF";
          else if (d.includes("F/F") || pn.replace("BBF", "").includes("FF")) part = "ECO-FF-MT";
          else part = "ECO-BBF-MT";
          return M(line, [[part, 1]], "review", "AIS pedestal quoted as Devon ECO-style pedestal. Confirm size and finish.", "storage");
        }
        if (d.includes("LATERAL")) return M(line, [["G-LF230", 1]], "review", 'AIS lateral quoted as Devon 30" 2-drawer lateral', "storage");
        const wm = line.description.match(WIDTH);
        const w = wm ? wm[1] : null;
        for (const [key, prefix] of [["BINDER", "HMU271"], ["OVERHEAD", "HMU271"], ["FULL HEIGHT SHELF", "HMA282"], ["SHELF", "HMA281"]]) {
          if (d.includes(key) && w && has(`${prefix}.${w}`)) return M(line, [[`${prefix}.${w}`, 1]], "review", "", "storage");
        }
        if (d.includes("TACK") && w && has(`TB${w}`)) return M(line, [[`TB${w}`, 1]], "ok", "", "storage");
        return null;
      },
    ];

    function mapLine(line) {
      for (const rule of rules) {
        const m = rule(line);
        if (m) return m;
      }
      return M(line, [], "unmapped", "no rule or override for this AIS part", "");
    }

    function autoAdd(q) {
      const added = [];
      const add = (part, qty, why) => {
        if (qty > 0 && has(part) && !(part in q)) { q[part] = qty; added.push([part, qty, why]); }
      };
      const count = (prefix) => Object.entries(q).filter(([k]) => k.startsWith(prefix)).reduce((s, [, v]) => s + v, 0);
      add("ACC-106", count("ECO-") + count("G-LF"), "fastener kit, one per pedestal/lateral");
      add("ACC-107", count("HMP165") + count("HMP166") + count("HMP225") + count("HMP226"), "fastener kit, one per cantilever item");
      add("ACC-108", count("HMP455"), "fastener kit, one per corner bracket");
      if (Object.keys(q).some((k) => /^HM(01|51|52|61|62)/.test(k))) add("ACC-110", 1, "touch-up paint, one per panel order at no charge");
      return added;
    }

    function map(lines) {
      const heights = new Map(); // insertion order, so ties go to the first height seen (as in Python)
      for (const ln of lines) {
        const pn = ln.part.toUpperCase();
        const m = pn.match(PANEL);
        if (m && !pn.startsWith("P-DLPF") && !pn.startsWith("P-DLSEOR")) {
          const h = devonHeight(+m[2])[0];
          heights.set(h, (heights.get(h) || 0) + ln.qty);
        }
      }
      runHeight = null;
      let bestCount = -1;
      for (const [h, c] of heights) if (c > bestCount) { runHeight = h; bestCount = c; }

      const mappings = lines.map(mapLine);
      const raw = {}, sources = {}, firstSeen = [];
      for (const m of mappings) {
        for (const [part, ratio] of m.targets) {
          if (!(part in raw)) { raw[part] = 0; firstSeen.push(part); }
          raw[part] += m.source.qty * ratio;
          (sources[part] ||= []);
          if (!sources[part].includes(m.source.part)) sources[part].push(m.source.part);
        }
      }
      const quantities = {};
      for (const p of firstSeen) if (raw[p] > 0) quantities[p] = Math.ceil(raw[p] - 1e-9);

      const warnings = [];
      const sumEnds = (ends) => mappings.filter((m) => ends.some((e) => m.source.part.toUpperCase().endsWith(e))).reduce((s, m) => s + m.source.qty, 0);
      const lefts = sumEnds(["UNCT24L", "UNCT16L"]), rights = sumEnds(["UNCT24R", "UNCT16R"]);
      if (lefts !== rights) warnings.push(`AIS left cantilevers (${lefts}) and right cantilevers (${rights}) don't match; Devon sells them as pairs`);

      const autoAdded = autoAdd(quantities);
      return {
        mappings, quantities, sources, autoAdded, warnings,
        review: mappings.filter((m) => m.status === "review"),
        unmapped: mappings.filter((m) => m.status === "unmapped"),
      };
    }

    return { map, mapLine };
  }

  // ---------------------------------------------------------------- pricing
  function estimate(catalog, quantities, grade, delivery, stations) {
    const lines = Object.entries(quantities).map(([part, qty]) => {
      const item = catalog.items[part];
      const lp = listPrice(item, grade);
      return { part, description: item.description, qty, listEach: lp, netEach: lp * catalog.netMultiplier, weight: item.weight * qty, row: item.row };
    }).sort((a, b) => a.row - b.row);
    lines.forEach((l) => { l.netExt = l.netEach * l.qty; l.listExt = l.listEach * l.qty; });
    const product = lines.reduce((s, l) => s + l.netExt, 0);
    const surcharge = product * catalog.surchargeRate;
    const total = product + surcharge + (delivery || 0);
    return {
      lines, listTotal: lines.reduce((s, l) => s + l.listExt, 0), product, surcharge, delivery: delivery || 0, total,
      weight: lines.reduce((s, l) => s + l.weight, 0), stations: stations || null,
      perStation: stations ? total / stations : null,
    };
  }

  // ---------------------------------------------------------------- writer
  const colIndex = (col) => [...col].reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0);

  function cellXml(ref, style, value) {
    const s = style ? ` s="${style}"` : "";
    if (value === null || value === undefined || value === "") return `<c r="${ref}"${s}/>`;
    if (typeof value === "number") return `<c r="${ref}"${s}><v>${value}</v></c>`;
    return `<c r="${ref}"${s} t="inlineStr"><is><t>${escapeXml(value)}</t></is></c>`;
  }

  function setCell(xml, ref, value) {
    const row = +ref.replace(/[A-Z]+/, ""), col = ref.replace(/\d+/, "");
    const cellRe = new RegExp(`<c r="${ref}"([^>]*?)(?:/>|>[\\s\\S]*?</c>)`);
    const m = xml.match(cellRe);
    if (m) {
      if (m[0].includes("<f")) throw new Error(`refusing to overwrite formula cell ${ref}`);
      const style = (m[1].match(/s="(\d+)"/) || [])[1];
      return xml.slice(0, m.index) + cellXml(ref, style, value) + xml.slice(m.index + m[0].length);
    }
    const rowRe = new RegExp(`<row r="${row}"[^>]*?(/>|>([\\s\\S]*?)</row>)`);
    const rm = xml.match(rowRe);
    if (!rm) throw new Error(`row ${row} not found in the calculator`);
    const add = cellXml(ref, null, value);
    if (rm[1] === "/>") {
      const opened = rm[0].slice(0, -2) + ">";
      return xml.slice(0, rm.index) + opened + add + "</row>" + xml.slice(rm.index + rm[0].length);
    }
    const body = rm[2], bodyStart = rm.index + rm[0].indexOf(">") + 1;
    const cre = /<c r="([A-Z]+)\d+"/g;
    let cm;
    while ((cm = cre.exec(body))) {
      if (colIndex(cm[1]) > colIndex(col)) {
        const pos = bodyStart + cm.index;
        return xml.slice(0, pos) + add + xml.slice(pos);
      }
    }
    const pos = bodyStart + body.length;
    return xml.slice(0, pos) + add + xml.slice(pos);
  }

  function fillSheet(sheet, catalog, quantities, header) {
    for (const p of catalog.order) sheet = setCell(sheet, "C" + catalog.items[p].row, null);
    for (const [part, qty] of Object.entries(quantities)) {
      const item = catalog.items[part];
      if (!item) throw new Error(`${part} is not in the Devon calculator`);
      sheet = setCell(sheet, "C" + item.row, qty);
    }
    const g = header.grade || 0;
    const fields = [
      ["B4", ""], ["B6", header.project || ""], ["B7", header.description || ""], ["B8", ""],
      ["B9", header.date || ""], ["B11", header.shipTo || ""], ["J10", g + 1], ["B16", `${GRADES[g]}(Grade ${g + 1})`],
    ];
    if (header.dealer != null) fields.push(["B5", header.dealer]);
    if (header.trim != null) fields.push(["B14", header.trim]);
    if (header.delivery != null) fields.push(["G444", header.delivery]);
    if (header.stations != null) fields.push(["G450", header.stations]);
    for (const [ref, v] of fields) sheet = setCell(sheet, ref, v);
    return sheet.replace(/(<f[^>]*?(?:\/>|>[^<]*<\/f>))<v>[^<]*<\/v>/g, "$1");
  }

  /**
   * Fill a copy of the calculator. format "xlsm" keeps Devon's macros;
   * "xlsx" drops them (hosted pages can only hand out .xlsx).
   */
  async function writeQuote(zipLib, calcBytes, catalog, quantities, header, format = "xlsm") {
    const zip = await zipLib.loadAsync(calcBytes);
    let sheet = await zip.file(SHEET).async("string");
    let wb = await zip.file(WORKBOOK).async("string");
    sheet = fillSheet(sheet, catalog, quantities, header);
    if (wb.includes("<calcPr/>")) wb = wb.replace("<calcPr/>", '<calcPr fullCalcOnLoad="1"/>');
    else if (wb.includes("<calcPr") && !wb.includes("fullCalcOnLoad")) wb = wb.replace("<calcPr", '<calcPr fullCalcOnLoad="1"');
    zip.file(SHEET, sheet);
    zip.file(WORKBOOK, wb);
    if (format === "xlsx") {
      let ct = await zip.file("[Content_Types].xml").async("string");
      ct = ct.replace("application/vnd.ms-excel.sheet.macroEnabled.main+xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
        .replace(/<Override[^>]*PartName="\/xl\/vbaProject\.bin"[^>]*\/>/, "")
        .replace(/<Default[^>]*Extension="bin"[^>]*ContentType="application\/vnd\.ms-office\.vbaProject"[^>]*\/>/, "");
      zip.file("[Content_Types].xml", ct);
      const relsPath = "xl/_rels/workbook.xml.rels";
      if (zip.file(relsPath)) {
        const rels = (await zip.file(relsPath).async("string")).replace(/<Relationship[^>]*Target="vbaProject\.bin"[^>]*\/>/, "");
        zip.file(relsPath, rels);
      }
      zip.remove("xl/vbaProject.bin");
    }
    return zip.generateAsync({ type: "uint8array", compression: "DEFLATE" });
  }

  // ---------------------------------------------------------------- report
  // toFixed rounds the exact binary value, as Python's format() does.
  const money = (x) => {
    const [i, f] = Math.abs(x).toFixed(2).split(".");
    return (x < 0 ? "-$" : "$") + i.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + "." + f;
  };
  const fmtQty = (n) => String(Number.isInteger(n) ? n : +n.toFixed(6));

  function finishes(lines) {
    const seen = new Map();
    for (const ln of lines) {
      for (const o of ln.options || []) {
        const g = o.group, d = o.description;
        if (!g || !d) continue;
        const dl = d.toLowerCase();
        if (["grade", "no ", "(fabric", "insert laminates", "divi insert"].some((p) => dl.startsWith(p))) continue;
        if (["fabric", "paint", "laminate", "trim", "edge", "glass", "color"].some((k) => g.toLowerCase().includes(k))) {
          const key = g + "\u0000" + d;
          seen.set(key, (seen.get(key) || 0) + ln.qty);
        }
      }
    }
    return [...seen.entries()]
      .map(([k, q]) => { const [g, d] = k.split("\u0000"); return { group: g, selection: d, pieces: q }; })
      .sort((a, b) => (a.group + "\u0000" + a.selection < b.group + "\u0000" + b.selection ? -1 : 1));
  }

  function crosswalkCsv(result) {
    const q = (v) => (/[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
    const out = [["ais_part", "ais_description", "ais_qty", "tag", "devon_part", "devon_qty", "status", "note"].join(",")];
    for (const m of result.mappings) {
      const s = m.source;
      if (!m.targets.length) out.push([s.part, s.description, fmtQty(s.qty), s.tag, "", "", m.status, m.note].map(q).join(","));
      for (const [part, ratio] of m.targets) out.push([s.part, s.description, fmtQty(s.qty), s.tag, part, fmtQty(s.qty * ratio), m.status, m.note].map(q).join(","));
    }
    return out.join("\r\n") + "\r\n";
  }

  function reportMd({ project, bomFile, quoteFile, catalog, grade, lines, result, est, notes = "", drawings = [] }) {
    const o = [];
    const w = (s) => o.push(s);
    w(`# Devon quote review · ${project || "untitled project"}\n`);
    w(`- AIS bill of materials: \`${bomFile}\` (${lines.length} lines, ${fmtQty(lines.reduce((s, l) => s + l.qty, 0))} pieces)`);
    w(`- Devon calculator filled in: \`${quoteFile}\``);
    w(`- Price list: ${catalog.title} · fabric grade ${GRADES[grade]} · net = list × ${catalog.netMultiplier}`);
    if (drawings.length) w(`- 2D plan(s) for checking: ` + drawings.map((d) => `\`${d}\``).join(", "));
    w("");
    w("## Estimated Devon cost\n");
    w("| | |\n|---|---:|");
    w(`| List | ${money(est.listTotal)} |`);
    w(`| Product net | ${money(est.product)} |`);
    w(`| Surcharge (${Math.round(catalog.surchargeRate * 100)}%) | ${money(est.surcharge)} |`);
    w(`| Delivery (estimate) | ${money(est.delivery)} |`);
    w(`| **Total** | **${money(est.total)}** |`);
    if (est.perStation) w(`| Per station (${est.stations}) | ${money(est.perStation)} |`);
    w(`| Weight (approx.) | ${est.weight.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ",")} lbs |\n`);
    w("These totals are this tool's own math. The calculator recalculates its own figures when you open it, and the two should match.\n");
    const { review, unmapped } = result;
    w(`## Needs your attention (${unmapped.length} unmapped, ${review.length} to confirm)\n`);
    if (result.warnings.length) { result.warnings.forEach((x) => w(`- ⚠️ ${x}`)); w(""); }
    if (unmapped.length) {
      w("### Unmapped: not in the Devon quote yet\n");
      w("Add these by hand, or save a correction on the page so the tool learns them.\n");
      w("| AIS part | Description | Qty | Why |\n|---|---|---:|---|");
      unmapped.forEach((m) => w(`| ${m.source.part} | ${m.source.description} | ${fmtQty(m.source.qty)} | ${m.note} |`));
      w("");
    }
    if (review.length) {
      w("### Mapped: please confirm\n");
      w("| AIS part | Qty | → Devon | Check |\n|---|---:|---|---|");
      review.forEach((m) => w(`| ${m.source.part} | ${fmtQty(m.source.qty)} | ${m.targets.map((t) => t[0]).join(", ") || "—"} | ${m.note} |`));
      w("");
    }
    if (!unmapped.length && !review.length && !result.warnings.length) w("Nothing flagged.\n");
    const fin = finishes(lines);
    if (fin.length) {
      w("## AIS finishes in the design\n");
      w("Pick the matching Devon trim, fabric and worksurface colors. The calculator's TRIM field is currently left as the template value.\n");
      w("| Option | Selection | Pieces |\n|---|---|---:|");
      fin.forEach((f) => w(`| ${f.group} | ${f.selection} | ${fmtQty(f.pieces)} |`));
      w("");
    }
    if (notes.trim()) { w("## Design notes / dictation\n"); w(notes.trim() + "\n"); }
    w("## Devon line items\n");
    w("| Devon part | Description | Qty | Net ea | Net ext | From AIS |\n|---|---|---:|---:|---:|---|");
    const auto = new Set(result.autoAdded.map((a) => a[0]));
    for (const l of est.lines) {
      const src = (result.sources[l.part] || []).join(", ") || (auto.has(l.part) ? "auto-added" : "");
      w(`| ${l.part} | ${l.description} | ${l.qty} | ${money(l.netEach)} | ${money(l.netExt)} | ${src} |`);
    }
    w("");
    if (result.autoAdded.length) w("Auto-added: " + result.autoAdded.map(([p, q, why]) => `${p} ×${q} (${why})`).join("; ") + "\n");
    return o.join("\n");
  }

  const safeStem = (name) => String(name).replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "") || "quote";

  return {
    GRADES, buildCatalog, loadCalculator, listPrice, parseSif, parseCsv, parseTable, parseBom,
    makeMapper, devonHeight, connector, estimate, setCell, fillSheet, writeQuote,
    finishes, crosswalkCsv, reportMd, safeStem,
  };
});
