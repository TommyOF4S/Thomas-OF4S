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
  const NOT_SKUS = ["HMA224."]; // rows in Devon's calculator that aren't real SKUs
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
      if (items[a] || NOT_SKUS.some((x) => a.startsWith(x))) continue; // ACC-110 is listed twice; HMA224 isn't a real SKU
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
      finished_end: `HMA128.${a}`, wall_start: `HMA199.${b}`,
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
    let plan = null; // joints read from the 2D plan, when one was given
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
        const isEnd = pn === "P-DLSEOR" || line.description.toUpperCase().includes("END OF RUN");
        if (plan && (m || isEnd)) return M(line, [], "ok", "connectors and finished ends are counted from the 2D plan", "plan");
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
        if (isEnd) {
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

    function heightChanges(warnings) {
      const fillers = new Map();
      for (const ch of plan.heightChanges || []) {
        const part = DOT_COLORS[ch.color];
        if (!ch.joint) { warnings.push(`A ${ch.color} dot on page ${ch.page} isn't on a panel joint, so its filler strip (${part}) was not quoted. Put the dot right on the joint.`); continue; }
        if (!has(part)) { warnings.push(`${part} (${ch.color} dot) isn't in the Devon calculator; add it by hand.`); continue; }
        fillers.set(part, (fillers.get(part) || 0) + 1);
      }
      return fillers;
    }

    function planConnectors(lines, bomHeights) {
      const height = runHeight || 53;
      const c = plan.counts;
      const warnings = [];
      const fillers = heightChanges(warnings);
      const parts = [["straight", "inline"], ["l", "2way"], ["tee", "3way"], ["cross", "4way"], ["ends", "finished_end"]]
        .filter(([kind]) => c[kind]).map(([kind, dk]) => [kind, connector(dk, height), c[kind]]);
      for (const [p, q] of fillers) parts.push(["filler", p, q]);
      if (bomHeights.length > 1 && !(plan.heightChanges || []).length) {
        warnings.push(`The BOM has panels at more than one height; plan connectors are all quoted at ${height}"H. Mark each height change on the CET plan with a colored dot (red 39/53, blue 39/67, yellow 47/53, green 47/67, black 53/67) to add its high/low filler strip.`);
      }
      if (c.angled) warnings.push(`The 2D plan has ${c.angled} joint(s) at an angle other than 90 or 180 degrees. Devon has no angled connector; check those runs.`);
      if (c.other) warnings.push(`The 2D plan has ${c.other} joint(s) where more than four panels meet. Check those by hand.`);
      const bom = { panels: 0, pf2: 0, pf3: 0, pf4: 0, seor: 0 };
      const bomWidths = new Map();
      for (const ln of lines) {
        const pn = ln.part.toUpperCase();
        const pm = pn.match(POST);
        if (pm) bom["pf" + pm[1]] += ln.qty;
        else if (pn === "P-DLSEOR" || ln.description.toUpperCase().includes("END OF RUN")) bom.seor += ln.qty;
        else {
          const m = pn.match(PANEL);
          if (m) { bom.panels += ln.qty; bomWidths.set(+m[3], (bomWidths.get(+m[3]) || 0) + ln.qty); }
        }
      }
      const n = (k, word) => `${k} ${word}` + (k === 1 ? "" : "s");
      const checks = [
        ["panels", plan.panels, n(plan.panels, "panel"), "panels"],
        ["pf2", c.straight + c.l, `${n(c.straight, "straight joint")} + ${n(c.l, "corner")}`, "2-way posts"],
        ["pf3", c.tee, n(c.tee, "three-way joint"), "3-way posts"],
        ["pf4", c.cross, n(c.cross, "four-way joint"), "4-way posts"],
        ["seor", c.ends, n(c.ends, "free end"), "end-of-run shrouds"],
      ];
      for (const [key, planN, planText, bomText] of checks) {
        if (bom[key] && bom[key] !== planN) warnings.push(`The 2D plan shows ${planText}, but the AIS BOM has ${fmtQty(bom[key])} ${bomText}. Make sure the plan and the BOM are the same revision.`);
      }
      const pw = plan.widths;
      const same = bomWidths.size === Object.keys(pw).length && [...bomWidths].every(([k, v]) => pw[k] === v);
      if (bomWidths.size && Object.keys(pw).length && !same) {
        const fmt = (entries) => entries.sort((a, b) => a[0] - b[0]).map(([k, v]) => `${fmtQty(v)} x ${k}"`).join(", ");
        warnings.push(`Panel widths differ: the plan has ${fmt(Object.entries(pw).map(([k, v]) => [+k, v]))}; the BOM has ${fmt([...bomWidths])}.`);
      }
      return [parts, warnings];
    }

    function map(lines, planResult = null) {
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
      plan = planResult && planResult.panels ? planResult : null;

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
      const warnings = [];
      let planParts = [];
      if (plan) {
        const [parts, planWarnings] = planConnectors(lines, [...heights.keys()]);
        planParts = parts;
        warnings.push(...planWarnings);
        for (const [, part, qty] of parts) {
          if (!(part in raw)) { raw[part] = 0; firstSeen.push(part); }
          raw[part] += qty;
          (sources[part] ||= []);
          if (!sources[part].includes("2D plan")) sources[part].push("2D plan");
        }
      }
      const quantities = {};
      for (const p of firstSeen) if (raw[p] > 0) quantities[p] = Math.ceil(raw[p] - 1e-9);

      const sumEnds = (ends) => mappings.filter((m) => ends.some((e) => m.source.part.toUpperCase().endsWith(e))).reduce((s, m) => s + m.source.qty, 0);
      const lefts = sumEnds(["UNCT24L", "UNCT16L"]), rights = sumEnds(["UNCT24R", "UNCT16R"]);
      if (lefts !== rights) warnings.push(`AIS left cantilevers (${lefts}) and right cantilevers (${rights}) don't match; Devon sells them as pairs`);

      const autoAdded = autoAdd(quantities);
      return {
        mappings, quantities, sources, autoAdded, warnings, plan, planParts,
        review: mappings.filter((m) => m.status === "review"),
        unmapped: mappings.filter((m) => m.status === "unmapped"),
      };
    }

    return { map, mapLine };
  }

  // ---------------------------------------------------------------- 2D plan (port of plan.py)
  const STD_WIDTHS = [12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72];
  const PANEL_INCHES = 2.0, POST_GAP = 1.4, WIDTH_TOLERANCE = 1.5, JOIN_FACTOR = 2.0;
  const PLAN_KINDS = ["straight", "l", "tee", "cross", "ends", "angled", "other"];
  const r2 = (v) => Math.round(v * 100) / 100;
  const MARK_JOINT_FACTOR = 6.0, MARK_MAX_FACTOR = 20.0;
  // Dot color -> Devon high/low filler strip
  const DOT_COLORS = { red: "HMHL3953", blue: "HMHL3967", yellow: "HMHL4753", green: "HMHL4767", black: "HMHL5367" };

  function dotColor(f) {
    if (!f) return null;
    const [r, g, b] = f;
    if (Math.max(r, g, b) < 0.1) return "black";
    if (r > 0.6 && g < 0.4 && b < 0.4) return "red";
    if (r > 0.6 && g > 0.6 && b < 0.4) return "yellow";
    if (g > 0.45 && r < 0.4 && b < 0.4) return "green";
    if (b > 0.5 && r < 0.4 && g < 0.5) return "blue";
    return null;
  }

  /** Colored dots the designer put on joints where the panel height changes. */
  function heightMarks(shapes, joints, t, page) {
    const out = [];
    for (const s of shapes) {
      const color = dotColor(s.fill);
      const w = s.x1 - s.x0, h = s.y1 - s.y0;
      if (!color || Math.max(w, h) > MARK_MAX_FACTOR * t || Math.min(w, h) <= 0 || w / h < 0.5 || w / h > 2) continue;
      const x = (s.x0 + s.x1) / 2, y = (s.y0 + s.y1) / 2;
      let near = null, nd = Infinity;
      for (const j of joints) { const d = Math.hypot(j.x - x, j.y - y); if (d < nd) { nd = d; near = j; } }
      const joint = near && nd <= MARK_JOINT_FACTOR * t ? near.kind : null;
      if (joint === null && color === "black") continue; // CET plans are full of small black shapes
      out.push({ x, y, page, joint, color });
    }
    return out;
  }

  function nominalWidth(length, t) {
    const implied = (length / t) * PANEL_INCHES + POST_GAP;
    let best = STD_WIDTHS[0];
    for (const s of STD_WIDTHS) if (Math.abs(implied - s) < Math.abs(implied - best)) best = s;
    return Math.abs(implied - best) <= WIDTH_TOLERANCE ? best : null;
  }
  const neutralGray = (f) => !!f && Math.max(...f) - Math.min(...f) < 0.02 && f[0] > 0.5 && f[0] < 0.97;

  function findPanels(rects) {
    const groups = new Map();
    for (const r of rects) {
      const w = r.x1 - r.x0, h = r.y1 - r.y0, t = Math.min(w, h), len = Math.max(w, h);
      if (t >= 0.05 && t <= 5 && len >= 3 * t && neutralGray(r.fill)) {
        const key = [r2(t), ...r.fill.map(r2)].join("|");
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(r);
      }
    }
    let best = null, bestFit = 0;
    for (const [key, rs] of groups) {
      const t = +key.split("|")[0];
      const fit = rs.filter((r) => nominalWidth(Math.max(r.x1 - r.x0, r.y1 - r.y0), t)).length;
      if (fit >= 2 && fit / rs.length >= 0.9 && fit > bestFit) { best = key; bestFit = fit; }
    }
    if (best === null) return [[], null];
    const t = +best.split("|")[0];
    return [groups.get(best).filter((r) => nominalWidth(Math.max(r.x1 - r.x0, r.y1 - r.y0), t)), t];
  }

  function jointsOnPage(panels, t, page) {
    const ends = [];
    panels.forEach((r, i) => {
      const w = r.x1 - r.x0, h = r.y1 - r.y0, cx = (r.x0 + r.x1) / 2, cy = (r.y0 + r.y1) / 2;
      const [a, b] = w >= h ? [[r.x0, cy], [r.x1, cy]] : [[cx, r.y0], [cx, r.y1]];
      for (const [e, o] of [[a, b], [b, a]]) {
        const dx = e[0] - o[0], dy = e[1] - o[1], n = Math.hypot(dx, dy) || 1;
        ends.push([e[0], e[1], dx / n, dy / n, i]);
      }
    });
    const parent = ends.map((_, i) => i);
    const find = (x) => { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; };
    const tol = JOIN_FACTOR * t;
    for (let i = 0; i < ends.length; i++) {
      for (let j = i + 1; j < ends.length; j++) {
        if (ends[i][4] !== ends[j][4] && Math.hypot(ends[i][0] - ends[j][0], ends[i][1] - ends[j][1]) <= tol) parent[find(i)] = find(j);
      }
    }
    const groups = new Map();
    ends.forEach((e, i) => { const k = find(i); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(e); });
    const out = [];
    for (const g of groups.values()) {
      const x = g.reduce((s, e) => s + e[0], 0) / g.length, y = g.reduce((s, e) => s + e[1], 0) / g.length;
      let kind;
      if (g.length === 1) kind = "ends";
      else if (g.length === 2) {
        const dot = g[0][2] * g[1][2] + g[0][3] * g[1][3];
        kind = dot < -0.95 ? "straight" : Math.abs(dot) < 0.15 ? "l" : "angled";
      } else if (g.length === 3) kind = "tee";
      else if (g.length === 4) kind = "cross";
      else kind = "other";
      out.push({ kind, x, y, page });
    }
    return out;
  }

  /** pages: [[{x0, y0, x1, y1, fill: [r, g, b] | null}]] (0-1 colors); shapes: filled paths per page, same form */
  function analyzeRects(pages, shapes = null) {
    const res = { counts: Object.fromEntries(PLAN_KINDS.map((k) => [k, 0])), widths: {}, joints: [], pages: [], panels: 0, heightChanges: [] };
    pages.forEach((rects, p) => {
      const [panels, t] = findPanels(rects);
      res.pages.push({ page: p + 1, panels: panels.length, thickness: t });
      if (!panels.length) return;
      for (const r of panels) {
        const w = nominalWidth(Math.max(r.x1 - r.x0, r.y1 - r.y0), t);
        res.widths[w] = (res.widths[w] || 0) + 1;
        res.panels++;
      }
      const js = jointsOnPage(panels, t, p + 1);
      res.joints.push(...js);
      js.forEach((j) => res.counts[j.kind]++);
      if (shapes) res.heightChanges.push(...heightMarks(shapes[p], js, t, p + 1));
    });
    return res;
  }

  /** Axis-aligned filled/stroked rectangles on every page, read with PDF.js (v3 operator lists). */
  async function pdfRects(pdfjsLib, bytes, { maxPages = 20 } = {}) {
    const OPS = pdfjsLib.OPS;
    const doc = await pdfjsLib.getDocument({ data: bytes, disableFontFace: true, isEvalSupported: false }).promise;
    const pages = [], extras = [];
    const views = [];
    for (let n = 1; n <= Math.min(doc.numPages, maxPages); n++) {
      const page = await doc.getPage(n);
      const ops = await page.getOperatorList();
      const rects = [], shapes = [];
      let ctm = [1, 0, 0, 1, 0, 0], fill = [0, 0, 0];
      const stack = [];
      let pending = [];
      const mul = (m, c) => [m[0] * c[0] + m[1] * c[2], m[0] * c[1] + m[1] * c[3], m[2] * c[0] + m[3] * c[2], m[2] * c[1] + m[3] * c[3],
        m[4] * c[0] + m[5] * c[2] + c[4], m[4] * c[1] + m[5] * c[3] + c[5]];
      const tp = (x, y) => [ctm[0] * x + ctm[2] * y + ctm[4], ctm[1] * x + ctm[3] * y + ctm[5]];
      const toRect = (pts) => {
        if (pts.length >= 2) { const a = pts[0], b = pts[pts.length - 1]; if (Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1]) < 1e-6) pts = pts.slice(0, -1); }
        if (pts.length !== 4) return null;
        const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
        const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
        const eps = 1e-3;
        const onCorner = pts.every((p) => (Math.abs(p[0] - x0) < eps || Math.abs(p[0] - x1) < eps) && (Math.abs(p[1] - y0) < eps || Math.abs(p[1] - y1) < eps));
        const corners = new Set(pts.map((p) => `${Math.abs(p[0] - x0) < eps}${Math.abs(p[1] - y0) < eps}`));
        return onCorner && corners.size === 4 ? { x0, y0, x1, y1 } : null;
      };
      for (let i = 0; i < ops.fnArray.length; i++) {
        const fn = ops.fnArray[i], args = ops.argsArray[i];
        if (fn === OPS.save) stack.push([ctm, fill]);
        else if (fn === OPS.restore) { const s = stack.pop(); if (s) [ctm, fill] = s; }
        else if (fn === OPS.transform) ctm = mul(args, ctm);
        else if (fn === OPS.paintFormXObjectBegin) { stack.push([ctm, fill]); if (args && args[0]) ctm = mul(args[0], ctm); }
        else if (fn === OPS.paintFormXObjectEnd) { const s = stack.pop(); if (s) [ctm, fill] = s; }
        else if (fn === OPS.setFillRGBColor) fill = [args[0] / 255, args[1] / 255, args[2] / 255];
        else if (fn === OPS.constructPath) {
          const [sub, coords] = args;
          let k = 0, cur = null;
          const push = () => { if (cur) pending.push(cur); cur = null; };
          for (const op of sub) {
            if (op === OPS.moveTo) { push(); cur = [tp(coords[k], coords[k + 1])]; k += 2; }
            else if (op === OPS.lineTo) { (cur ||= []).push(tp(coords[k], coords[k + 1])); k += 2; }
            else if (op === OPS.curveTo) {
              (cur ||= []).curved = true;
              for (let q = 0; q < 6; q += 2) cur.push(tp(coords[k + q], coords[k + q + 1]));
              k += 6;
            } else if (op === OPS.curveTo2 || op === OPS.curveTo3) {
              (cur ||= []).curved = true;
              for (let q = 0; q < 4; q += 2) cur.push(tp(coords[k + q], coords[k + q + 1]));
              k += 4;
            } else if (op === OPS.closePath) push();
            else if (op === OPS.rectangle) {
              const [x, y, w, h] = coords.slice(k, k + 4); k += 4;
              push();
              pending.push([tp(x, y), tp(x + w, y), tp(x + w, y + h), tp(x, y + h)]);
            }
          }
          push();
        } else if ([OPS.fill, OPS.eoFill, OPS.fillStroke, OPS.eoFillStroke, OPS.closeFillStroke, OPS.closeEOFillStroke,
          OPS.stroke, OPS.closeStroke, OPS.endPath].includes(fn)) {
          const filled = [OPS.fill, OPS.eoFill, OPS.fillStroke, OPS.eoFillStroke, OPS.closeFillStroke, OPS.closeEOFillStroke].includes(fn);
          if (fn !== OPS.endPath) {
            for (const pts of pending) {
              const r = pts.curved ? null : toRect(pts);
              if (r) rects.push({ ...r, fill: filled ? fill.slice() : null });
              if (filled && pts.length) {
                const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
                shapes.push({ x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys), fill: fill.slice() });
              }
            }
          }
          pending = [];
        }
      }
      pages.push(rects);
      extras.push(shapes);
      views.push(page);
    }
    return { pages, extras, pdfPages: views };
  }

  async function analyzePdf(pdfjsLib, bytes) {
    const { pages, extras, pdfPages } = await pdfRects(pdfjsLib, bytes);
    return { result: analyzeRects(pages, extras), pdfPages };
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
    if (result.plan) {
      w("## Connectors from the 2D plan\n");
      w(`Read ${result.plan.panels} panels off the plan and measured every joint. These replace the AIS post counts.\n`);
      w("| Joint on the plan | Qty | Devon part |\n|---|---:|---|");
      const labels = { straight: "Two panels in a straight line (180°)", l: "Corner, two panels at 90°", tee: "Three panels", cross: "Four panels", ends: "Free end of a run",
        filler: "Height change (colored dot): high/low filler strip" };
      for (const [k, p, q] of result.planParts) w(`| ${labels[k]} | ${q} | ${p} |`);
      w("");
      w("Free ends are quoted as finished ends. Swap any that stop at a wall to a wall start (HMA199).\n");
    }
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
    makeMapper, devonHeight, connector, DOT_COLORS, estimate, setCell, fillSheet, writeQuote,
    finishes, crosswalkCsv, reportMd, safeStem, analyzeRects, pdfRects, analyzePdf, nominalWidth,
  };
});
