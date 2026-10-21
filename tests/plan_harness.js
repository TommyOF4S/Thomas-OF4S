// Prints the JS plan reader's result for a PDF: node plan_harness.js plan.pdf
console.log = console.warn = (...a) => console.error(...a); // keep stdout for the JSON result
const fs = require("fs");
const path = require("path");
const pdfjs = require("pdfjs-dist/legacy/build/pdf.js");
const E = require(path.join(__dirname, "..", "devon_quote", "web", "engine.js"));
E.analyzePdf(pdfjs, new Uint8Array(fs.readFileSync(process.argv[2])))
  .then(({ result }) => process.stdout.write(JSON.stringify({ counts: result.counts, widths: result.widths, panels: result.panels, pages: result.pages, heightChanges: result.heightChanges, pinkDashes: result.pinkDashes })))
  .catch((e) => { console.error(e); process.exit(1); });
