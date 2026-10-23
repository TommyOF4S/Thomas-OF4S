// Teilen wall pricing. Source of truth: the Teilen Quote Builder page.

(function (root) {
  // Teilen "System Walls Pricing" sheet, 1/8/2026. Base prices before the increase.
  var B32 = 32 / 12, DOORH = 80 / 12;
  var PANELS = [
    { code: 'T101', cat: 'Melamine', pic: '01', base: 11.42, short: 'Full melamine', desc: '5/8" thickness full melamine panel' },
    { code: 'T102', cat: 'Melamine', pic: '02', base: 12.16, short: 'Melamine in 2 segments', desc: '5/8" thickness full melamine panel segment in two' },
    { code: 'T103', cat: 'Melamine', pic: '03', base: 12.89, short: 'Melamine in 3 segments', desc: '5/8" thickness full melamine panel segment in three' },
    { code: 'T104', cat: 'Melamine', pic: '04', base: 13.64, short: 'Melamine in 4 segments', desc: '5/8" thickness full melamine panel segment in four' },
    { code: 'T105', cat: 'Glass', pic: '05', base: 19.68, short: 'Full glass, framed', desc: '1/4" thickness full tempered glass panel (framed)' },
    { code: 'T105F', cat: 'Glass', pic: '05', base: 28.71, short: 'Full glass, frameless', desc: '3/8" thickness full tempered frameless glass panel' },
    { code: 'T106', cat: 'Glass', pic: '06', base: 20.75, short: 'Glass in 2 segments', desc: '1/4" thickness full tempered glass panel segment in two' },
    { code: 'T107', cat: 'Glass', pic: '07', base: 21.79, short: 'Glass in 3 segments', desc: '1/4" thickness full tempered glass panel segment in three' },
    { code: 'T108', cat: 'Glass', pic: '08', base: 22.89, short: 'Glass in 4 segments', desc: '1/4" thickness full tempered glass panel segment in four' },
    { code: 'T109', cat: 'Mixed', pic: '09', base: 19.93, short: 'Melamine base 32", glass above', desc: '5/8" melamine panel on bottom 32" and 1/4" tempered glass the rest' },
    { code: 'T109F', cat: 'Mixed', pic: '09', base: 23.13, short: 'Melamine base 32", frameless glass above', desc: '5/8" melamine panel on bottom 32" and 3/8" tempered frameless glass the rest' },
    { code: 'T110', cat: 'Mixed', pic: '10', base: 19.08, short: 'Glass to door height, melamine top', desc: '1/4" tempered glass panel till the door height and 5/8" melamine panel on top' },
    { code: 'T110F', cat: 'Mixed', pic: '10', base: 24.87, short: 'Frameless glass to door height, melamine top', desc: '3/8" tempered frameless glass panel till the door height and 5/8" melamine panel on top' },
    { code: 'T111', cat: 'Mixed', pic: '11', base: 15.47, short: "Melamine to 8', glass on top", desc: '5/8" melamine panel till 8\'H and 1/4" tempered glass on top' },
    { code: 'T112', cat: 'Mixed', pic: '12', base: 16.13, short: 'Melamine base, glass band, melamine top', desc: '5/8" melamine on bottom 32" and 1/4" glass till door height, rest melamine' },
    { code: 'T112F', cat: 'Mixed', pic: '12', base: 24.49, short: 'Melamine base, frameless glass band, melamine top', desc: '5/8" melamine on bottom 32" and 3/8" frameless glass till door height, rest melamine' },
    { code: 'T113', cat: 'Mixed', pic: '13*', base: 17.89, approx: true, short: 'Melamine base, glass in 2 segments', desc: '5/8" melamine on bottom 32" and 1/4" glass the rest, segment in two' },
    { code: 'T114', cat: 'Mixed', pic: '14*', base: 18.43, approx: true, short: 'Melamine base, glass in 3 segments', desc: '5/8" melamine on bottom 32" and 1/4" glass the rest, segment in three' },
    { code: 'T115', cat: 'Mixed', pic: '15*', base: 15.48, approx: true, short: 'Melamine in 2 segments, glass above', desc: '5/8" melamine panel segment in two and 1/4" glass the rest' },
    { code: 'T116', cat: 'Mixed', pic: '16*', base: 23.09, approx: true, short: 'Melamine in 3 segments, glass above', desc: '5/8" melamine panel segment in three and 1/4" glass the rest' },
    { code: 'T117', cat: 'Mixed', pic: '', base: 19.85, approx: true, noPic: true, short: 'Melamine in 4 segments, glass above', desc: '5/8" melamine panel segment in four and 1/4" glass the rest' },
    { code: 'T118', cat: 'Mixed', pic: '', base: 16.37, approx: true, noPic: true, short: 'Melamine in 5 segments, glass above', desc: '5/8" melamine panel segment in five and 1/4" glass the rest' }
  ];
  // h: fixed door height in ft. maxH / minH: the "up to" and "from" heights on the sheet.
  var DOORS = [
    { code: 'HW1', cat: 'Door', group: 'Hinged', base: 680, h: DOORH, kind: 'hinged', mat: 'wood', short: 'Hollow wood hinged, 80"H, lock', desc: '36"W x 80"H hollow wood hinged door with key lever lock' },
    { code: 'A1', cat: 'Door', group: 'Hinged', base: 675, h: DOORH, kind: 'hinged', mat: 'alu', short: 'Aluminum/glass hinged, 80"H, lock', desc: '36"W x 80"H aluminum/glass hinged door with key lever lock' },
    { code: 'A1C', cat: 'Door', group: 'Hinged', base: 825, maxH: 8, kind: 'hinged', mat: 'alu', short: 'Aluminum/glass hinged, up to 96"H, lock', desc: '36"W up to 96"H aluminum/glass hinged door with key lever lock' },
    { code: 'FL1', cat: 'Door', group: 'Hinged', base: 935, h: DOORH, kind: 'hinged', mat: 'glass', short: 'Frameless glass hinged, 80"H', desc: '36"W x 80"H frameless glass 3/8" hinged door with handle 8" (no lock)' },
    { code: 'FLHF', cat: 'Door', group: 'Hinged', base: 1220, maxH: 10, kind: 'hinged', mat: 'glass', short: 'Frameless glass hinged, up to 120"H, lock', desc: '36"W up to 120"H frameless with 3/8" glass hinged door with key lever lock' },
    { code: 'FLP', cat: 'Door', group: 'Pivot', base: 1220, maxH: 9, kind: 'pivot', mat: 'glass', short: 'Frameless glass pivot, up to 108"H', desc: '36"W up to 108"H frameless 3/8" glass pivot door with handle 24" (no lock)' },
    { code: 'FLP.5', cat: 'Door', group: 'Pivot', base: 1350, minH: 9, maxH: 10, kind: 'pivot', mat: 'glass', short: 'Frameless 1/2" glass pivot, 108" to 120"H', desc: '36"W from 108"H to 120"H frameless 1/2" glass pivot door with handle 24" (no lock)' },
    { code: 'FLPS', cat: 'Door', group: 'Pivot', base: 1400, maxH: 10, kind: 'pivot', mat: 'alu', short: 'Slim-frame glass pivot, up to 120"H, lock', desc: '36"W up to 120"H slim frame with 3/8" glass pivot door with key lever lock' },
    { code: 'HWS1', cat: 'Door', group: 'Barn and sliding', base: 770, h: DOORH, kind: 'barn', mat: 'wood', short: 'Hollow wood barn, 80"H', desc: '36"W x 80"H hollow wood barn door with handle insert (no lock)' },
    { code: 'FLB', cat: 'Door', group: 'Barn and sliding', base: 905, h: DOORH, kind: 'barn', mat: 'glass', short: 'Frameless glass barn, 80"H', desc: '36"W x 80"H frameless 3/8" glass barn door with handle 8" (no lock)' },
    { code: 'FLS', cat: 'Door', group: 'Barn and sliding', base: 1700, maxH: 10, kind: 'sliding', mat: 'glass', short: 'Frameless glass sliding, up to 120"H', desc: '36"W up to 120"H frameless 3/8" glass sliding door with handle 24" (no lock)' },
    { code: 'FLSS', cat: 'Door', group: 'Barn and sliding', base: 1850, maxH: 10, kind: 'sliding', mat: 'alu', short: 'Slim-frame glass sliding, up to 120"H', desc: '36"W up to 120"H slim frame with 3/8" glass sliding door with handle 24" (no lock)' }
  ];
  var ALL = PANELS.concat(DOORS);
  var BY_CODE = {};
  ALL.forEach(function (p) { BY_CODE[p.code] = p; });

  function round2(n) { return Math.round((n + Number.EPSILON) * 100) / 100; }

  // Accepts 9'6", 9' 6, 9ft 6in, 9 6, 114", 114 in, 9.5
  function parseLen(raw) {
    if (raw == null) return null;
    var s = String(raw).trim().toLowerCase()
      .replace(/[’′‘`]/g, "'").replace(/[”″“]/g, '"').replace(/''/g, '"');
    if (!s) return null;
    var n = '(\\d+(?:\\.\\d+)?|\\.\\d+)', m;
    m = s.match(new RegExp('^' + n + "\\s*(?:'|ft\\.?|feet|foot)\\s*-?\\s*(?:" + n + '\\s*(?:"|in\\.?|inch|inches)?)?$'));
    if (m) return +m[1] + (m[2] ? +m[2] / 12 : 0);
    m = s.match(new RegExp('^' + n + '\\s*(?:"|in\\.?|inch|inches)$'));
    if (m) return +m[1] / 12;
    m = s.match(new RegExp('^(\\d+)\\s+' + n + '$'));
    if (m) return +m[1] + +m[2] / 12;
    m = s.match(new RegExp('^' + n + '$'));
    if (m) return +m[1];
    return null;
  }
  function fmtLen(ft) {
    if (ft == null || !isFinite(ft)) return '';
    var inches = Math.round(ft * 1200) / 100;
    var f = Math.floor(inches / 12 + 1e-9);
    var i = round2(inches - f * 12);
    if (i >= 12) { f += 1; i = 0; }
    return f + "' " + i + '"';
  }

  // Elevation bands from the floor up, in feet. Models 13 to 18 are approximate.
  function bands(code, H) {
    var fl = /F$/.test(code), c = String(code || '').replace(/F$/, ''), out = [];
    function seg(m, a, b, n) {
      n = n || 1; b = Math.min(b, H); if (b <= a) return;
      var s = (b - a) / n;
      for (var k = 0; k < n; k++) out.push({ m: m, y0: a + k * s, y1: a + (k + 1) * s, fl: m === 'glass' && fl });
    }
    switch (c) {
      case 'T102': seg('mel', 0, H, 2); break;
      case 'T103': seg('mel', 0, H, 3); break;
      case 'T104': seg('mel', 0, H, 4); break;
      case 'T105': seg('glass', 0, H, 1); break;
      case 'T106': seg('glass', 0, H, 2); break;
      case 'T107': seg('glass', 0, H, 3); break;
      case 'T108': seg('glass', 0, H, 4); break;
      case 'T109': seg('mel', 0, B32); seg('glass', B32, H); break;
      case 'T110': seg('glass', 0, DOORH); seg('mel', DOORH, H); break;
      case 'T111': seg('mel', 0, 8); seg('glass', 8, H); break;
      case 'T112': seg('mel', 0, B32); seg('glass', B32, DOORH); seg('mel', DOORH, H); break;
      case 'T113': seg('mel', 0, B32); seg('glass', B32, H, 2); break;
      case 'T114': seg('mel', 0, B32); seg('glass', B32, H, 3); break;
      case 'T115': seg('mel', 0, DOORH, 2); seg('glass', DOORH, H); break;
      case 'T116': seg('mel', 0, DOORH, 3); seg('glass', DOORH, H); break;
      case 'T117': seg('mel', 0, DOORH, 4); seg('glass', DOORH, H); break;
      case 'T118': seg('mel', 0, DOORH, 5); seg('glass', DOORH, H); break;
      default: seg('mel', 0, H, 1);
    }
    return out;
  }
  function doorHeight(d, H) { return Math.min(d.h || d.maxH || DOORH, H); }

  function makePrice(settings, frozen) {
    var inc = +(settings && settings.increase) || 0, base = (settings && settings.base) || {};
    return function (code) {
      if (frozen && frozen.prices && frozen.prices[code] != null) return +frozen.prices[code];
      var p = BY_CODE[code]; if (!p) return 0;
      var b = base[code] != null && base[code] !== '' && isFinite(+base[code]) ? +base[code] : p.base;
      return b * (1 + inc);
    };
  }

  function computeWall(w, ctx) {
    var h = +w.h > 0 ? +w.h : 0, l = +w.l > 0 ? +w.l : 0;
    var qty = Math.max(1, Math.round(+w.qty || 1));
    var doors = (w.doors || []).filter(function (d) { return d && BY_CODE[d.code] && (+d.qty || 0) > 0; });
    var doorsN = doors.reduce(function (a, d) { return a + Math.round(+d.qty); }, 0);
    var hasDims = h > 0 && l > 0;
    var panel = BY_CODE[w.model] && BY_CODE[w.model].cat !== 'Door' ? BY_CODE[w.model] : null;
    var sqft = hasDims ? h * l : 0;
    var billable = hasDims ? Math.max(0, sqft - ctx.ded * doorsN) : 0;
    var ppsf = panel ? ctx.price(panel.code) : 0;
    var material = billable * ppsf;
    var doorCost = doors.reduce(function (a, d) { return a + Math.round(+d.qty) * ctx.price(d.code); }, 0);
    var labor = l > 0 ? l * ctx.labor : 0;
    var unit = material + doorCost + labor;
    var warnings = [];
    if (!panel) warnings.push('Pick a panel model.');
    if (!hasDims) warnings.push('Enter the wall height and length.');
    if (hasDims && doorsN * 3 > l + 1e-9) warnings.push(doorsN + (doorsN === 1 ? ' door' : ' doors') + ' at 36" wide need at least ' + fmtLen(doorsN * 3) + ' of wall. This wall is ' + fmtLen(l) + '.');
    if (hasDims && doorsN > 0 && billable === 0) warnings.push('The door deduction uses up all ' + round2(sqft) + ' sqft, so no panel is billed.');
    var seen = {};
    doors.forEach(function (d) {
      var spec = BY_CODE[d.code]; if (seen[d.code] || !h) return; seen[d.code] = 1;
      if (spec.h && h < spec.h - 1e-9) warnings.push(d.code + ' is 80" tall. This wall is only ' + fmtLen(h) + '.');
      if (spec.minH && h < spec.minH - 1e-9) warnings.push(d.code + ' is made for openings 108" to 120" tall. For a ' + fmtLen(h) + ' wall, FLP covers up to 108".');
    });
    if (panel && h) {
      var c = panel.code.replace(/F$/, '');
      if (c === 'T111' && h <= 8) warnings.push("T111 switches to glass at 8'. At " + fmtLen(h) + ' this wall would be all melamine.');
      if ((c === 'T110' || c === 'T112') && h <= DOORH) warnings.push(panel.code + ' changes material at door height (80"). This wall is shorter than that.');
    }
    return {
      h: h, l: l, qty: qty, doors: doors, doorsN: doorsN, hasDims: hasDims, panel: panel,
      sqft: sqft, billable: billable, ppsf: ppsf, material: material, doorCost: doorCost, labor: labor, unit: unit,
      ext: { sqft: sqft * qty, lf: l * qty, doorsN: doorsN * qty, material: material * qty, doors: doorCost * qty, labor: labor * qty, total: unit * qty },
      warnings: warnings, complete: hasDims && !!panel
    };
  }

  function computeQuote(q, price) {
    var a = q.assumptions || {};
    var ctx = { price: price, ded: +a.doorDeduction || 0, labor: +a.laborRate || 0 };
    var walls = (q.walls || []).map(function (w) { return computeWall(w, ctx); });
    function sum(k) { return walls.reduce(function (s, w) { return s + w.ext[k]; }, 0); }
    var material = sum('material'), doors = sum('doors'), labor = sum('labor');
    var subtotal = material + doors + labor, shipping = +a.shipping || 0, cost = subtotal + shipping;
    var m = Math.min(Math.max(+q.margin || 0, 0), 0.95), f = 1 / (1 - m);
    var itemize = q.itemize !== false, lines = [];
    walls.forEach(function (w, i) {
      var base = itemize ? w.ext.material + w.ext.doors : w.ext.total;
      lines.push({ type: 'wall', index: i, amount: round2(base * f) });
    });
    if (itemize && labor > 0) lines.push({ type: 'install', amount: round2(labor * f) });
    if (shipping > 0) lines.push({ type: 'freight', amount: round2(shipping * f) });
    var sell = round2(lines.reduce(function (s, l) { return s + l.amount; }, 0));
    var taxRate = Math.max(0, +q.taxRate || 0), tax = round2(sell * taxRate), total = round2(sell + tax);
    var sqft = sum('sqft'), profit = sell - cost;
    return {
      walls: walls, material: material, doors: doors, labor: labor, subtotal: subtotal, shipping: shipping, cost: cost,
      margin: m, markup: f - 1, lines: lines, sell: sell, taxRate: taxRate, tax: tax, total: total, profit: profit,
      realMargin: sell > 0 ? profit / sell : 0, sqft: sqft, lf: sum('lf'), doorsN: sum('doorsN'), perSqft: sqft > 0 ? sell / sqft : 0
    };
  }

  root.TQ = { PANELS: PANELS, DOORS: DOORS, ALL: ALL, BY_CODE: BY_CODE, B32: B32, DOORH: DOORH, round2: round2, parseLen: parseLen, fmtLen: fmtLen, bands: bands, doorHeight: doorHeight, makePrice: makePrice, computeWall: computeWall, computeQuote: computeQuote };
})(typeof window !== 'undefined' ? window : globalThis);

// ---------------------------------------------------------------------------
// CLI. The pricing code above is copied verbatim from
// teilen-quote-builder/teilen-quote-builder.html (CALC-START..CALC-END).
// Keep the two in sync when Teilen issues a new price sheet.
//
// Usage: node teilen_calc.js quote.json        (or pipe JSON on stdin)
//        node teilen_calc.js --prices          (print the price list)
// quote.json shape: see references/quote-schema.md
// ---------------------------------------------------------------------------
if (typeof require !== 'undefined' && require.main === module) {
  var T = globalThis.TQ;
  var fs = require('fs');
  var args = process.argv.slice(2);
  var settings = { increase: 0.05, base: {} };
  if (args[0] === '--prices') {
    var p = T.makePrice(settings, null);
    T.ALL.forEach(function (x) { console.log([x.code, x.cat, x.short, 'base ' + x.base, 'yours ' + T.round2(p(x.code))].join(' | ')); });
    process.exit(0);
  }
  var raw = args[0] ? fs.readFileSync(args[0], 'utf8') : fs.readFileSync(0, 'utf8');
  var q = JSON.parse(raw);
  if (q.settings) settings = Object.assign(settings, q.settings);
  (q.walls || []).forEach(function (w) {
    if (w.h == null && w.hText != null) w.h = T.parseLen(w.hText);
    if (w.l == null && w.lText != null) w.l = T.parseLen(w.lText);
  });
  q.assumptions = Object.assign({ laborRate: 50, doorDeduction: 21, shipping: 600 }, q.assumptions || {});
  if (q.margin == null) q.margin = 0.30;
  var c = T.computeQuote(q, T.makePrice(settings, q.frozen));
  var r = T.round2;
  var out = {
    walls: c.walls.map(function (w, i) {
      var src = q.walls[i];
      return { name: src.name || 'Wall ' + (i + 1), model: src.model, height: T.fmtLen(w.h), length: T.fmtLen(w.l), qty: w.qty,
        sqft: r(w.sqft), billableSqft: r(w.billable), pricePerSqft: r(w.ppsf), panels: r(w.material), doors: r(w.doorCost),
        install: r(w.labor), wallCost: r(w.unit), extendedCost: r(w.ext.total), warnings: w.warnings };
    }),
    cost: { panels: r(c.material), doors: r(c.doors), install: r(c.labor), freight: r(c.shipping), total: r(c.cost) },
    sell: { margin: c.margin, markup: r(c.markup), lines: c.lines, subtotal: c.sell, tax: c.tax, total: c.total, grossProfit: r(c.profit), perSqft: r(c.perSqft) },
    totals: { sqft: r(c.sqft), linearFt: r(c.lf), doors: c.doorsN }
  };
  console.log(JSON.stringify(out, null, 2));
}
