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
  const DIVI_TO_DEVON_HEIGHT = { 42: 39, 50: 53, 82: 85 }; // set equivalents; other heights round up
  const HEIGHT_TOLERANCE = 6;

  function connector(kind, height) {
    const [a, b] = CONNECTOR_CODES[height];
    return {
      "2way": `HMA130.${a}`, "3way": `HMA137.${a}`, "4way": `HMC132.${b}`, inline: `HMP213.${b}`,
      finished_end: `HMA128.${a}`, wall_start: `HMA199.${b}`,
    }[kind];
  }

  /** divi50: the Devon height chosen for 50" Divi panels (53 or 47). */
  function devonHeight(h, divi50 = 53) {
    if (h === 50) return [divi50, ""];
    if (DIVI_TO_DEVON_HEIGHT[h]) return [DIVI_TO_DEVON_HEIGHT[h], ""];
    for (const d of DEVON_HEIGHTS) {
      if (h <= d) return [d, d - h > HEIGHT_TOLERANCE ? `AIS ${h}"H rounds up to Devon ${d}"H` : ""];
    }
    return [85, `AIS ${h}"H is taller than any Devon panel; used 85"H`];
  }

  const PANEL = /^P-DL([A-Z]+?)(\d{2})(\d{2})$/;
  const POST = /^P-DLPF(?:PP(?=[23]))?([234])(\d{2})$/; // P-DLPFPP2/PP3 are 2-way/3-way posts too
  const WS = /^W-WS(\d{2})(\d{2})$/;
  const CANT = /^WPS-UNCT(\d{2})([LRS])$/;
  const CANT_DEPTH = /(\d{2})\s*(?:D\b|"|in\b)/i;
  const CANTILEVER_PAIR_NOTE = "Devon sells cantilevers as L/R pairs: pairs = (AIS lefts + rights) / 2, rounded up";
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

  function makeMapper(catalog, overrides = [], { divi50 = 53 } = {}) {
    if (divi50 !== 53 && divi50 !== 47) throw new Error(`50" Divi panels can be quoted as 53" or 47" Devon panels, not ${divi50}"`);
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
    let widthHeights = new Map(); // Divi heights the BOM has in each panel width
    let heightPoints = []; // {page, x, y, part, src} where panel labels show a height change
    let marks = null; // pink dashes and colored dots read from 2D images
    const has = (p) => catalog.has(p);

    const rules = [
      // Posts and end-of-run shrouds the 2D plan counts. Runs before saved corrections, so a correction made for a
      // quote without a 2D doesn't add the same connectors a second time.
      function drawing(line) {
        const pn = line.part.toUpperCase();
        const m = pn.match(POST);
        const isEnd = pn === "P-DLSEOR" || line.description.toUpperCase().includes("END OF RUN");
        let note;
        if (plan && (m || isEnd)) note = "connectors and finished ends are counted from the 2D plan";
        else return null;
        const saved = rules[1](line);
        if (saved && saved.targets.length) note += `; the saved correction to ${saved.targets.map(([p]) => p).join(", ")} is used only without a 2D`;
        return M(line, [], "ok", note, "plan");
      },
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
        let [height, hnote] = devonHeight(h, divi50);
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
        if (m) {
          const ways = +m[1];
          const [height, hnote] = devonHeight(+m[2], divi50);
          // an AIS 2-way post is a corner
          return M(line, [[connector(ways === 2 ? "2way" : ways === 3 ? "3way" : "4way", height), 1]], hnote ? "review" : "ok", hnote, "post");
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
        const d = line.description.toUpperCase();
        const m = pn.match(CANT);
        let depth = null, hand = null;
        if (m) { depth = +m[1]; hand = m[2]; }
        else if (d.includes("CANTILEVER")) {
          hand = d.includes("SHARED") ? "S" : d.includes("LEFT") ? "L" : d.includes("RIGHT") ? "R" : null;
          const dm = line.description.match(CANT_DEPTH);
          depth = dm ? +dm[1] : 24;
        }
        if (hand) {
          const size = depth >= 22 ? "22" : "16";
          if (hand === "S") return M(line, [[`HMP226.${size}`, 1]], "ok", "", "support");
          // Each AIS left or right is half a Devon pair; the total is rounded up after adding them all.
          return M(line, [[size === "22" ? "HMP225.22" : "HMP165.16", 0.5]], "ok", CANTILEVER_PAIR_NOTE, "support");
        }
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

    const JOINT_WORDS = { l: "corner", tee: "3-way joint", cross: "4-way joint", ends: "free end", angled: "angled joint", other: "joint of 5+ panels" };

    function pinkDashCount(warnings) {
      const dashes = plan.pinkDashes || [];
      const on = dashes.filter((d) => d.joint);
      const off = dashes.length - on.length;
      const n = (k, word) => `${k} ${word}` + (k === 1 ? "" : "s");
      const unmarked = plan.counts.straight - on.filter((d) => d.joint === "straight").length;
      if (unmarked > 0) {
        const one = unmarked === 1;
        warnings.push(`${n(unmarked, "straight joint")} on the plan ${one ? "has" : "have"} no pink dash, so ${one ? "it was" : "they were"} not quoted as panel-to-panel connectors. Add a pink dash in CET, or check the plan.`);
      }
      const other = new Map();
      for (const d of on) if (d.joint !== "straight") other.set(d.joint, (other.get(d.joint) || 0) + 1);
      for (const [kind, k] of other) {
        const one = k === 1;
        warnings.push(`${n(k, "pink dash")} ${one ? "is" : "are"} on a ${JOINT_WORDS[kind] || "joint"}, which also gets its own connector; check ${one ? "it" : "them"}.`);
      }
      if (off) {
        const one = off === 1;
        warnings.push(`${n(off, "pink dash")} ${one ? "is" : "are"}n't on a panel joint, so ${one ? "it was" : "they were"} not quoted. Put each dash right on the joint.`);
      }
      return on.length;
    }

    function markFillers(warnings) {
      const fillers = new Map();
      for (const color of Object.keys(DOT_COLORS)) {
        const n = (marks.dots || {})[color] || 0;
        if (!n) continue;
        const part = DOT_COLORS[color];
        if (has(part)) fillers.set(part, (fillers.get(part) || 0) + n);
        else warnings.push(`${part} (${color} dot) isn't in the Devon calculator; add it by hand.`);
      }
      return fillers;
    }

    // The AIS SIF doesn't list straight joints (its 2-way posts are corners), so each pink dash on a 2D image
    // adds a panel-to-panel connector, at the BOM's main panel height.
    function imageConnectors(lines, bomHeights) {
      const warnings = [];
      const height = runHeight || 53;
      const parts = [];
      if (marks.pink) parts.push(["pink", connector("inline", height), marks.pink]);
      for (const [p, q] of markFillers(warnings)) parts.push(["filler", p, q]);
      if (bomHeights.length > 1 && !Object.keys(marks.dots || {}).length) {
        warnings.push(`The BOM has panels at more than one height; panel-to-panel connectors are quoted at ${height}"H and the 2D has no colored dots. Mark each height change with a colored dot (red 39/53, blue 39/67, yellow 47/53, green 47/67, purple 53/67) to add its high/low filler strip.`);
      }
      return [parts, warnings];
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

    /** Devon height of a plan panel: its label, else the BOM's only height in that width. */
    function panelHeight(width, height) {
      const known = widthHeights.get(width);
      if (height === null && known && known.size === 1) height = [...known][0];
      return height === null ? null : devonHeight(height, divi50)[0];
    }
    const jointHeights = (panels) => [...new Set(panels.map(([w, h]) => panelHeight(w, h)).filter((h) => h !== null))].sort((a, b) => a - b);

    /** High/low filler strips where panels of different labeled heights meet: one from each lower height up to the tallest. */
    function labelFillers(warnings) {
      const fillers = new Map();
      for (const j of plan.joints) {
        const hs = jointHeights(j.panels);
        if (hs.length < 2) continue;
        const top = hs[hs.length - 1];
        if (hs.length > 2) warnings.push(`A ${JOINT_WORDS[j.kind] || "joint"} on page ${j.page} joins panels at ${hs.join(", ")}"H; quoted a filler strip from each lower height to ${top}"H. Check it.`);
        for (const lo of hs.slice(0, -1)) {
          const part = `HMHL${lo}${top}`;
          if (has(part)) { fillers.set(part, (fillers.get(part) || 0) + 1); heightPoints.push({ page: j.page, x: j.x, y: j.y, part, src: j.src }); }
          else warnings.push(`Panels at ${lo}" and ${top}" meet on page ${j.page}, but Devon's calculator has no filler strip for that change; add it by hand.`);
        }
      }
      return new Map([...fillers].sort((a, b) => (a[0] < b[0] ? -1 : 1)));
    }

    function planConnectors(lines, bomHeights) {
      const def = runHeight || 53;
      const c = plan.counts;
      const warnings = [];
      const labeled = (plan.labels || []).some((l) => l.matched);
      const heightAt = labeled ? (panels) => { const hs = jointHeights(panels || []); return hs.length ? hs[hs.length - 1] : def; } : () => def;
      let dotFillers = heightChanges(warnings);
      const markDots = marks && Object.keys(marks.dots || {}).length;
      if (!(plan.heightChanges || []).length && markDots) dotFillers = markFillers(warnings);
      const dotted = !!((plan.heightChanges || []).length || markDots);
      let fillers = dotFillers;
      if (labeled) {
        const labelWarnings = [];
        const lf = labelFillers(labelWarnings);
        if (!dotted) { fillers = lf; warnings.push(...[...new Set(labelWarnings)].sort()); }
        else {
          const fmt = (f) => [...f].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([p, q]) => `${p} x ${q}`).join(", ") || "none";
          if (fmt(lf) !== fmt(dotFillers)) warnings.push(`The colored dots give filler strips ${fmt(dotFillers)}, but the panel labels on the plan give ${fmt(lf)}. The dots were quoted; check which is right.`);
          heightPoints = [];
        }
      }
      const entries = new Map(); // "kind|devonKind|height" -> qty
      const add = (kind, dk, h, q = 1) => { const k = `${kind}|${dk}|${h}`; entries.set(k, (entries.get(k) || 0) + q); };
      const devonKinds = { straight: "inline", l: "2way", tee: "3way", cross: "4way", ends: "finished_end" };
      const pinkPlan = (plan.pinkDashes || []).length > 0;
      const pinkImage = !pinkPlan && marks && marks.pink;
      for (const j of plan.joints) {
        if (devonKinds[j.kind] && !(j.kind === "straight" && (pinkPlan || pinkImage))) add(j.kind, devonKinds[j.kind], heightAt(j.panels));
      }
      if (pinkPlan) { // the designer marked the panel-to-panel joints: their count wins
        pinkDashCount(warnings);
        for (const d of plan.pinkDashes) if (d.joint) add("pink", "inline", heightAt(d.panels));
      } else if (pinkImage) {
        if (marks.pink !== c.straight) warnings.push(`The 2D image has ${marks.pink} pink dashes but the plan measures ${c.straight} straight joints; the pink dashes were quoted.`);
        const straight = new Map();
        for (const j of plan.joints) if (j.kind === "straight") { const h = heightAt(j.panels); straight.set(h, (straight.get(h) || 0) + 1); }
        let h = def, best = -1;
        for (const [k, v] of straight) if (v > best) { h = k; best = v; }
        add("pink", "inline", h, marks.pink);
      }
      const order = { straight: 0, pink: 1, l: 2, tee: 3, cross: 4, ends: 5 };
      const parts = [...entries].map(([k, q]) => { const [kind, dk, h] = k.split("|"); return [kind, dk, +h, q]; })
        .sort((a, b) => order[a[0]] - order[b[0]] || a[2] - b[2]).map(([kind, dk, h, q]) => [kind, connector(dk, h), q]);
      for (const [p, q] of fillers) parts.push(["filler", p, q]);
      if (labeled) {
        const unknown = new Map();
        for (const j of plan.joints) for (const [w, h] of j.panels || []) if (panelHeight(w, h) === null) unknown.set(w, (unknown.get(w) || 0) + 1);
        let missing = 0;
        for (const v of unknown.values()) missing += Math.ceil(v / 2); // each panel shows up at both of its ends
        if (missing) {
          const ws = [...unknown.keys()].sort((a, b) => a - b).map((w) => `${w}"W`).join(", ");
          warnings.push(`${missing} panel(s) on the plan (${ws}) have no height label, and the BOM has more than one height in that width; their joints were quoted at ${def}"H with no filler strips. Check them.`);
        }
        const stray = plan.labels.filter((l) => !l.matched);
        if (stray.length) warnings.push(`${stray.length} panel label(s) on the plan (${stray.map((l) => l.text).join(", ")}) aren't next to a panel of that width, so they were not used. Check the plan.`);
      } else if (bomHeights.length > 1 && !dotted) {
        warnings.push(`The BOM has panels at more than one height; plan connectors are all quoted at ${def}"H. Export the CET 2D as a PDF with the panel labels showing (letter, height, width, like A6660) so height changes get their high/low filler strips, or mark each height change with a colored dot (red 39/53, blue 39/67, yellow 47/53, green 47/67, purple 53/67).`);
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
        ["pf2", c.l, n(c.l, "corner"), "2-way (corner) posts"],
        ["pf3", c.tee, n(c.tee, "three-way joint"), "3-way posts"],
        ["pf4", c.cross, n(c.cross, "four-way joint"), "4-way posts"],
        ["seor", c.ends, n(c.ends, "free end"), "end-of-run shrouds"],
      ];
      for (const [key, planN, planText, bomText] of checks) {
        if (bom[key] && bom[key] !== planN) warnings.push(`The 2D plan shows ${planText}, but the AIS BOM has ${fmtQty(bom[key])} ${bomText}. Make sure the plan and the BOM are the same revision.`);
      }
      const bomSizes = new Map(), labelSizes = new Map();
      for (const ln of lines) {
        const pn = ln.part.toUpperCase(), m = pn.match(PANEL);
        if (m && !pn.startsWith("P-DLPF") && !pn.startsWith("P-DLSEOR")) { const k = `${+m[2]}|${+m[3]}`; bomSizes.set(k, (bomSizes.get(k) || 0) + ln.qty); }
      }
      for (const l of plan.labels || []) if (l.matched) { const k = `${l.height}|${l.width}`; labelSizes.set(k, (labelSizes.get(k) || 0) + 1); }
      const nLabeled = [...labelSizes.values()].reduce((a, b) => a + b, 0);
      const sameSizes = bomSizes.size === labelSizes.size && [...bomSizes].every(([k, v]) => labelSizes.get(k) === v);
      if (labeled && bomSizes.size && labelSizes.size && nLabeled === plan.panels && !sameSizes) {
        const fmt = (z) => [...z].map(([k, v]) => [...k.split("|").map(Number), v]).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([h, w, v]) => `${fmtQty(v)} x ${h}"H ${w}"W`).join(", ");
        warnings.push(`Panel sizes differ: the plan labels show ${fmt(labelSizes)}; the BOM has ${fmt(bomSizes)}.`);
      }
      const pw = plan.widths;
      const same = bomWidths.size === Object.keys(pw).length && [...bomWidths].every(([k, v]) => pw[k] === v);
      if (bomWidths.size && Object.keys(pw).length && !same) {
        const fmt = (entries) => entries.sort((a, b) => a[0] - b[0]).map(([k, v]) => `${fmtQty(v)} x ${k}"`).join(", ");
        warnings.push(`Panel widths differ: the plan has ${fmt(Object.entries(pw).map(([k, v]) => [+k, v]))}; the BOM has ${fmt([...bomWidths])}.`);
      }
      return [parts, warnings];
    }

    function map(lines, planResult = null, marksSummary = null) {
      const heights = new Map(); // insertion order, so ties go to the first height seen (as in Python)
      for (const ln of lines) {
        const pn = ln.part.toUpperCase();
        const m = pn.match(PANEL);
        if (m && !pn.startsWith("P-DLPF") && !pn.startsWith("P-DLSEOR")) {
          const h = devonHeight(+m[2], divi50)[0];
          heights.set(h, (heights.get(h) || 0) + ln.qty);
        }
      }
      runHeight = null;
      let bestCount = -1;
      for (const [h, c] of heights) if (c > bestCount) { runHeight = h; bestCount = c; }
      plan = planResult && planResult.panels ? planResult : null;
      widthHeights = new Map();
      for (const ln of lines) {
        const pn = ln.part.toUpperCase(), m = pn.match(PANEL);
        if (m && !pn.startsWith("P-DLPF") && !pn.startsWith("P-DLSEOR")) { if (!widthHeights.has(+m[3])) widthHeights.set(+m[3], new Set()); widthHeights.get(+m[3]).add(+m[2]); }
      }
      heightPoints = [];
      marks = marksSummary && (marksSummary.pink || Object.keys(marksSummary.dots || {}).length) ? marksSummary : null;

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
      if (plan || marks) {
        const [parts, planWarnings] = plan ? planConnectors(lines, [...heights.keys()]) : imageConnectors(lines, [...heights.keys()]);
        planParts = parts;
        warnings.push(...planWarnings);
        const label = plan ? "2D plan" : "2D marks";
        for (const [, part, qty] of parts) {
          if (!(part in raw)) { raw[part] = 0; firstSeen.push(part); }
          raw[part] += qty;
          (sources[part] ||= []);
          if (!sources[part].includes(label)) sources[part].push(label);
        }
      } else if (heights.size) {
        warnings.push("The AIS SIF doesn't list straight panel-to-panel joints, and Devon quotes a panel-to-panel connector (HMP213) at each one. Add the 2D (a CET PDF) so they're counted; none are quoted now.");
      }
      if (marksSummary && marksSummary.offPanel) {
        const one = marksSummary.offPanel === 1;
        warnings.push(`${marksSummary.offPanel} colored mark${one ? "" : "s"} on the 2D ${one ? "is" : "are"}n't on the drawing's panel lines, so ${one ? "it was" : "they were"} not quoted.`);
      }
      const quantities = {};
      for (const p of firstSeen) if (raw[p] > 0) quantities[p] = Math.ceil(raw[p] - 1e-9);

      const autoAdded = autoAdd(quantities);
      return {
        mappings, quantities, sources, autoAdded, warnings, plan, planParts, marks, heightPoints, divi50,
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
  const MAX_THICKNESS = 20.0; // thickest drawn panel accepted, in PDF points (CET's scale varies with the sheet)
  const PANEL_LABEL = /^[A-Z](\d{2})(\d{2})$/; // CET panel tag: letter, height, width
  const LABEL_REACH = 12.0; // a panel label sits within this many panel thicknesses of its panel
  // Dot color -> Devon high/low filler strip
  const DOT_COLORS = { red: "HMHL3953", blue: "HMHL3967", yellow: "HMHL4753", green: "HMHL4767", purple: "HMHL5367" };

  function dotColor(f) {
    if (!f) return null;
    const [r, g, b] = f;
    if (r > 0.6 && g < 0.4 && b < 0.4) return "red";
    if (r > 0.6 && g > 0.6 && b < 0.4) return "yellow";
    if (g > 0.45 && r < 0.4 && b < 0.4) return "green";
    if (b > 0.5 && r < 0.4 && g < 0.5) return "blue";
    if (r >= 0.4 && r <= 0.8 && g < 0.3 && b > 0.45) return "purple";
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
      if (t >= 0.05 && t <= MAX_THICKNESS && len >= 3 * t && neutralGray(r.fill)) {
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
      out.push({ kind, x, y, page, panels: g.map((e) => e[4]).sort((a, b) => a - b) });
    }
    return out;
  }

  const rectDistance = (x, y, r) => Math.hypot(Math.max(r.x0 - x, 0, x - r.x1), Math.max(r.y0 - y, 0, y - r.y1));

  /** CET panel labels on the page, and the labeled Divi height of each panel they name (Map panel index -> height).
   *  A label goes to the nearest panel of the width it names; closest pairs are matched first, one label per panel. */
  function panelLabels(words, panels, t, page) {
    const found = [];
    for (const w of words) { const m = w.text.match(PANEL_LABEL); if (m) found.push([w, +m[1], +m[2]]); }
    const widths = panels.map((r) => nominalWidth(Math.max(r.x1 - r.x0, r.y1 - r.y0), t));
    const pairs = [];
    found.forEach(([w, , width], li) => panels.forEach((r, pi) => { if (widths[pi] === width) pairs.push([rectDistance(w.x, w.y, r), li, pi]); }));
    pairs.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
    const heights = new Map(), used = new Set();
    for (const [d, li, pi] of pairs) {
      if (d > LABEL_REACH * t || used.has(li) || heights.has(pi)) continue;
      used.add(li); heights.set(pi, found[li][1]);
    }
    const labels = found.map(([w, h, width], li) => ({ text: w.text, height: h, width, page, x: w.x, y: w.y, matched: used.has(li) }));
    return [labels, heights];
  }

  const isPink = (c) => !!c && c[0] > 0.8 && c[2] > 0.45 && c[1] < 0.8 && c[0] - c[1] > 0.2;

  /** Pink dashes the designer drew on panel-to-panel joints. Several strokes on one joint count once. */
  function pinkDashes(shapes, strokes, joints, t, page) {
    const cands = [...shapes.map((s) => [s.x0, s.y0, s.x1, s.y1, s.fill, false]), ...strokes.map((s) => [s.x0, s.y0, s.x1, s.y1, s.color, s.line])];
    const out = [], marked = new Set();
    for (const [x0, y0, x1, y1, color, line] of cands) {
      if (!isPink(color)) continue;
      const w = x1 - x0, h = y1 - y0;
      const length = line ? Math.hypot(w, h) : Math.max(w, h);
      if (!line && length < 2.5 * Math.min(w, h)) continue; // a dot or a blob, not a dash
      if (length < 0.5 * t || length > MARK_MAX_FACTOR * t) continue;
      const x = (x0 + x1) / 2, y = (y0 + y1) / 2;
      let best = null, bd = null;
      joints.forEach((j, i) => { const d = Math.hypot(j.x - x, j.y - y); if (bd === null || d < bd) { best = i; bd = d; } });
      if (best !== null && bd <= MARK_JOINT_FACTOR * t) {
        if (!marked.has(best)) { marked.add(best); out.push({ x, y, page, joint: joints[best].kind, panels: joints[best].panels }); }
      } else if (!out.some((m) => m.joint === null && Math.hypot(m.x - x, m.y - y) <= JOIN_FACTOR * t)) {
        out.push({ x, y, page, joint: null });
      }
    }
    return out;
  }

  /** pages: [[{x0, y0, x1, y1, fill: [r, g, b] | null}]] (0-1 colors); shapes: filled paths per page, same form;
   *  strokes: pink stroked paths per page ({x0, y0, x1, y1, color, line}) */
  function analyzeRects(pages, shapes = null, strokes = null, words = null) {
    const res = { counts: Object.fromEntries(PLAN_KINDS.map((k) => [k, 0])), widths: {}, joints: [], pages: [], panels: 0, heightChanges: [], pinkDashes: [], labels: [] };
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
      const [labels, heights] = panelLabels(words ? words[p] || [] : [], panels, t, p + 1);
      res.labels.push(...labels);
      const sizes = panels.map((r, i) => [nominalWidth(Math.max(r.x1 - r.x0, r.y1 - r.y0), t), heights.has(i) ? heights.get(i) : null]);
      for (const j of js) j.panels = j.panels.map((i) => sizes[i]);
      res.joints.push(...js);
      js.forEach((j) => res.counts[j.kind]++);
      if (shapes) res.heightChanges.push(...heightMarks(shapes[p], js, t, p + 1));
      if (shapes || strokes) res.pinkDashes.push(...pinkDashes(shapes ? shapes[p] : [], strokes ? strokes[p] : [], js, t, p + 1));
    });
    return res;
  }

  /** Axis-aligned filled/stroked rectangles on every page, read with PDF.js (v3 operator lists). */
  async function pdfRects(pdfjsLib, bytes, { maxPages = 20 } = {}) {
    const OPS = pdfjsLib.OPS;
    const doc = await pdfjsLib.getDocument({ data: bytes, disableFontFace: true, isEvalSupported: false }).promise;
    const pages = [], extras = [], strokeLists = [], wordLists = [];
    const views = [];
    for (let n = 1; n <= Math.min(doc.numPages, maxPages); n++) {
      const page = await doc.getPage(n);
      const ops = await page.getOperatorList();
      const rects = [], shapes = [], strokes = [];
      let ctm = [1, 0, 0, 1, 0, 0], fill = [0, 0, 0], stroke = [0, 0, 0];
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
        if (fn === OPS.save) stack.push([ctm, fill, stroke]);
        else if (fn === OPS.restore) { const s = stack.pop(); if (s) [ctm, fill, stroke] = s; }
        else if (fn === OPS.transform) ctm = mul(args, ctm);
        else if (fn === OPS.paintFormXObjectBegin) { stack.push([ctm, fill, stroke]); if (args && args[0]) ctm = mul(args[0], ctm); }
        else if (fn === OPS.paintFormXObjectEnd) { const s = stack.pop(); if (s) [ctm, fill, stroke] = s; }
        else if (fn === OPS.setFillRGBColor) fill = [args[0] / 255, args[1] / 255, args[2] / 255];
        else if (fn === OPS.setStrokeRGBColor) stroke = [args[0] / 255, args[1] / 255, args[2] / 255];
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
          const stroked = [OPS.stroke, OPS.closeStroke, OPS.fillStroke, OPS.eoFillStroke, OPS.closeFillStroke, OPS.closeEOFillStroke].includes(fn);
          if (fn !== OPS.endPath) {
            for (const pts of pending) {
              const r = pts.curved ? null : toRect(pts);
              if (r) rects.push({ ...r, fill: filled ? fill.slice() : null });
              if (!pts.length) continue;
              const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
              const box = { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
              if (filled) shapes.push({ ...box, fill: fill.slice() });
              if (stroked && isPink(stroke)) strokes.push({ ...box, color: stroke.slice(), line: pts.length === 2 && !pts.curved });
            }
          }
          pending = [];
        }
      }
      // words, for CET's panel labels: the center of each whitespace-separated token in each text item
      const words = [];
      for (const it of (await page.getTextContent()).items) {
        const str = it.str || "", tr = it.transform;
        if (!str.trim()) continue;
        const [a, b, c, d, e, f] = tr, al = Math.hypot(a, b) || 1, cl = Math.hypot(c, d) || 1;
        const per = it.width / str.length;
        for (const m of str.matchAll(/\S+/g)) {
          const along = (m.index + m[0].length / 2) * per, up = 0.3 * cl;
          words.push({ text: m[0], x: e + (a / al) * along + (c / cl) * up, y: f + (b / al) * along + (d / cl) * up, vertical: Math.abs(b) > Math.abs(a) });
        }
      }
      wordLists.push(words);
      pages.push(rects);
      extras.push(shapes);
      strokeLists.push(strokes);
      views.push(page);
    }
    return { pages, extras, strokes: strokeLists, words: wordLists, pdfPages: views };
  }

  async function analyzePdf(pdfjsLib, bytes) {
    const { pages, extras, strokes, words, pdfPages } = await pdfRects(pdfjsLib, bytes);
    return { result: analyzeRects(pages, extras, strokes, words), pdfPages };
  }

  // ---------------------------------------------------------------- marks in 2D images (port of marks.py)
  // Designers mark the 2D: a pink dash on each panel-to-panel joint, and a colored dot where the panel
  // height changes (the color picks the filler strip). In an image (PNG/JPG, or a PDF without vector
  // panels) the marks are found by color and shape.
  const MARK_CLASSES = [null, "pink", "red", "blue", "yellow", "green", "purple"];

  function pixelClass(r, g, b) {
    if (r > 204 && b > 115 && g < 204 && r - g > 51) return 1; // pink
    if (r > 153 && g < 102 && b < 102) return 2; // red
    if (b > 128 && r < 102 && g < 128) return 3; // blue
    if (r > 153 && g > 153 && b < 102) return 4; // yellow
    if (g > 115 && r < 102 && b < 102) return 5; // green
    if (r > 101 && r < 205 && g < 80 && b > 115) return 6; // purple
    return 0;
  }

  /** data: RGBA bytes (row-major), width, height. Returns {dashes, dots, size: {w, h}, limits}. */
  function imageMarks(data, W, H) {
    const L = Math.max(W, H);
    const dMin = Math.max(6, Math.round(0.004 * L)), dMax = Math.max(dMin + 1, Math.round(0.04 * L));
    const lenMin = dMin, lenMax = Math.max(lenMin + 1, Math.round(0.08 * L));
    const N = W * H;
    const cls = new Uint8Array(N), dark = new Uint8Array(N);
    for (let i = 0; i < N; i++) {
      const a = data[4 * i + 3], w = 255 * (255 - a);
      const r = Math.floor((data[4 * i] * a + w) / 255), g = Math.floor((data[4 * i + 1] * a + w) / 255), b = Math.floor((data[4 * i + 2] * a + w) / 255);
      cls[i] = pixelClass(r, g, b);
      // drawing ink: black lines and gray panel fills (neutral, not white)
      dark[i] = Math.max(r, g, b) < 235 && Math.max(r, g, b) - Math.min(r, g, b) < 30 ? 1 : 0;
    }
    // integral image of ink pixels, for the "is it on a panel" check
    const S = new Float64Array((W + 1) * (H + 1));
    for (let y = 0; y < H; y++) {
      let row = 0;
      for (let x = 0; x < W; x++) { row += dark[y * W + x]; S[(y + 1) * (W + 1) + x + 1] = S[y * (W + 1) + x + 1] + row; }
    }
    const darkIn = (x0, y0, x1, y1) => {
      x0 = Math.max(0, x0); y0 = Math.max(0, y0); x1 = Math.min(W - 1, x1); y1 = Math.min(H - 1, y1);
      if (x1 < x0 || y1 < y0) return [0, 0];
      const A = (x, y) => S[y * (W + 1) + x];
      return [A(x1 + 1, y1 + 1) - A(x0, y1 + 1) - A(x1 + 1, y0) + A(x0, y0), (x1 - x0 + 1) * (y1 - y0 + 1)];
    };
    const seen = new Uint8Array(N);
    const stack = new Int32Array(N);
    const comps = [];
    for (let i0 = 0; i0 < N; i0++) {
      const c = cls[i0];
      if (!c || seen[i0]) continue;
      let top = 0; stack[top++] = i0; seen[i0] = 1;
      let n = 0, minx = W, maxx = -1, miny = H, maxy = -1, sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0, darkOwn = 0, redNext = 0;
      while (top) {
        const i = stack[--top];
        const x = i % W, y = (i - x) / W;
        n++; sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y; darkOwn += dark[i];
        if (x < minx) minx = x; if (x > maxx) maxx = x; if (y < miny) miny = y; if (y > maxy) maxy = y;
        for (let dy = -1; dy <= 1; dy++) {
          const yy = y + dy;
          if (yy < 0 || yy >= H) continue;
          for (let dx = -1; dx <= 1; dx++) {
            const xx = x + dx;
            if (xx < 0 || xx >= W || (!dx && !dy)) continue;
            const j = yy * W + xx;
            if (!seen[j] && cls[j] === c) { seen[j] = 1; stack[top++] = j; }
            else if (c === 1 && cls[j] === 2) redNext++;
          }
        }
      }
      const bw = maxx - minx + 1, bh = maxy - miny + 1;
      if (Math.max(bw, bh) < Math.min(dMin, lenMin) || Math.max(bw, bh) > Math.max(dMax, lenMax) * 1.5) continue;
      const mx = sx / n, my = sy / n;
      const cxx = sxx / n - mx * mx + 1 / 12, cyy = syy / n - my * my + 1 / 12, cxy = sxy / n - mx * my;
      const tr = cxx + cyy, det = cxx * cyy - cxy * cxy, disc = Math.sqrt(Math.max(0, (tr * tr) / 4 - det));
      const l1 = tr / 2 + disc, l2 = Math.max(tr / 2 - disc, 1e-9);
      if (c === 1 && redNext > 0.2 * n) continue; // the blurred pinkish edge of something red, not a pink mark
      comps.push({ c, n, bw, bh, mx, my, elong: Math.sqrt(l1 / l2), length: Math.sqrt(12 * l1), fill: n / (bw * bh), darkOwn });
    }
    const dashes = [], dots = [];
    for (const k of comps) {
      if (k.c === 1) {
        if (k.elong >= 1.8 && k.length >= lenMin && k.length <= lenMax) dashes.push({ kind: "dash", color: "pink", x: k.mx, y: k.my, size: k.length, darkOwn: k.darkOwn, n: k.n });
      } else {
        const size = Math.max(k.bw, k.bh);
        const round = k.elong <= 1.6 && k.fill >= 0.6;
        if (round && size >= dMin && size <= dMax) dots.push({ kind: "dot", color: MARK_CLASSES[k.c], x: k.mx, y: k.my, size, darkOwn: k.darkOwn, n: k.n });
      }
    }
    // Dotted lines (dimension leaders) are chains of look-alike dots: group dots of one color and
    // similar size that sit within three sizes of each other; a group of three or more is a line.
    const parent = dots.map((_, i) => i);
    const find = (i) => { while (parent[i] !== i) { parent[i] = parent[parent[i]]; i = parent[i]; } return i; };
    dots.forEach((a, i) => {
      for (let j = i + 1; j < dots.length; j++) {
        const b = dots[j];
        if (b.color !== a.color) continue;
        const ratio = b.size / a.size;
        if (ratio < 0.7 || ratio > 1.43) continue;
        if (Math.hypot(b.x - a.x, b.y - a.y) <= 3 * Math.max(a.size, b.size)) parent[find(i)] = find(j);
      }
    });
    const groupSize = new Map();
    dots.forEach((_, i) => groupSize.set(find(i), (groupSize.get(find(i)) || 0) + 1));
    const chained = new Set(dots.map((_, i) => i).filter((i) => groupSize.get(find(i)) >= 3));
    // A spot inside a bigger patch of the same color (e.g. the hole of a letter in a yellow callout box)
    // is part of that patch, not a mark.
    const embedded = (m, c) => {
      const R = Math.round(1.5 * m.size), cx = Math.round(m.x), cy = Math.round(m.y);
      let same = 0, area = 0;
      for (let y = Math.max(0, cy - R); y <= Math.min(H - 1, cy + R); y++) {
        for (let x = Math.max(0, cx - R); x <= Math.min(W - 1, cx + R); x++) { area++; if (cls[y * W + x] === c) same++; }
      }
      return (same - m.n) / Math.max(1, area - m.n) >= 0.15;
    };
    const classOf = (color) => MARK_CLASSES.indexOf(color);
    const kept = dots.filter((m, i) => !chained.has(i) && !embedded(m, classOf(m.color)));
    const keptDashes = dashes.filter((m) => !embedded(m, 1));
    // A mark sits on the drawing: there must be panel lines (ink) right around it.
    const out = (m) => {
      const R = Math.round(1.5 * m.size);
      const [d, area] = darkIn(Math.round(m.x) - R, Math.round(m.y) - R, Math.round(m.x) + R, Math.round(m.y) + R);
      const onPanel = (d - m.darkOwn) / area >= 0.05;
      return { kind: m.kind, color: m.color, x: Math.round(m.x * 10) / 10, y: Math.round(m.y * 10) / 10, size: Math.round(m.size * 10) / 10, onPanel };
    };
    return { dashes: keptDashes.map(out), dots: kept.map(out), size: { w: W, h: H }, limits: { dMin, dMax, lenMin, lenMax } };
  }

  /** Sum the marks of several images/pages: {pink, dots: {color: n}, offPanel: n, marks: [...]} */
  function summarizeMarks(list) {
    const res = { pink: 0, dots: {}, offPanel: 0, sources: list.length };
    const use = (d) => (d.use === undefined ? d.onPanel : d.use);
    for (const m of list) {
      for (const d of m.dashes) { if (use(d)) res.pink++; else if (!d.onPanel) res.offPanel++; }
      for (const d of m.dots) { if (use(d)) res.dots[d.color] = (res.dots[d.color] || 0) + 1; else if (!d.onPanel) res.offPanel++; }
    }
    return res;
  }

  // ---------------------------------------------------------------- pricing
  // Delivery estimate from the order weight, fitted to 25 Devon quotes to OF4S (33010), Aug 2024 - Oct 2026:
  // freight ~ $445 + $0.27/lb (R^2 0.96, typical miss about $110). Devon confirms the real figure.
  const DELIVERY_BASE = 445, DELIVERY_PER_LB = 0.27;
  const estimateDelivery = (weight) => (weight > 0 ? Math.floor((DELIVERY_BASE + DELIVERY_PER_LB * weight) / 5 + 0.5) * 5 : 0);

  /** delivery null/undefined: estimated from the order weight. */
  function estimate(catalog, quantities, grade, delivery, stations) {
    const lines = Object.entries(quantities).map(([part, qty]) => {
      const item = catalog.items[part];
      const lp = listPrice(item, grade);
      return { part, description: item.description, qty, listEach: lp, netEach: lp * catalog.netMultiplier, weight: item.weight * qty, row: item.row };
    }).sort((a, b) => a.row - b.row);
    lines.forEach((l) => { l.netExt = l.netEach * l.qty; l.listExt = l.listEach * l.qty; });
    const product = lines.reduce((s, l) => s + l.netExt, 0);
    const surcharge = product * catalog.surchargeRate;
    const weight = lines.reduce((s, l) => s + l.weight, 0);
    const deliveryAuto = delivery === null || delivery === undefined;
    if (deliveryAuto) delivery = estimateDelivery(weight);
    const total = product + surcharge + delivery;
    return {
      lines, listTotal: lines.reduce((s, l) => s + l.listExt, 0), product, surcharge, delivery, deliveryAuto, total,
      weight, stations: stations || null,
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
    if (lines.some((l) => /^P-DL(?!PF|SEOR)[A-Z]+50\d{2}$/.test(l.part.toUpperCase()))) w(`- AIS 50"H panels quoted as Devon ${result.divi50 || 53}"H`);
    w("");
    w("## Estimated Devon cost\n");
    w("| | |\n|---|---:|");
    w(`| List | ${money(est.listTotal)} |`);
    w(`| Product net | ${money(est.product)} |`);
    w(`| Surcharge (${Math.round(catalog.surchargeRate * 100)}%) | ${money(est.surcharge)} |`);
    w(est.deliveryAuto ? `| Delivery (estimated from ${Math.round(est.weight).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")} lbs: $445 + $0.27/lb; Devon confirms) | ${money(est.delivery)} |` : `| Delivery (estimate) | ${money(est.delivery)} |`);
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
      if ((result.plan.pinkDashes || []).length) w("Panel-to-panel connectors are counted from the pink dashes drawn on the plan, one per marked joint.\n");
      const tags = new Map();
      for (const l of result.plan.labels || []) if (l.matched) tags.set(l.text, (tags.get(l.text) || 0) + 1);
      if (tags.size) {
        const total = [...tags.values()].reduce((a, b) => a + b, 0);
        const list = [...tags].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([t, n]) => `${t} x ${n}`).join(", ");
        w(`Panel heights come from the CET panel labels (${total} of ${result.plan.panels} panels labeled: ${list}). Each connector is quoted at the tallest panel at its joint; where heights change, a high/low filler strip covers the step.\n`);
      }
      w("| Joint on the plan | Qty | Devon part |\n|---|---:|---|");
      const labels = { straight: "Two panels in a straight line (180°)", pink: "Panel-to-panel joint (pink dash on the plan)", l: "Corner, two panels at 90°", tee: "Three panels", cross: "Four panels", ends: "Free end of a run",
        filler: (result.heightPoints || []).length ? "Height change (panel labels): high/low filler strip" : "Height change (colored dot): high/low filler strip" };
      for (const [k, p, q] of result.planParts) w(`| ${labels[k]} | ${q} | ${p} |`);
      w("");
      w("Free ends are quoted as finished ends. Swap any that stop at a wall to a wall start (HMA199).\n");
    }
    if (result.marks) {
      const mk = result.marks;
      const dots = Object.entries(mk.dots || {}).map(([color, n]) => `${n} ${color}`).join(", ") || "none";
      w("## Marks read from the 2D\n");
      w(`Pink dashes (panel-to-panel): ${mk.pink} · colored dots (filler strips): ${dots}\n`);
      if (!result.plan) {
        w("The AIS SIF doesn't list straight joints, so each pink dash adds a panel-to-panel connector. AIS 2-way posts are quoted as corners.\n");
        w("| From the 2D | Qty | Devon part |\n|---|---:|---|");
        const labels = { pink: "Pink dash: panel-to-panel connector", filler: "Colored dot: high/low filler strip" };
        for (const [k, p, q] of result.planParts) w(`| ${labels[k]} | ${q} | ${p} |`);
        w("");
      }
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
    makeMapper, devonHeight, estimateDelivery, connector, DOT_COLORS, estimate, setCell, fillSheet, writeQuote,
    finishes, crosswalkCsv, reportMd, safeStem, analyzeRects, pdfRects, analyzePdf, nominalWidth, imageMarks, summarizeMarks,
  };
});
