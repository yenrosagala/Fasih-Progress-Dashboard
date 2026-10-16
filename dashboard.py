import csv
import json
import os

from config import data_column_labels

INPUT_JSON = "outputs/data_sample.json"
SURVEY_CSV = "outputs/csv/survey_collection_deadline_adjusted.csv"
OUTPUT_HTML = "outputs/dashboard.html"

LABELS = {
    "name": "Survei",
    "codeIdentity": "Kode Identitas",
    "status": "Status",
    "prov": "Provinsi",
    "kab": "Kabupaten/Kota",
    "kec": "Kecamatan",
    "desa": "Desa/Kelurahan",
    "sls": "SLS",
    "petugas": "Petugas",
    "peran": "Peran",
    "mode": "Mode",
    "sumError": "Error",
    "sumRemark": "Remark",
    "sumClean": "Clean",
    "done": "Selesai",
    "dateCreated": "Dibuat",
    "dateModified": "Diperbarui",
    "latitude": "Latitude",
    "longitude": "Longitude",
}

ORDER = [
    "name", "codeIdentity", "status",
    "prov", "kab", "kec", "desa", "sls",
    "petugas", "peran", "mode",
    "data1", "data2", "data3", "data4", "data5",
    "data6", "data7", "data8", "data9", "data10",
    "sumError", "sumRemark", "sumClean", "done",
    "dateCreated", "dateModified", "latitude", "longitude",
]

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{--bg:#0f172a;--card:#1e293b;--line:#334155;--fg:#e2e8f0;--mut:#94a3b8;--acc:#38bdf8;--panel2:#111c30;--hover:#172036;--track:#0b1424;--faint:#64748b}
  html[data-theme="light"]{--bg:#f1f5f9;--card:#ffffff;--line:#e2e8f0;--fg:#0f172a;--mut:#64748b;--acc:#0284c7;--panel2:#f8fafc;--hover:#eef2f7;--track:#e2e8f0;--faint:#94a3b8}
  *{box-sizing:border-box}
  body{margin:0;font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--fg)}
  header{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:12px;align-items:baseline}
  header h1{margin:0;font-size:18px}
  header .gen{color:var(--mut);font-size:12px}
  .themebtn{margin-left:auto;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:4px 12px;cursor:pointer;font-size:16px;line-height:1.4}
  .themebtn:hover{border-color:var(--acc);color:var(--acc)}
  .wrap{padding:16px 20px}
  .cards{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:130px;border-left-width:4px}
  .card .n{font-size:22px;font-weight:700}
  .card .l{color:var(--mut);font-size:12px}
  .card .s{color:var(--mut);font-size:11px;margin-top:2px}
  .filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
  .filters input,.filters select{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:7px 10px;min-width:140px}
  .filters input{min-width:240px}
  .filters button{background:var(--acc);color:#04263a;border:0;border-radius:8px;padding:7px 14px;font-weight:600;cursor:pointer}
  .tabs{display:flex;gap:6px;align-items:center;margin-bottom:14px;border-bottom:1px solid var(--line)}
  .tab{background:transparent;border:0;color:var(--mut);padding:8px 18px;cursor:pointer;font-weight:600;font-size:14px;border-bottom:2px solid transparent}
  .tab:hover{color:var(--fg)}
  .tab.active{color:var(--fg);border-bottom-color:var(--acc)}
  .tabs .gen{margin-left:auto;color:var(--mut);font-size:12px;padding-bottom:8px}
  .panel{display:none}
  .panel.active{display:block}
  .tblwrap{overflow:auto;max-height:70vh;border:1px solid var(--line);border-radius:10px}
  table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}
  th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left}
  th{position:sticky;top:0;background:var(--panel2);cursor:pointer;user-select:none;z-index:1}
  th:hover{color:var(--acc)}
  tbody tr:hover{background:var(--hover)}
  .ar{color:var(--acc);font-size:10px}
  .pager{display:flex;gap:10px;align-items:center;margin-top:10px;color:var(--mut)}
  .pager button{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:5px 12px;cursor:pointer}
  .pager button:disabled{opacity:.4;cursor:default}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}
  .sec{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
  .sec h3{margin:0 0 2px;font-size:12px;color:var(--fg);font-weight:700;text-transform:uppercase;letter-spacing:.04em}
  .sec .sub{color:var(--mut);font-size:11px;margin-bottom:10px}
  .bar{display:grid;grid-template-columns:minmax(70px,40%) 1fr auto;gap:8px;align-items:center;margin:5px 0;font-size:12px}
  .bl{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--fg)}
  .btrack{background:var(--track);border-radius:6px;height:14px;overflow:hidden}
  .bfill{background:linear-gradient(90deg,#0284c7,#38bdf8);height:100%;border-radius:6px}
  .bv{color:var(--mut);white-space:nowrap;text-align:right}
  .bp{color:var(--faint)}
  .more{color:var(--mut);font-size:11px;margin-top:8px}
  .legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:10px;font-size:12px;color:var(--mut)}
  .legend span{display:inline-flex;align-items:center;gap:5px}
  .sw{width:11px;height:11px;border-radius:3px;display:inline-block}
  .srow{display:grid;grid-template-columns:minmax(80px,34%) 1fr auto;gap:8px;align-items:center;margin:5px 0;font-size:12px}
  .sbl{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--fg)}
  .sbtrack{background:var(--track);border-radius:6px;height:16px;overflow:hidden}
  .sbfill{display:flex;height:100%;border-radius:6px;overflow:hidden}
  .seg{height:100%}
  .sbv{color:var(--mut);white-space:nowrap;text-align:right;min-width:78px}
  .sbv b{color:var(--fg)}
  .ntot{color:var(--faint)}
  .empty{color:var(--mut);font-size:12px}
  .pmeta{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:14px;font-size:13px}
  .pmeta .t{font-weight:700;font-size:15px}
  .pmeta .d{color:var(--mut);font-size:12px;margin-top:2px}
  .donutwrap{display:flex;flex-direction:column;align-items:center}
  .donut{width:190px;height:190px;border-radius:50%;position:relative;margin:4px 0 2px}
  .dhole{position:absolute;inset:26%;background:var(--card);border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center}
  .dhole b{font-size:24px;color:var(--fg)}
  .dhole span{font-size:11px;color:var(--mut)}
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <span class="gen">Diperbarui: __GENERATED__</span>
  <button id="theme" class="themebtn" title="Ganti tema terang/gelap">&#9728;</button>
</header>
<div class="wrap">
  <div class="filters" id="filters"></div>
  <div class="tabs">
    <button class="tab active" data-tab="data">Data</button>
    <button class="tab" data-tab="dashboard">Dashboard</button>
    <button class="tab" data-tab="progress">Progress</button>
    <span class="gen" id="shown"></span>
  </div>

  <section id="panel-data" class="panel active">
    <div class="tblwrap"><table><thead id="head"></thead><tbody id="body"></tbody></table></div>
    <div class="pager">
      <button id="prev">&laquo; Prev</button>
      <span id="pageinfo"></span>
      <button id="next">Next &raquo;</button>
      <label>Baris: <select id="psize">
        <option>50</option><option selected>100</option><option>250</option><option>500</option><option value="0">Semua</option>
      </select></label>
    </div>
  </section>

  <section id="panel-dashboard" class="panel">
    <div class="cards" id="cards"></div>
    <div class="grid" id="chartgrid"></div>
  </section>

  <section id="panel-progress" class="panel">
    <div class="pmeta" id="pmeta"></div>
    <div class="cards" id="pkpi"></div>
    <div class="grid" id="progressgrid"></div>
  </section>
</div>
<script>
const COLUMNS = __COLUMNS__;
const DATA = __DATA__;
const META = __META__;
const FILTER_KEYS = ["name","prov","kab","kec","desa","status","peran","mode","petugas","data4"];
const state = { q:"", page:0, pageSize:100, sort:{key:null, dir:1}, filters:{} };
FILTER_KEYS.forEach(k => state.filters[k] = "");
const LABEL = {}; COLUMNS.forEach(c => LABEL[c.key] = c.label);

// Status model, mirroring monit_vip_horti_s.py (richer-than-OPEN/DRAFT workflow).
const STATUS_DEF = [
  { key:"appr_admin",   label:"Approved Admin",    color:"#1B7F4B", aliases:["APPROVED BY ADMIN","APPROVED ADMIN","APPROVE ADMIN"] },
  { key:"appr_pengawas",label:"Approved Pengawas", color:"#5CB887", aliases:["APPROVED BY PENGAWAS","APPROVED PENGAWAS","APPROVE PENGAWAS"] },
  { key:"submitted",    label:"Submitted",         color:"#F5B731", aliases:["SUBMITTED"] },
  { key:"rejected",     label:"Ditolak",           color:"#E5484D", aliases:["REJECTED","DITOLAK","DIKEMBALIKAN"] },
  { key:"draft",        label:"Draft",             color:"#7DB3F0", aliases:["DRAFT"] },
  { key:"open",         label:"Open",              color:"#CBD3E1", aliases:["OPEN"] },
  { key:"other",        label:"Lainnya",           color:"#94A3B8", aliases:[] },
];
const STATUS = {}; STATUS_DEF.forEach(d => STATUS[d.key] = d);
const STATUS_ORDER = STATUS_DEF.map(d => d.key);
const SUBMIT_KEYS = ["submitted","appr_pengawas","appr_admin"];
const FINAL_KEYS = ["appr_admin"];

function canonStatus(v){
  const s = String(v || "").trim().toUpperCase();
  if (!s) return "other";
  for (const d of STATUS_DEF) if (d.aliases.some(a => s.includes(a))) return d.key;
  return "other";
}
function zeroCounts(){ const o = {}; STATUS_ORDER.forEach(k => o[k] = 0); return o; }
function aggregate(rows){
  const o = { total:0, assigned:0, counts:zeroCounts() };
  for (const r of rows){ o.total++; o.counts[canonStatus(val(r,"status"))]++; if (val(r,"petugas")) o.assigned++; }
  return o;
}
function aggGroups(rows, groupKey){
  const m = new Map();
  for (const r of rows){
    const g = String(val(r,groupKey) || "(kosong)");
    if (!m.has(g)) m.set(g, { total:0, assigned:0, counts:zeroCounts() });
    const o = m.get(g); o.total++; o.counts[canonStatus(val(r,"status"))]++; if (val(r,"petugas")) o.assigned++;
  }
  return [...m.entries()].map(([g,o]) => ({ g, ...o }));
}
const sumKeys = (c,keys) => keys.reduce((s,k) => s + (c[k]||0), 0);
const submitUp = o => sumKeys(o.counts, SUBMIT_KEYS);
const finalN = o => sumKeys(o.counts, FINAL_KEYS);
const startedN = o => o.total - (o.counts.open || 0);
const pctSubmit = o => o.total ? submitUp(o)/o.total*100 : 0;
const pctFinal = o => o.total ? finalN(o)/o.total*100 : 0;
const pctStarted = o => o.total ? startedN(o)/o.total*100 : 0;
const pctAssign = o => o.total ? o.assigned/o.total*100 : 0;

// Overview sections: [container id, title, value-getter, top-N]
const CHARTS = [
  ["ch-status",    "Distribusi Status",                r => val(r,"status")],
  ["ch-prov",      "Sampel per Provinsi",              r => val(r,"prov")],
  ["ch-kab",       "Sampel per Kabupaten/Kota",        r => val(r,"kab"), 15],
  ["ch-kec",       "Sampel per Kecamatan",             r => val(r,"kec"), 15],
  ["ch-desa",      "Sampel per Desa/Kelurahan",        r => val(r,"desa"), 15],
  ["ch-petugas",   "Sampel per Petugas (Pencacah)",    r => val(r,"petugas"), 15],
  ["ch-peran",     "Peran Petugas",                    r => val(r,"peran")],
  ["ch-mode",      "Mode Pendataan",                   r => val(r,"mode")],
  ["ch-jenis",     "Jenis (data3)",                    r => val(r,"data3")],
  ["ch-kat",       "Kategori Sampel (data4)",          r => val(r,"data4")],
  ["ch-komoditas", "Komoditas Utama (data9)",          r => val(r,"data9"), 15],
  ["ch-day",       "Dibuat per Tanggal",               r => String(val(r,"dateCreated")).slice(0,10)],
];

function esc(v){ return String(v ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function val(r,k){ const v = r[k]; return v === null || v === undefined ? "" : v; }

function matches(r, skip){
  for (const k of FILTER_KEYS){
    if (k === skip) continue;
    if (state.filters[k] && String(val(r,k)) !== state.filters[k]) return false;
  }
  if (state.q){
    const s = state.q.toLowerCase();
    let hit = false;
    for (const c of COLUMNS){ if (String(val(r,c.key)).toLowerCase().includes(s)){ hit = true; break; } }
    if (!hit) return false;
  }
  return true;
}

let filtered = [];

function distinctOptions(key){
  const set = new Set();
  for (const r of DATA) if (matches(r, key)) { const v = val(r,key); if (v !== "") set.add(String(v)); }
  return [...set].sort();
}

function buildFilterUI(){
  const box = document.getElementById("filters");
  box.innerHTML = "";
  const search = document.createElement("input");
  search.placeholder = "Cari (kode, nama, petugas...)";
  search.value = state.q;
  search.oninput = () => { state.q = search.value; state.page = 0; apply(); };
  box.appendChild(search);

  for (const k of FILTER_KEYS){
    const sel = document.createElement("select");
    sel.dataset.key = k;
    sel.onchange = () => { state.filters[k] = sel.value; state.page = 0; apply(); };
    box.appendChild(sel);
  }
  const reset = document.createElement("button");
  reset.textContent = "Reset";
  reset.onclick = () => { FILTER_KEYS.forEach(k => state.filters[k] = ""); state.q = ""; state.page = 0;
    document.querySelector(".filters input").value = ""; apply(); };
  box.appendChild(reset);
}

function refreshSelects(){
  document.querySelectorAll(".filters select").forEach(sel => {
    const k = sel.dataset.key;
    const opts = distinctOptions(k);
    const cur = state.filters[k];
    if (cur && !opts.includes(cur)) state.filters[k] = cur = "";
    sel.innerHTML = '<option value="">Semua ' + esc(LABEL[k] || k) + "</option>" +
      opts.map(o => '<option value="' + esc(o) + '"' + (o === cur ? " selected" : "") + ">" + esc(o) + "</option>").join("");
  });
}

function renderCards(){
  let er = 0, rm = 0, cl = 0, done = 0;
  const pet = new Set(), desa = new Set(), kab = new Set();
  for (const r of filtered){
    er += Number(val(r,"sumError")) || 0;
    rm += Number(val(r,"sumRemark")) || 0;
    cl += Number(val(r,"sumClean")) || 0;
    const d = val(r,"done"); if (d === true || d === "true" || d === 1) done++;
    if (val(r,"petugas")) pet.add(val(r,"petugas"));
    if (val(r,"desa")) desa.add(val(r,"desa"));
    if (val(r,"kab")) kab.add(val(r,"kab"));
  }
  const n = filtered.length;
  const items = [
    ["Total Sampel", n, "", "#38bdf8"],
    ["Selesai", done, (n ? (done/n*100).toFixed(1) : "0.0") + "%", "#22c55e"],
    ["Total Error", er, "", "#ef4444"],
    ["Total Remark", rm, "", "#f59e0b"],
    ["Total Clean", cl, "", "#38bdf8"],
    ["Rata-rata Error", (n ? er/n : 0).toFixed(2), "", "#94a3b8"],
    ["Petugas", pet.size, "", "#a78bfa"],
    ["Kabupaten/Kota", kab.size, "", "#14b8a6"],
    ["Desa/Kelurahan", desa.size, "", "#f472b6"],
  ];
  document.getElementById("cards").innerHTML = items.map(([l,v,s,col]) =>
    '<div class="card" style="border-left-color:' + col + '"><div class="n" style="color:' + col + '">' +
    (typeof v === "number" ? v.toLocaleString("id-ID") : esc(v)) + '</div><div class="l">' + esc(l) + "</div>" +
    (s ? '<div class="s">' + esc(s) + "</div>" : "") + "</div>").join("");
}

function groupCount(getter){
  const m = new Map();
  for (const r of filtered){ const v = getter(r); const k = String(v === "" || v === null || v === undefined ? "(kosong)" : v); m.set(k, (m.get(k) || 0) + 1); }
  return [...m.entries()].map(([k,v]) => ({k,v})).sort((a,b) => b.v - a.v || a.k.localeCompare(b.k));
}

function renderDashboard(){
  const grid = document.getElementById("chartgrid");
  grid.innerHTML = CHARTS.map(([id, title]) =>
    '<div class="sec"><h3>' + esc(title) + '</h3><div id="' + id + '"></div></div>').join("");
  for (const [id, title, getter, top] of CHARTS){
    const items = groupCount(getter);
    const el = document.getElementById(id);
    if (!items.length){ el.innerHTML = '<div class="empty">tidak ada data</div>'; continue; }
    const total = items.reduce((s,i) => s + i.v, 0) || 1;
    const shown = top ? items.slice(0, top) : items;
    const max = Math.max(...shown.map(i => i.v));
    el.innerHTML = shown.map(({k,v}) =>
      '<div class="bar" title="' + esc(k) + ': ' + v + '">' +
        '<div class="bl">' + esc(k) + '</div>' +
        '<div class="btrack"><div class="bfill" style="width:' + (v / max * 100).toFixed(1) + '%"></div></div>' +
        '<div class="bv">' + v.toLocaleString("id-ID") + ' <span class="bp">' + (v / total * 100).toFixed(1) + '%</span></div>' +
      '</div>').join("") +
      (top && items.length > top ? '<div class="more">+ ' + (items.length - top) + ' lainnya dari ' + items.length + ' kategori</div>' : "");
  }
}

/* ---------------- PROGRESS TAB (reference: monit_vip_horti_s.py) ---------------- */

function fmtStamp(s){ return (s && s.length >= 15) ? `${s.slice(6,8)}/${s.slice(4,6)}/${s.slice(0,4)} ${s.slice(9,11)}:${s.slice(11,13)}` : (s || "-"); }
function fmtDate(d){ return d.toLocaleDateString("id-ID", {day:"2-digit", month:"short", year:"numeric"}); }

function parseStamp(s){
  if (!s || s.length < 8) return null;
  const d = new Date(Date.UTC(+s.slice(0,4), +s.slice(4,6)-1, +s.slice(6,8)));
  return isNaN(d.getTime()) ? null : d;
}
// "today" = data snapshot date (META.generated), matching monit_vip_horti_s.py, so
// elapsed/remaining stay consistent with the data instead of the viewer's clock.
function daysInfo(){
  const d = { total:0, elapsed:0, left:0, txt:"periode tidak tersedia" };
  const s = META.startDate ? new Date(META.startDate) : null;
  const e = META.endDate ? new Date(META.endDate) : null;
  const now = parseStamp(META.generated) || new Date();
  if (s && e && !isNaN(s) && !isNaN(e)){
    const dd = (a,b) => Math.floor((b - a) / 86400000);
    d.total = dd(s,e) + 1;
    d.elapsed = Math.min(Math.max(dd(s,now) + 1, 0), d.total);
    d.left = Math.max(dd(now,e) + 1, 0);
    d.txt = `${fmtDate(s)} - ${fmtDate(e)} \u2022 hari ke-${d.elapsed}/${d.total} \u2022 sisa ${d.left} hari (per tanggal data)`;
  }
  return d;
}

function sec(title, sub, inner){
  return '<div class="sec"><h3>' + esc(title) + '</h3>' + (sub ? '<div class="sub">' + esc(sub) + '</div>' : "") + inner + '</div>';
}

function stackRow(g, o, showN){
  const segs = STATUS_ORDER.map(k => {
    const v = o.counts[k] || 0; if (!v) return "";
    const w = o.total ? v/o.total*100 : 0;
    return '<div class="seg" style="width:' + w.toFixed(2) + '%;background:' + STATUS[k].color +
      '" title="' + esc(g) + " - " + esc(STATUS[k].label) + ": " + v + '"></div>';
  }).join("");
  return '<div class="srow" title="' + esc(g) + ": n=" + o.total + '">' +
    '<div class="sbl">' + esc(g) + "</div>" +
    '<div class="sbtrack"><div class="sbfill">' + segs + "</div></div>" +
    '<div class="sbv"><b>' + pctSubmit(o).toFixed(0) + '%</b>' +
      (showN ? ' <span class="ntot">n=' + o.total.toLocaleString("id-ID") + "</span>" : "") + "</div></div>";
}

function statusLegend(present){
  return '<div class="legend">' + STATUS_DEF.filter(d => d.key !== "other" || present.has("other")).map(d =>
    '<span><i class="sw" style="background:' + d.color + '"></i>' + esc(d.label) + "</span>").join("") + "</div>";
}

function donut(all){
  const total = all.total || 1; let acc = 0; const stops = [];
  STATUS_ORDER.forEach(k => {
    const v = all.counts[k] || 0; if (!v) return;
    const s = acc/total*360; acc += v; const e = acc/total*360;
    stops.push(STATUS[k].color + " " + s.toFixed(2) + "deg " + e.toFixed(2) + "deg");
  });
  if (!stops.length) stops.push("#334155 0deg 360deg");
  return '<div class="donutwrap"><div class="donut" style="background:conic-gradient(' + stops.join(",") + ')">' +
    '<div class="dhole"><b>' + (all.total ? pctSubmit(all).toFixed(1) : "0.0") + '%</b><span>submit+</span></div></div></div>';
}

function progressCards(all, days){
  const rem = all.total - submitUp(all);
  const npd = rem / Math.max(days.left, 1);
  const rej = all.counts.rejected || 0;
  const items = [
    ["Total Sampel", all.total, aggGroups(filtered,"kab").length + " kab/kota", "#38bdf8"],
    ["Sudah Mulai", pctStarted(all).toFixed(1) + "%", startedN(all) + " sampel tidak OPEN", "#3E8EDE"],
    ["Submit+", pctSubmit(all).toFixed(1) + "%", submitUp(all) + " sampel", "#E0A100"],
    ["Final (Approved Admin)", pctFinal(all).toFixed(1) + "%", finalN(all) + " sampel", "#1B7F4B"],
    ["Ditolak Pengawas", rej, rej > 0 ? "perlu diperbaiki" : "tidak ada", rej > 0 ? "#E5484D" : "#94a3b8"],
    ["Sisa Waktu", days.left + " hari", "perlu \u00b1" + npd.toFixed(0) + " sampel/hari", "#8A4FFF"],
  ];
  document.getElementById("pkpi").innerHTML = items.map(([l,v,s,col]) =>
    '<div class="card" style="border-left-color:' + col + '"><div class="l">' + esc(l) + '</div>' +
    '<div class="n" style="color:' + col + '">' + (typeof v === "number" ? v.toLocaleString("id-ID") : esc(v)) + "</div>" +
    '<div class="s">' + esc(s) + "</div></div>").join("");
}

function assignRows(provs){
  const max = Math.max(...provs.map(o => o.total), 1);
  return provs.map(o => {
    const p = pctAssign(o), a = o.assigned, na = o.total - o.assigned;
    return '<div class="srow"><div class="sbl">' + esc(o.g) + '</div>' +
      '<div class="sbtrack"><div class="sbfill" style="width:' + (o.total/max*100).toFixed(1) + '%">' +
        '<div class="seg" style="width:' + p.toFixed(2) + '%;background:#2F6FED" title="Sudah assign: ' + a + '"></div>' +
        '<div class="seg" style="width:' + (100-p).toFixed(2) + '%;background:#F0A3A6" title="Belum assign: ' + na + '"></div>' +
      '</div></div>' +
      '<div class="sbv"><b>' + p.toFixed(0) + '%</b> <span class="ntot">n=' + o.total.toLocaleString("id-ID") + "</span></div></div>";
  }).join("");
}

function priorityRows(kabs, days){
  const rem = kabs.map(o => ({ g:o.g, rem:o.total - submitUp(o), npd:(o.total - submitUp(o)) / Math.max(days.left,1) }))
                  .filter(x => x.rem > 0).sort((a,b) => b.rem - a.rem).slice(0, 10);
  if (!rem.length) return '<div class="empty">Semua sampel sudah submit+</div>';
  const max = Math.max(...rem.map(x => x.rem), 1);
  const thr = [...rem.map(x => x.npd)].sort((a,b) => a-b)[Math.floor(rem.length*0.7)] || 0;
  return rem.map(x => {
    const col = x.npd >= thr ? "#E5484D" : "#F5A25D";
    return '<div class="bar"><div class="bl" title="' + esc(x.g) + '">' + esc(x.g) + '</div>' +
      '<div class="btrack"><div class="bfill" style="width:' + (x.rem/max*100).toFixed(1) + '%;background:' + col + '"></div></div>' +
      '<div class="bv">' + x.rem.toLocaleString("id-ID") + ' <span class="bp">\u00b1' + x.npd.toFixed(0) + '/hari</span></div></div>';
  }).join("");
}

function renderProgress(){
  const all = aggregate(filtered);
  const present = new Set(STATUS_ORDER.filter(k => (all.counts[k]||0) > 0));
  const days = daysInfo();
  const provs = aggGroups(filtered, "prov").sort((a,b) => pctSubmit(b) - pctSubmit(a) || b.total - a.total);
  const kabs  = aggGroups(filtered, "kab").sort((a,b) => pctSubmit(b) - pctSubmit(a) || b.total - a.total);

  document.getElementById("pmeta").innerHTML =
    '<div class="t">' + esc(META.name || "Monitoring Progress") + '</div>' +
    '<div class="d">Data per ' + esc(fmtStamp(META.generated)) + "  |  " + esc(days.txt) +
    "  |  " + filtered.length.toLocaleString("id-ID") + " sampel (terfilter)</div>";

  progressCards(all, days);

  document.getElementById("progressgrid").innerHTML =
    sec("Komposisi Status", "Seluruh sampel (terfilter)", donut(all) + statusLegend(present)) +
    sec("Progress per Provinsi", "% dari total sampel \u2022 angka tebal = % submit+",
        provs.map(o => stackRow(o.g, o, true)).join("") || '<div class="empty">tidak ada data</div>' +
        statusLegend(present)) +
    sec("Progress per Kabupaten/Kota", "Urut dari % submit+ tertinggi \u2022 warna = status sampel",
        kabs.map(o => stackRow(o.g, o, true)).join("") || '<div class="empty">tidak ada data</div>') +
    sec("Status Assignment", "Sudah vs belum di-assign ke petugas (per provinsi)", assignRows(provs)) +
    sec("Prioritas: Sisa Sampel Terbanyak", "10 kabupaten dengan sisa (belum submit+) terbanyak",
        priorityRows(kabs, days));
}

/* ---------------- DATA TAB ---------------- */

function renderTable(){
  const head = document.getElementById("head");
  head.innerHTML = "<tr>" + COLUMNS.map(c =>
    '<th data-k="' + c.key + '">' + esc(c.label) +
    '<span class="ar">' + (state.sort.key === c.key ? (state.sort.dir > 0 ? " \u25B2" : " \u25BC") : "") + "</span></th>").join("") + "</tr>";

  const size = state.pageSize || filtered.length || 1;
  const maxPage = Math.max(0, Math.ceil(filtered.length / size) - 1);
  if (state.page > maxPage) state.page = maxPage;
  const start = state.page * size;
  const page = filtered.slice(start, start + size);

  document.getElementById("body").innerHTML = page.map(r =>
    "<tr>" + COLUMNS.map(c => "<td>" + esc(val(r,c.key)) + "</td>").join("") + "</tr>").join("");

  document.getElementById("pageinfo").textContent =
    (filtered.length ? (start+1).toLocaleString("id-ID") + "-" + Math.min(start+size, filtered.length).toLocaleString("id-ID") + " / " : "") +
    filtered.length.toLocaleString("id-ID");
  document.getElementById("prev").disabled = state.page <= 0;
  document.getElementById("next").disabled = state.page >= maxPage;
  document.getElementById("shown").textContent = filtered.length.toLocaleString("id-ID") + " sampel";
}

function apply(){
  filtered = DATA.filter(r => matches(r, null));
  if (state.sort.key){
    const k = state.sort.key, d = state.sort.dir;
    filtered.sort((a,b) => {
      const x = val(a,k), y = val(b,k);
      const nx = parseFloat(x), ny = parseFloat(y);
      if (!isNaN(nx) && !isNaN(ny) && x !== "" && y !== "") return (nx-ny)*d;
      return String(x).localeCompare(String(y))*d;
    });
  }
  refreshSelects();
  renderCards();
  renderDashboard();
  renderProgress();
  renderTable();
}

document.querySelectorAll(".tab").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.id === "panel-" + btn.dataset.tab));
  };
});

document.getElementById("head").addEventListener("click", e => {
  const th = e.target.closest("th"); if (!th) return;
  const k = th.dataset.k;
  state.sort = state.sort.key === k ? { key:k, dir:-state.sort.dir } : { key:k, dir:1 };
  renderTable();
});
document.getElementById("prev").onclick = () => { state.page--; renderTable(); };
document.getElementById("next").onclick = () => { state.page++; renderTable(); };
document.getElementById("psize").onchange = e => { state.pageSize = parseInt(e.target.value,10); state.page = 0; renderTable(); };

buildFilterUI();
apply();

const themeBtn = document.getElementById("theme");
function applyTheme(t){
  document.documentElement.setAttribute("data-theme", t);
  themeBtn.textContent = t === "light" ? "\u263E" : "\u2600";
}
let savedTheme = "dark";
try { savedTheme = localStorage.getItem("fasih-theme") || "dark"; } catch(e){}
applyTheme(savedTheme);
themeBtn.onclick = () => {
  const t = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
  try { localStorage.setItem("fasih-theme", t); } catch(e){}
  applyTheme(t);
};
</script>
</body>
</html>
"""


def _columns(sample_row):
    cols, seen = [], set()
    for key in ORDER:
        if key in sample_row:
            label = data_column_labels.get(key) or LABELS.get(key)
            if not label and key.startswith("data") and key[4:].isdigit():
                label = f"Data {key[4:]}"
            cols.append({"key": key, "label": label or key})
            seen.add(key)
    for key in sample_row:
        if key not in seen:
            cols.append({"key": key, "label": key})
    return cols


def _meta(blob):
    meta = {"generated": blob.get("generated", ""), "name": "", "startDate": "", "endDate": ""}
    if os.path.exists(SURVEY_CSV):
        with open(SURVEY_CSV, encoding="utf-8") as f:
            row = next(csv.DictReader(f), None)
            if row:
                meta["name"] = row.get("name") or ""
                meta["startDate"] = row.get("startDate") or ""
                meta["endDate"] = row.get("endDate") or ""
    return meta


def build_dashboard(input_json=INPUT_JSON, output_html=OUTPUT_HTML):
    if not os.path.exists(input_json):
        print("  no data_sample.json, skipping dashboard")
        return
    with open(input_json, encoding="utf-8") as f:
        blob = json.load(f)
    rows = blob.get("rows", [])
    if not rows:
        print("  data_sample.json empty, skipping dashboard")
        return
    html = (_TEMPLATE
            .replace("__TITLE__", "Dashboard Sampel FASIH")
            .replace("__GENERATED__", blob.get("generated", ""))
            .replace("__COLUMNS__", json.dumps(_columns(rows[0]), ensure_ascii=False).replace("</", "<\\/"))
            .replace("__META__", json.dumps(_meta(blob), ensure_ascii=False).replace("</", "<\\/"))
            .replace("__DATA__", json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")))
    os.makedirs(os.path.dirname(output_html) or ".", exist_ok=True)
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  dashboard: {output_html} ({len(rows)} rows)")


if __name__ == "__main__":
    build_dashboard()
