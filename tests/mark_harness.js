// Height-mark edge cases for tests/test_plan.py: reads JSON {calc, pages, extras, strokes, words, lines} on stdin,
// prints the JS engine's quantities and warnings.
console.log = console.warn = (...a) => console.error(...a);
const fs = require("fs");
const path = require("path");
const JSZip = require("jszip");
const E = require(path.join(__dirname, "..", "devon_quote", "web", "engine.js"));
(async () => {
  const input = JSON.parse(fs.readFileSync(0, "utf8"));
  const { catalog } = await E.loadCalculator(JSZip, fs.readFileSync(input.calc));
  const plan = E.analyzeRects(input.pages, input.extras, input.strokes || null, input.words || null);
  const result = E.makeMapper(catalog, []).map(input.lines.map((l) => ({ ...l, tag: "", options: [] })), plan);
  process.stdout.write(JSON.stringify({ quantities: result.quantities, warnings: result.warnings, planParts: result.planParts }));
})().catch((e) => { console.error(e); process.exit(1); });
