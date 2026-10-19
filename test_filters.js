/* Self-check for the dashboard's multi-select filter logic. Run: node test_filters.js
   Loads the real inline script from the built site and exercises computeFilterKeys /
   matches, so it fails if the enumerated-option detection or the multi-value
   predicate regresses. No dependencies: a Proxy stands in for the DOM. */
const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync("outputs/site/index.html", "utf8");
const js = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join("\n");
if (!js.trim()) throw new Error("no inline script in outputs/site/index.html");

const P = new Proxy(function () {}, {
  get: (t, p) => (p === Symbol.toPrimitive ? () => "" : p === "then" ? undefined : P),
  set: () => true, apply: () => P, construct: () => P,
});
globalThis.document = P; globalThis.window = globalThis;
globalThis.localStorage = P; globalThis.navigator = P;
globalThis.fetch = () => new Promise(() => {});
try { vm.runInThisContext(js); } catch (e) { if (e instanceof SyntaxError) throw e; /* init touches DOM only; functions are defined above it */ }

COLUMNS = [{ key: "name", label: "Survei" }, { key: "data9", label: "Hasil Pendataan" }];
DATA = [
  { name: "A", data9: "1. Berhasil diwawancarai" },
  { name: "A", data9: "5. Bukan usaha pertanian" },
  { name: "A", data9: "6. Pindah keluar SLS" },
  { name: "B", data9: "1. Berhasil diwawancarai" },
];

const fk = computeFilterKeys();
if (!fk.keys.includes("data9")) throw new Error("enumerated column dropped from filters");
if (!fk.multi.includes("data9")) throw new Error("enumerated column not marked multi-select");

FILTER_KEYS = fk.keys;
state.filters = { data9: ["5. Bukan usaha pertanian", "6. Pindah keluar SLS"] };
if (!matches({ data9: "5. Bukan usaha pertanian" }, null)) throw new Error("selected value rejected");
if (!matches({ data9: "6. Pindah keluar SLS" }, null)) throw new Error("second selected value rejected");
if (matches({ data9: "1. Berhasil diwawancarai" }, null)) throw new Error("unselected value leaked through");

state.filters = { data9: [] };
if (!matches({ data9: "1. Berhasil diwawancarai" }, null)) throw new Error("empty filter must pass all");

console.log("test_filters OK");
process.exit(0);
