// Runs imageMarks() from the hosted page's engine on raw RGBA bytes: node marks_harness.js file.rgba W H
console.log = console.warn = (...a) => console.error(...a);
const fs = require("fs");
const path = require("path");
const E = require(path.join(__dirname, "..", "devon_quote", "web", "engine.js"));
const [file, w, h] = process.argv.slice(2);
const r = E.imageMarks(new Uint8Array(fs.readFileSync(file)), +w, +h);
process.stdout.write(JSON.stringify({ marks: r, summary: E.summarizeMarks([r]) }));
