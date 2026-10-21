// Runs the hosted page's JS engine under Node for tests/test_engine_parity.py.
// usage: node engine_harness.js <calculator.xlsm> <bom> <out.xlsx|.xlsm> <options-json>
console.log = console.warn = (...a) => console.error(...a); // keep stdout for the JSON result
const fs = require("fs");
const path = require("path");
const JSZip = require("jszip");
const E = require(path.join(__dirname, "..", "devon_quote", "web", "engine.js"));

(async () => {
  const [calcPath, bomPath, outPath, optsJson] = process.argv.slice(2);
  const opts = JSON.parse(optsJson || "{}");
  const { catalog } = await E.loadCalculator(JSZip, fs.readFileSync(calcPath));
  const lines = await E.parseBom(JSZip, path.basename(bomPath), fs.readFileSync(bomPath));
  let plan = null;
  if (opts.plan) {
    const pdfjs = require("pdfjs-dist/legacy/build/pdf.js");
    plan = (await E.analyzePdf(pdfjs, new Uint8Array(fs.readFileSync(opts.plan)))).result;
  }
  const result = E.makeMapper(catalog, opts.overrides || []).map(lines, plan);
  const grade = opts.grade || 0;
  const est = E.estimate(catalog, result.quantities, grade, opts.delivery || 0, opts.stations || null);
  const header = { project: opts.project || "", description: "WORKSTATIONS", date: "1.2.26", shipTo: "33010", grade, delivery: opts.delivery || 0, stations: opts.stations || null };
  const bytes = await E.writeQuote(JSZip, fs.readFileSync(calcPath), catalog, result.quantities, header, outPath.endsWith(".xlsx") ? "xlsx" : "xlsm");
  fs.writeFileSync(outPath, bytes);
  const catalogDump = {};
  for (const p of catalog.order) {
    const it = catalog.items[p];
    catalogDump[p] = [it.row, ...[0, 1, 2].map((g) => E.listPrice(it, g)), it.weight];
  }
  process.stdout.write(JSON.stringify({
    catalog: catalogDump,
    netMultiplier: catalog.netMultiplier,
    surchargeRate: catalog.surchargeRate,
    quantities: result.quantities,
    mappings: result.mappings.map((m) => [m.source.part, m.status, m.note, m.targets]),
    warnings: result.warnings,
    plan: plan && { counts: plan.counts, widths: plan.widths, panels: plan.panels },
    total: est.total,
    product: est.product,
    crosswalk: E.crosswalkCsv(result),
    report: E.reportMd({ project: opts.project || "", bomFile: path.basename(bomPath), quoteFile: path.basename(outPath), catalog, grade, lines, result, est, notes: opts.notes || "", drawings: [] }),
  }));
})().catch((e) => { console.error(e); process.exit(1); });
