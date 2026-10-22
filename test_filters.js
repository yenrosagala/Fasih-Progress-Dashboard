/* Self-check for the dashboard's multi-select filter logic and the kabupaten
   progress-bar logic. Run: node test_filters.js
   Loads the real inline script from the built site and exercises computeFilterKeys /
   matches / renderProgress's utama+done aggregation, so it fails if the enumerated-
   option detection, the multi-value predicate, or the progress math regresses.
   No dependencies: a Proxy stands in for the DOM. */
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
if (val({ data10: "None" }, "data10") !== "" || val({ data10: "undefined" }, "data10") !== "" || val({ data10: "1. Berhasil diwawancarai" }, "data10") !== "1. Berhasil diwawancarai") throw new Error("val() must blank serializer junk and keep real values");
console.log("test_filters OK");

/* --- Progress per Kabupaten: target = sampel utama, done = hasil diwawancarai & status >= submit --- */
const els = {};
globalThis.document = { getElementById: id => els[id] || (els[id] = { innerHTML: "", style: {}, onchange: null }) };
STATUS_DEF = [
  { key: "submitted", aliases: ["SUBMIT"] },
  { key: "approved",  aliases: ["APPROVED"] },
  { key: "rejected",  aliases: ["REJECTED"] },
  { key: "draft",     aliases: ["DRAFT"] },
  { key: "open",      aliases: ["OPEN"] },
  { key: "final",     aliases: ["ADMIN"] },
];
STATUS_ORDER = ["submitted", "approved", "final", "rejected", "draft", "open", "other"];
STATUS = {}; STATUS_ORDER.forEach(k => STATUS[k] = { label: k, color: "#000" });
SUBMIT_KEYS = ["submitted", "approved", "final"];
FINAL_KEYS = ["final"];
META = { name: "T", generated: "" };
LABEL = {};
MULTI_KEYS = ["data4", "data10"];
BACKEND = false; AI_ON = false;
COLUMNS = [
  { key: "prov", label: "Prov" }, { key: "kab", label: "Kab" },
  { key: "data4", label: "Kategori Sampel" }, { key: "data10", label: "Data 10" },
];
DATA = [
  { kab: "Kab X", status: "SUBMITTED BY Pencacah", data4: "1. Utama",   data10: "1. Berhasil diwawancarai" },
  { kab: "Kab X", status: "OPEN",                  data4: "1. Utama",   data10: "1. Berhasil diwawancarai" },
  { kab: "Kab X", status: "SUBMITTED BY Pencacah", data4: "2. Cadangan", data10: "1. Berhasil diwawancarai" },
  { kab: "Kab Y", status: "APPROVED BY Pengawas",  data4: "1. Utama",   data10: "" },
  { kab: "Kab Y", status: "REJECTED BY Pengawas",  data4: "1. Utama",   data10: "1. Berhasil diwawancarai" },
];
filtered = DATA; state = { q: "", page: 0, pageSize: 100, sort: { key: null, dir: 1 }, filters: {}, graphKey: null };
renderProgress();
let pg = els.progressgrid.innerHTML;
if (!pg.includes("Kab X") || !pg.includes("1/2")) throw new Error("utama-target/done logic wrong:\n" + String(pg).slice(0, 400));
if (!pg.includes("0/2")) throw new Error("Kab Y should be 0/2 (status-only and rejected rows are not done)");
if (!pg.includes("1/4")) throw new Error("prov row should be done/target progress (1/4):\n" + String(pg).slice(0, 400));
if (!pg.includes("<span>progress</span>")) throw new Error("donut hole should show progress, not submit+");
if (pg.includes("Komposisi Status")) throw new Error("status-composition donut title should be gone");
/* Tabel tab div[3]: enum table counts only status submitted+ rows */
DATA[4].data10 = "3. Tidak berhasil";
DATA.push({ kab: "Kab Y", status: "OPEN", data4: "1. Utama", data10: "4. Lain-lain" });
filtered = DATA;
renderPTable();
const pt = els.ptable.innerHTML;
const ix = pt.indexOf("target: jumlah sampel");
if (ix < 0) throw new Error("enum table target note missing");
const en = pt.slice(ix);
if (!en.includes("<th>Target</th>")) throw new Error("div[3] should show Target column, not Total");
if (!en.includes("(kosong)")) throw new Error("approved row with empty hasil should appear as (kosong)");
if (!en.includes("<td>2</td>")) throw new Error("Kab X target should be 2 utama rows, got:\n" + en.slice(0, 300));
if (!en.includes("<td>3</td>")) throw new Error("Kab Y target should be 3 utama rows, got:\n" + en.slice(0, 300));
/* div[2] Progress table: Target = utama, Progress = done/target */
const t1ix = pt.indexOf("<th>Target</th>");
if (t1ix < 0 || t1ix > ix) throw new Error("div[2] should show Target column before the div[3] note");
const t1 = pt.slice(t1ix, ix);
if (!t1.includes("<th>Progress</th>")) throw new Error("div[2] should show Progress column, not %Submit+");
if (!t1.includes("<td>50.0%</td>")) throw new Error("Kab X progress should be 50.0% (1/2):\n" + t1.slice(0, 400));
/* Degraded: no Kategori Sampel column -> target = all rows (X = 2/3) */
COLUMNS = COLUMNS.filter(c => c.key !== "data4");
renderProgress();
pg = els.progressgrid.innerHTML;
if (!pg.includes("2/3")) throw new Error("degraded target should count all rows:\n" + String(pg).slice(0, 400));
/* One name, two kab_code (JAYAPURA = 9403 + 9471 in FASIH): must stay two
   rows keyed by kab_code, each labeled with the name from the data. */
DATA.push({ kab: "JAYAPURA", kab_code: "9403", status: "SUBMITTED BY Pencacah", data4: "1. Utama", data10: "1. Berhasil diwawancarai" });
DATA.push({ kab: "JAYAPURA", kab_code: "9471", status: "OPEN", data4: "1. Utama", data10: "1. Berhasil diwawancarai" });
filtered = DATA;
renderProgress();
pg = els.progressgrid.innerHTML;
/* progRow titles are "NAME: done/total"; enumRow titles are "NAME: n=..." - only count the former. */
const jrow = (pg.match(/title="JAYAPURA: \d/g) || []).length;
if (jrow !== 2) throw new Error("progress must group by kab_code, not name: " + jrow + " JAYAPURA rows:\n" + String(pg).slice(0, 400));
renderPTable();
const pth = els.ptable.innerHTML;
const t1a = pth.indexOf("<th>Target</th>"), t1b = pth.indexOf("target: jumlah sampel");
const jtab = ((pth.slice(t1a, t1b).match(/>JAYAPURA</g)) || []).length;
if (jtab !== 2) throw new Error("PTable must show 2 rows labeled by name, got " + jtab);
console.log("kab_progress OK");
process.exit(0);
