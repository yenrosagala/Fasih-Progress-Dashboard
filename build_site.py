"""Build a static multi-survey site (Phase 1, mock/static data).

Emits into outputs/site/:
  index.html            the shell: survey picker + adaptive Data/Dashboard/Progress tabs
  surveys.json          manifest the shell loads first
  data/<id>.json        one payload per survey (columns, statusMap, rows, meta)

The shell renders whatever schema a payload declares, so the same frontend works
for any survey. Phase 1 serves pre-built JSON; a later backend swaps the fetch
for API calls without touching the shell.
"""
import csv
import json
import os
import zlib

from config import data_column_labels

DATA_JSON = "outputs/data_sample.json"
SURVEY_CFG = "inputs/survey_config.json"
SITE_DIR = "outputs/site"

LABELS = {
    "name": "Survei", "periode": "Periode", "codeIdentity": "Kode Identitas", "status": "Status",
    "prov": "Provinsi", "kab": "Kabupaten/Kota", "kec": "Kecamatan",
    "desa": "Desa/Kelurahan", "sls": "SLS", "petugas": "Petugas", "peran": "Peran",
    "mode": "Mode", "sumError": "Error", "sumRemark": "Remark", "sumClean": "Clean",
    "done": "Selesai", "dateCreated": "Dibuat", "dateModified": "Diperbarui",
    "latitude": "Latitude", "longitude": "Longitude",
}
ORDER = [
    "name", "periode", "codeIdentity", "status", "prov", "kab", "kec", "desa", "sls",
    "petugas", "peran", "mode", "data1", "data2", "data3", "data4", "data5",
    "data6", "data7", "data8", "data9", "data10",
    "sumError", "sumRemark", "sumClean", "done",
    "dateCreated", "dateModified", "latitude", "longitude",
]

# Canonical status buckets (reference: monit_vip_horti_s.py). Aliases are matched
# by substring, in order, against the row's raw status value. Any survey can
# override this by shipping its own statusMap.
STATUS_MAP = [
    {"key": "final", "label": "Approved Admin", "color": "#1B7F4B",
     "aliases": ["COMPLETED BY ADMIN", "APPROVED BY ADMIN", "APPROVE ADMIN", "CLEAN"]},
    {"key": "approved", "label": "Approved Pengawas", "color": "#5CB887",
     "aliases": ["COMPLETED BY PENGAWAS", "APPROVED BY PENGAWAS", "APPROVE PENGAWAS"]},
    {"key": "submitted", "label": "Submitted", "color": "#F5B731", "aliases": ["SUBMITTED"]},
    {"key": "rejected", "label": "Ditolak", "color": "#E5484D",
     "aliases": ["REJECTED", "REVOKED", "EDITED", "DITOLAK"]},
    {"key": "draft", "label": "Draft", "color": "#7DB3F0", "aliases": ["DRAFT"]},
    {"key": "open", "label": "Open", "color": "#CBD3E1", "aliases": ["OPEN", "BELUM_ENTRY"]},
    {"key": "other", "label": "Lainnya", "color": "#94A3B8", "aliases": []},
]

_DEMO_NAME = "[ CONTOH ] VIP-HORTI.S 2026"
_DEMO_ID = "demo-vip-horti"
_BUCKET_ALIAS = {
    "final": "APPROVED BY ADMIN KABUPATEN", "approved": "APPROVED BY PENGAWAS",
    "submitted": "SUBMITTED BY PENCACAH", "rejected": "REJECTED BY PENGAWAS",
    "draft": "DRAFT", "open": "OPEN",
}
_DEMO_CYCLE = (["final"] * 40 + ["approved"] * 20 + ["submitted"] * 15
               + ["rejected"] * 7 + ["draft"] * 8 + ["open"] * 10)


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


def _payload(sid, name, stype, rows, generated, period, demo=False):
    return {
        "id": sid, "name": name, "type": stype, "demo": demo,
        "generated": generated, "period": period,
        "columns": _columns(rows[0]) if rows else [],
        "statusMap": STATUS_MAP,
        "submitKeys": ["submitted", "approved", "final"],
        "finalKeys": ["final"],
        "rows": rows,
    }


def _demo_rows(rows, generated):
    out = []
    for r in rows:
        rec = dict(r)
        key = f'{rec.get("prov_code")}|{rec.get("kab_code")}|{rec.get("codeIdentity")}'
        bucket = _DEMO_CYCLE[zlib.crc32(key.encode()) % len(_DEMO_CYCLE)]
        rec["name"] = _DEMO_NAME
        rec["status"] = _BUCKET_ALIAS[bucket]
        out.append(rec)
    return out


def _clean(o):
    # pandas emits float('nan') for missing cells; NaN/Inf are invalid JSON.
    if isinstance(o, float):
        return None if (o != o or o in (float("inf"), float("-inf"))) else o
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_clean(obj), f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _load_cfg():
    with open(SURVEY_CFG, encoding="utf-8") as f:
        return json.load(f).get("selected_surveys", [])


def write_payload(sid, name, stype, rows, generated, period, demo=False):
    """Write one survey payload to data/<sid>.json; returns it."""
    payload = _payload(sid, name, stype, rows, generated, period, demo)
    _write(os.path.join(SITE_DIR, "data", f"{sid}.json"), payload)
    return payload


def rebuild_manifest():
    """Rebuild surveys.json from the data/*.json payloads on disk.

    Lets a refresh of a single survey update the manifest without rebuilding
    every payload. Configured surveys keep survey_config.json order; demo last.
    """
    order = {s.get("name"): i for i, s in enumerate(_load_cfg())}
    ddir = os.path.join(SITE_DIR, "data")
    items, generated = [], ""
    files = sorted(os.listdir(ddir)) if os.path.isdir(ddir) else []
    for fn in files:
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(ddir, fn), encoding="utf-8") as f:
            p = json.load(f)
        if (p.get("generated") or "") > generated:
            generated = p.get("generated") or ""
        items.append({"id": p.get("id"), "name": p.get("name", ""), "type": p.get("type", ""),
                      "demo": bool(p.get("demo")), "period": p.get("period", {"start": "", "end": ""}),
                      "rows": len(p.get("rows", [])), "hasData": bool(p.get("rows"))})
    items.sort(key=lambda x: (1 if x["demo"] else 0, order.get(x["name"], 10 ** 6), x["name"]))
    _write(os.path.join(SITE_DIR, "surveys.json"), {"generated": generated, "surveys": items})
    return items


def build_site():
    if not os.path.exists(DATA_JSON):
        print(f"  no {DATA_JSON}, skipping site")
        return
    with open(DATA_JSON, encoding="utf-8") as f:
        blob = json.load(f)
    all_rows = blob.get("rows", [])
    generated = blob.get("generated", "")

    made = 0
    for s in _load_cfg():
        sid = s.get("surveyPeriodId")
        if not sid:
            continue
        rows = [r for r in all_rows if r.get("name") == s.get("name")]
        period = {"start": s.get("surveyPeriodStartDate", ""), "end": s.get("surveyPeriodEndDate", "")}
        write_payload(sid, s.get("name", ""), s.get("type", ""), rows, generated, period)
        made += 1

    # Demo survey: same region columns, statuses spread across all buckets, so the
    # picker + adaptive schema are demonstrable on static data.
    if all_rows:
        demo = _demo_rows(all_rows, generated)
        write_payload(_DEMO_ID, _DEMO_NAME, "pencacahan", demo, generated,
                      {"start": "", "end": ""}, demo=True)
        made += 1

    rebuild_manifest()
    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(_SHELL)
    print(f"  site: {SITE_DIR}/index.html ({made} surveys, {len(all_rows)} base rows)")


_SHELL = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard Sampel FASIH</title>
<style>
  :root{--bg:#0f172a;--card:#1e293b;--line:#334155;--fg:#e2e8f0;--mut:#94a3b8;--acc:#38bdf8;--panel2:#111c30;--hover:#172036;--track:#0b1424;--faint:#64748b}
  html[data-theme="light"]{--bg:#f1f5f9;--card:#ffffff;--line:#e2e8f0;--fg:#0f172a;--mut:#64748b;--acc:#0284c7;--panel2:#f8fafc;--hover:#eef2f7;--track:#e2e8f0;--faint:#94a3b8}
  *{box-sizing:border-box}
  body{margin:0;font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--fg)}
  header{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:12px;align-items:center}
  header h1{margin:0;font-size:18px}
  header .gen{color:var(--mut);font-size:12px}
  .pick{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:6px 10px;min-width:220px;font:inherit}
  .pick:hover{border-color:var(--acc)}
  .pill{background:var(--acc);color:#04263a;border-radius:999px;padding:2px 10px;font-size:11px;font-weight:700}
  .themebtn{margin-left:auto;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:4px 12px;cursor:pointer;font-size:16px;line-height:1.4}
  .themebtn:hover{border-color:var(--acc);color:var(--acc)}
  .hdr-actions{margin-left:auto;display:flex;gap:10px;align-items:center}
  .hdr-actions .themebtn{margin-left:0}
  .hdr-actions .pngbtn{margin-left:0;margin-bottom:0}
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
  .pngbtn{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:5px 12px;cursor:pointer;font:inherit;font-weight:600;font-size:12px;margin-left:10px;margin-bottom:8px}
  .pngbtn:hover{border-color:var(--acc);color:var(--acc)}
  .pngbtn:disabled{opacity:.6;cursor:default}
  .pngbtn.busy::after{content:"";display:inline-block;width:.72em;height:.72em;margin-left:.45em;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;vertical-align:-1px;animation:spin .7s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
  .modal{position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:50;padding:16px}
  .modalbox{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;max-width:560px;width:100%;max-height:90vh;overflow:auto}
  .modalbox h3{margin:0 0 8px;font-size:16px}
  .modalbox ol{margin:8px 0;padding-left:20px;font-size:12px;color:var(--mut)}
  .modalbox ol b{color:var(--fg)}
  .modalbox textarea{width:100%;min-height:110px;background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:8px;font:12px/1.4 ui-monospace,Consolas,monospace;resize:vertical}
  .modalbox .fasihbtn{display:inline-block;text-decoration:none;background:var(--acc);color:#04263a;border-radius:6px;padding:3px 12px;font-weight:700;font-size:12px;margin:2px 0}
  .modalbox .fasihbtn:hover{filter:brightness(1.08)}
  .modalmsg{min-height:18px;font-size:12px;margin:6px 0}
  .modalmsg.ok{color:#5CB887}
  .modalmsg.err{color:#E5484D}
  .modalfoot{display:flex;gap:8px;justify-content:flex-end}
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
  .sec.zoomable{cursor:zoom-in;transition:border-color .15s}
  .sec.zoomable:hover{border-color:var(--acc)}
  .cmmore{color:var(--mut);font-size:11px;margin:0 0 10px}
  .cmbody{max-height:60vh;overflow:auto;padding-right:4px}
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
  .donut svg{display:block}
  .dhole{position:absolute;inset:26%;background:var(--card);border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center}
  .dhole b{font-size:24px;color:var(--fg)}
  .dhole span{font-size:11px;color:var(--mut)}
  .notice{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;color:var(--mut)}
  .notice.err{border-color:#E5484D;color:#F0A3A6}
  #rfov{position:fixed;inset:0;background:rgba(6,8,12,.68);backdrop-filter:blur(2px);display:none;align-items:center;justify-content:center;z-index:60;padding:16px}
  #rfov.on{display:flex}
  .rfbox{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;min-width:280px;max-width:440px;box-shadow:0 12px 48px rgba(0,0,0,.5)}
  .rfspin{width:34px;height:34px;border:3px solid var(--line);border-top-color:var(--acc);border-radius:50%;margin:0 auto 12px;animation:spin .8s linear infinite}
  .rfbox h3{margin:0 0 2px;font-size:15px;text-align:center}
  .rfsub{text-align:center;color:var(--mut);font-size:12px}
  .rfsteps{list-style:none;margin:14px 0 0;padding:0;font-size:13px}
  .rfsteps li{display:flex;gap:9px;align-items:center;padding:5px 0;color:var(--mut)}
  .rfsteps li.done{color:var(--fg)}
  .rfsteps li.cur{color:var(--acc);font-weight:600}
  .rfdot{width:14px;text-align:center;flex:none}
  .user{color:var(--mut);font-size:12px}
  .steps{list-style:none;display:flex;gap:8px;padding:0;margin:0 0 14px;flex-wrap:wrap}
  .step{display:flex;align-items:center;gap:8px;padding:8px 14px;border:1px solid var(--line);border-radius:999px;color:var(--mut);font-size:13px;font-weight:600;background:var(--card);cursor:pointer}
  .step .dot{width:20px;height:20px;border-radius:50%;background:var(--line);color:var(--fg);display:flex;align-items:center;justify-content:center;font-size:11px;flex:none}
  .step.active{border-color:var(--acc);color:var(--fg)}
  .step.active .dot{background:var(--acc);color:#04263a}
  .step.done .dot{background:#22c55e;color:#04263a}
  .step.disabled{opacity:.45;cursor:default}
  .stepbody{display:flex;gap:10px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px;flex-wrap:wrap}
  .stepbody .lbl{font-size:12px;color:var(--mut);font-weight:600}
  .stepbody .pick{flex:1;min-width:220px}
  .go{background:var(--acc);color:#04263a;border:0;border-radius:8px;padding:8px 18px;font:inherit;font-weight:700;cursor:pointer}
  .go:hover{filter:brightness(1.08)}
  .go:disabled{opacity:.5;cursor:default}
</style>
</head>
<body>
<header>
  <h1 id="title">Dashboard Sampel FASIH</h1>
  <span class="pill" id="demopill" style="display:none">data contoh</span>
  <span class="gen" id="genlabel"></span>
  <div class="hdr-actions">
    <span class="user" id="userchip" style="display:none"></span>
    <button id="refresh" class="pngbtn" title="Ambil ulang data periode terpilih dari FASIH" style="display:none">&#8635; Perbarui</button>
    <button id="setsess" class="pngbtn" title="Atur sesi login FASIH untuk refresh" style="display:none">&#9881; Atur Sesi</button>
    <button id="theme" class="themebtn" title="Ganti tema terang/gelap">&#9728;</button>
    <a id="logout" class="pngbtn" href="/auth/logout" title="Keluar" style="display:none">Keluar</a>
  </div>
</header>
<div class="wrap">
  <div id="statusbox" class="notice">Memuat daftar survei&hellip;</div>
  <div id="wizard" style="display:none">
    <ol class="steps">
      <li class="step" id="st1" title="Pilih survei"><span class="dot">1</span><span>Pilih Survei</span></li>
      <li class="step" id="st2" title="Pilih periode"><span class="dot">2</span><span>Pilih Periode</span></li>
      <li class="step" id="st3" title="Lihat data"><span class="dot">3</span><span>Data</span></li>
    </ol>
    <div class="stepbody" id="sb1">
      <label class="lbl" for="picker">Survei</label>
      <select id="picker" class="pick" title="Pilih survei"></select>
      <button id="toStep2" class="go">Lanjut &rarr;</button>
    </div>
    <div class="stepbody" id="sb2" style="display:none">
      <button id="back1" class="pngbtn">&#8592; Kembali</button>
      <label class="lbl" for="period">Periode</label>
      <select id="period" class="pick" title="Pilih periode"></select>
      <button id="toStep3" class="go">Lihat Data &rarr;</button>
    </div>
  </div>
  <div id="app" style="display:none">
    <div class="filters" id="filters"></div>
    <div class="tabs">
      <button class="tab active" data-tab="data">Data</button>
      <button class="tab" data-tab="dashboard">Dashboard</button>
      <button class="tab" data-tab="progress">Progress</button>
      <span class="gen" id="shown"></span>
      <button id="png" class="pngbtn" title="Unduh tampilan ini sebagai PNG (tanpa header &amp; judul tab)">&#11015; PNG</button>
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
</div>
<div id="sessmodal" class="modal" style="display:none">
  <div class="modalbox" role="dialog" aria-modal="true" aria-label="Atur sesi FASIH">
    <h3>Atur Sesi FASIH</h3>
    <p class="gen">Sesi ini disimpan di server dan dipakai tombol &ldquo;Perbarui&rdquo;. Tidak perlu mengubah file di server.</p>
    <ol>
      <li>Buka FASIH dan login di browser:<br>
        <a class="fasihbtn" href="https://fasih-sm.bps.go.id/" target="_blank" rel="noopener">Buka FASIH &#8599;</a>
      </li>
      <li>Tekan <b>F12</b> &rarr; tab <b>Network</b> &rarr; muat ulang halaman.</li>
      <li>Klik permintaan mana pun &rarr; <b>Request Headers</b> &rarr; cari <b>Cookie</b>.</li>
      <li>Klik kanan nilainya &rarr; <b>Copy value</b>, lalu tempel di kotak bawah.</li>
    </ol>
    <textarea id="sessinput" spellcheck="false" placeholder="Tempel nilai header Cookie di sini..."></textarea>
    <div class="modalmsg" id="sessmsg"></div>
    <div class="modalfoot">
      <button id="sesscancel" class="pngbtn">Batal</button>
      <button id="sesssave" class="pngbtn">Simpan</button>
    </div>
  </div>
</div>
<div id="chartmodal" class="modal" style="display:none">
  <div class="modalbox" role="dialog" aria-modal="true" aria-label="Perbesar grafik">
    <h3 id="cmtitle"></h3>
    <div class="cmmore" id="cmsub"></div>
    <div id="cmbody" class="cmbody"></div>
    <div class="modalfoot">
      <button id="cmclose" class="pngbtn">Tutup</button>
    </div>
  </div>
</div>
<div id="rfov" role="alertdialog" aria-live="polite" aria-label="Memperbarui data">
  <div class="rfbox">
    <div class="rfspin"></div>
    <h3>Memperbarui data dari FASIH</h3>
    <div class="rfsub">Mohon tunggu, proses ini bisa beberapa menit.</div>
    <ul class="rfsteps" id="rfsteps"></ul>
    <div class="rfsub" id="rfdetail" style="margin:10px 0 0;display:none"></div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/html2canvas-pro@1/dist/html2canvas-pro.min.js" onerror="var s=document.createElement('script');s.src='https://unpkg.com/html2canvas-pro@1/dist/html2canvas-pro.min.js';document.head.appendChild(s);"></script>
<script>
/* ---------- adaptive schema: everything below is set per survey ---------- */
let COLUMNS = [], DATA = [], META = {}, LABEL = {};
let STATUS_DEF = [], STATUS = {}, STATUS_ORDER = [], SUBMIT_KEYS = [], FINAL_KEYS = [];
let FILTER_KEYS = [], CHARTS = [];
let state = { q:"", page:0, pageSize:100, sort:{key:null, dir:1}, filters:{} };
let CUR = { sid:"", pid:"" };  // current survey + period (on-demand backend flow)

const PREFERRED_FILTERS = ["periode","name","prov","kab","kec","desa","status","peran","mode","petugas","data3","data4","data9"];
/* Filters are derived from whatever columns a payload actually ships: any column
   with a small set of distinct values becomes a dropdown. PREFERRED_FILTERS only
   sets the display order; columns the scrape drops simply never appear. The cap
   keeps identifiers, coordinates, dates and free-text (names/addresses) out —
   they'd be one-option or thousands-of-options dropdowns. */
const MAX_FILTER_DISTINCT = 1000;
const NO_FILTER = new Set(["codeIdentity","latitude","longitude","dateCreated","dateModified",
                           "prov_code","kab_code","kec_code","desa_code","sls_code"]);
const CHART_DEFS = [
  ["status","Distribusi Status"], ["prov","Sampel per Provinsi"],
  ["kab","Sampel per Kabupaten/Kota",15], ["kec","Sampel per Kecamatan",15],
  ["desa","Sampel per Desa/Kelurahan",15], ["petugas","Sampel per Petugas",15],
  ["peran","Peran Petugas"], ["mode","Mode Pendataan"],
  ["data3","Jenis (data3)"], ["data4","Kategori Sampel (data4)"],
  ["data9","Komoditas Utama (data9)",15], ["dateCreated","Dibuat per Tanggal"],
];

/* ---------- shared helpers ---------- */
function esc(v){ return String(v ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function val(r,k){ const v = r[k]; return v === null || v === undefined ? "" : v; }

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

function buildCharts(){
  CHARTS = [];
  const keys = new Set(COLUMNS.map(c => c.key));
  for (const [key, title, top] of CHART_DEFS){
    if (!keys.has(key)) continue;
    const getter = key === "dateCreated" ? (r => String(val(r,"dateCreated")).slice(0,10)) : (r => val(r,key));
    CHARTS.push(["ch-" + key, title, getter, top]);
  }
}

function computeFilterKeys(){
  const kept = [];
  for (const c of COLUMNS){
    const k = c.key;
    if (NO_FILTER.has(k)) continue;
    const seen = new Set();
    for (const r of DATA){
      const v = val(r,k);
      if (v !== "") seen.add(v);
      if (seen.size > MAX_FILTER_DISTINCT) break;
    }
    if (seen.size >= 2 && seen.size <= MAX_FILTER_DISTINCT) kept.push({ k, n:seen.size });
  }
  const prio = k => { const i = PREFERRED_FILTERS.indexOf(k); return i === -1 ? 1e3 : i; };
  kept.sort((a,b) => prio(a.k) - prio(b.k) || a.n - b.n || a.k.localeCompare(b.k));
  return kept.map(x => x.k);
}

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
  const has = k => COLUMNS.some(c => c.key === k);
  const items = [["Total Sampel", n, "", "#38bdf8"]];
  if (has("done")) items.push(["Selesai", done, (n ? (done/n*100).toFixed(1) : "0.0") + "%", "#22c55e"]);
  if (has("sumError")) items.push(["Total Error", er, "", "#ef4444"]);
  if (has("sumRemark")) items.push(["Total Remark", rm, "", "#f59e0b"]);
  if (has("sumClean")) items.push(["Total Clean", cl, "", "#38bdf8"]);
  if (has("sumError")) items.push(["Rata-rata Error", (n ? er/n : 0).toFixed(2), "", "#94a3b8"]);
  if (has("petugas")) items.push(["Petugas", pet.size, "", "#a78bfa"]);
  if (has("kab")) items.push(["Kabupaten/Kota", kab.size, "", "#14b8a6"]);
  if (has("desa")) items.push(["Desa/Kelurahan", desa.size, "", "#f472b6"]);
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

function barHTML(items, total){
  const max = Math.max(...items.map(i => i.v), 1);
  return items.map(({k,v}) =>
    '<div class="bar" title="' + esc(k) + ': ' + v + '">' +
      '<div class="bl">' + esc(k) + '</div>' +
      '<div class="btrack"><div class="bfill" style="width:' + (v / max * 100).toFixed(1) + '%"></div></div>' +
      '<div class="bv">' + v.toLocaleString("id-ID") + ' <span class="bp">' + (v / total * 100).toFixed(1) + '%</span></div>' +
    '</div>').join("");
}

function renderDashboard(){
  const grid = document.getElementById("chartgrid");
  grid.innerHTML = CHARTS.map(([id, title]) =>
    '<div class="sec zoomable"><h3>' + esc(title) + '</h3><div id="' + id + '"></div></div>').join("");
  for (const [id, title, getter, top] of CHARTS){
    const items = groupCount(getter);
    const el = document.getElementById(id);
    if (!items.length){ el.innerHTML = '<div class="empty">tidak ada data</div>'; continue; }
    const total = items.reduce((s,i) => s + i.v, 0) || 1;
    const shown = top ? items.slice(0, top) : items;
    el.innerHTML = barHTML(shown, total) +
      (top && items.length > top ? '<div class="more">+ ' + (items.length - top) + ' lainnya dari ' + items.length + ' kategori &mdash; klik untuk lihat semua</div>' : "");
    const sec = el.parentElement;
    sec.onclick = () => openChart(title, items);
  }
}

function openChart(title, items){
  const total = items.reduce((s,i) => s + i.v, 0) || 1;
  document.getElementById("cmtitle").textContent = title;
  document.getElementById("cmsub").textContent = items.length.toLocaleString("id-ID") + " kategori";
  document.getElementById("cmbody").innerHTML = barHTML(items, total);
  document.getElementById("chartmodal").style.display = "flex";
}

/* ---------------- PROGRESS TAB (reference: monit_vip_horti_s.py) ---------------- */

function fmtStamp(s){ return (s && s.length >= 15) ? `${s.slice(6,8)}/${s.slice(4,6)}/${s.slice(0,4)} ${s.slice(9,11)}:${s.slice(11,13)}` : (s || "-"); }
function fmtDate(d){ return d.toLocaleDateString("id-ID", {day:"2-digit", month:"short", year:"numeric"}); }

function parseStamp(s){
  if (!s || s.length < 8) return null;
  const d = new Date(Date.UTC(+s.slice(0,4), +s.slice(4,6)-1, +s.slice(6,8)));
  return isNaN(d.getTime()) ? null : d;
}
// "today" = data snapshot date (META.generated), so elapsed/remaining stay
// consistent with the data instead of the viewer's clock.
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
  const total = all.total || 1, R = 70, SW = 50, C = 2 * Math.PI * R;
  let acc = 0;
  const segs = STATUS_ORDER.map(k => {
    const v = all.counts[k] || 0; if (!v) return "";
    const len = v / total * C, off = -acc * C; acc += v / total;
    return '<circle cx="95" cy="95" r="' + R + '" fill="none" stroke="' + STATUS[k].color +
      '" stroke-width="' + SW + '" stroke-dasharray="' + len.toFixed(2) + " " + (C - len).toFixed(2) +
      '" stroke-dashoffset="' + off.toFixed(2) + '"></circle>';
  }).join("");
  const ring = segs || '<circle cx="95" cy="95" r="' + R + '" fill="none" stroke="#334155" stroke-width="' + SW + '"></circle>';
  return '<div class="donutwrap"><div class="donut">' +
    '<svg viewBox="0 0 190 190" width="190" height="190" role="img" aria-label="Komposisi status sampel">' +
    '<g transform="rotate(-90 95 95)">' + ring + '</g></svg>' +
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
  const hasProv = COLUMNS.some(c => c.key === "prov");
  const hasKab = COLUMNS.some(c => c.key === "kab");
  const provs = hasProv ? aggGroups(filtered, "prov").sort((a,b) => pctSubmit(b) - pctSubmit(a) || b.total - a.total) : [];
  const kabs  = hasKab  ? aggGroups(filtered, "kab").sort((a,b) => pctSubmit(b) - pctSubmit(a) || b.total - a.total) : [];

  document.getElementById("pmeta").innerHTML =
    '<div class="t">' + esc(META.name || "Monitoring Progress") + '</div>' +
    '<div class="d">Data per ' + esc(fmtStamp(META.generated)) + "  |  " + esc(days.txt) +
    "  |  " + filtered.length.toLocaleString("id-ID") + " sampel (terfilter)</div>";

  progressCards(all, days);

  const sections = [ sec("Komposisi Status", "Seluruh sampel (terfilter)", donut(all) + statusLegend(present)) ];
  if (hasProv) sections.push(sec("Progress per Provinsi", "% dari total sampel \u2022 angka tebal = % submit+",
      provs.map(o => stackRow(o.g, o, true)).join("") || '<div class="empty">tidak ada data</div>' + statusLegend(present)));
  if (hasKab) sections.push(sec("Progress per Kabupaten/Kota", "Urut dari % submit+ tertinggi \u2022 warna = status sampel",
      kabs.map(o => stackRow(o.g, o, true)).join("") || '<div class="empty">tidak ada data</div>'));
  if (hasProv) sections.push(sec("Status Assignment", "Sudah vs belum di-assign ke petugas (per provinsi)", assignRows(provs)));
  if (hasKab) sections.push(sec("Prioritas: Sisa Sampel Terbanyak", "10 kabupaten dengan sisa (belum submit+) terbanyak",
      priorityRows(kabs, days)));
  document.getElementById("progressgrid").innerHTML = sections.join("");
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
  if (!DATA.length){ filtered = []; }
  else filtered = DATA.filter(r => matches(r, null));
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

/* ---------------- boot / step-by-step wizard ---------------- */

let STEP = 1;

function setStep(n){
  STEP = n;
  document.getElementById("sb1").style.display = n === 1 ? "" : "none";
  document.getElementById("sb2").style.display = (n === 2 && BACKEND) ? "" : "none";
  document.getElementById("app").style.display = n === 3 ? "" : "none";
  [1,2,3].forEach(i => {
    const el = document.getElementById("st" + i);
    el.classList.toggle("active", i === n);
    el.classList.toggle("done", i < n);
  });
  document.getElementById("st2").style.display = BACKEND ? "" : "none";
  document.getElementById("wizard").style.display = "";
}

function applySurvey(s){
  META = { id:s.id||"", generated:s.generated||"", name:s.name||"", type:s.type||"", demo:!!s.demo,
           startDate:(s.period||{}).start||"", endDate:(s.period||{}).end||"" };
  COLUMNS = s.columns || [];
  DATA = s.rows || [];
  STATUS_DEF = (s.statusMap && s.statusMap.length) ? s.statusMap : [];
  STATUS = {}; STATUS_DEF.forEach(d => STATUS[d.key] = d);
  STATUS_ORDER = STATUS_DEF.map(d => d.key);
  SUBMIT_KEYS = s.submitKeys || ["submitted","approved","final"];
  FINAL_KEYS = s.finalKeys || ["final"];
  LABEL = {}; COLUMNS.forEach(c => LABEL[c.key] = c.label);
  FILTER_KEYS = computeFilterKeys();
  buildCharts();
  state = { q:"", page:0, pageSize:state.pageSize || 100, sort:{key:null, dir:1}, filters:{} };
  FILTER_KEYS.forEach(k => state.filters[k] = "");

  document.getElementById("title").textContent = s.name || "Dashboard Sampel FASIH";
  document.getElementById("genlabel").textContent = "Diperbarui: " + (s.generated || "-");
  document.getElementById("demopill").style.display = s.demo ? "" : "none";
  const box = document.getElementById("statusbox");
  if (SESSION_WARN) showNotice(SESSION_WARN, true); else box.style.display = "none";
  buildFilterUI();
  apply();
  refreshVisible();
  setStep(3);
}

function showNotice(msg, isErr){
  const box = document.getElementById("statusbox");
  box.style.display = ""; box.className = "notice" + (isErr ? " err" : "");
  box.innerHTML = esc(msg);
}

/* static hosting: one payload per survey, no period step */
function pick(id){
  showNotice("Memuat data survei\u2026", false);
  fetch("data/" + encodeURIComponent(id) + ".json")
    .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(s => { try { localStorage.setItem("fasih-survey", id); } catch(e){}
                 document.getElementById("picker").value = id; applySurvey(s); })
    .catch(e => showNotice("Gagal memuat survei " + id + ": " + e.message + " (buka lewat web server, bukan file://)", true));
}

function initStatic(){
  fetch("surveys.json")
    .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(m => {
      const list = m.surveys || [];
      if (!list.length){ showNotice("Tidak ada survei pada manifest.", true); return; }
      const picker = document.getElementById("picker");
      picker.innerHTML = list.map(s =>
        '<option value="' + esc(s.id) + '">' + esc(s.name) + (s.demo ? " (contoh)" : "") +
        (s.hasData ? "" : " \u2014 belum ada data") + "</option>").join("");
      let want = new URLSearchParams(location.search).get("survey");
      if (!want) { try { want = localStorage.getItem("fasih-survey"); } catch(e){} }
      if (!want || !list.some(s => s.id === want)) want = (list.find(s => s.hasData) || list[0]).id;
      picker.value = want;
      setStep(1);
    })
    .catch(e => showNotice("Gagal memuat surveys.json: " + e.message + " (jalankan via web server, mis. `python -m http.server` di folder site)", true));
}

/* on-demand backend flow: step 1 survey (names only) -> step 2 periods ->
   step 3 load cached payload, or scrape that one period on request. */
function initBackend(){
  showNotice("Memuat daftar survei\u2026", false);
  fetch("api/surveys")
    .then(async r => {
      if (r.status === 503){ const j = await r.json().catch(() => ({})); throw new Error(j.detail || "Sesi FASIH belum diatur di server."); }
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(d => {
      const list = d.surveys || [];
      if (!list.length){ showNotice("Tidak ada survei pencacahan pada akun ini.", true); return; }
      const picker = document.getElementById("picker");
      picker.innerHTML = list.map(s => '<option value="' + esc(s.id) + '">' + esc(s.name) + "</option>").join("");
      let want = new URLSearchParams(location.search).get("survey");
      if (!want) { try { want = localStorage.getItem("fasih-survey"); } catch(e){} }
      if (!want || !list.some(s => s.id === want)) want = list[0].id;
      let lastPid = "";
      try { lastPid = localStorage.getItem("fasih-period") || ""; } catch(e){}
      if (lastPid) openSurvey(want, lastPid);
      else { picker.value = want; setStep(1); }
    })
    .catch(e => {
      showNotice("Gagal memuat daftar survei: " + e.message, true);
      if (/sesi/i.test(e.message)) openSess();
    });
}

function openSurvey(sid, wantPid){
  CUR = { sid: sid, pid: "" };
  try { localStorage.setItem("fasih-survey", sid); } catch(e){};
  document.getElementById("picker").value = sid;
  try { history.replaceState(null, "", "?survey=" + encodeURIComponent(sid)); } catch(e){}
  showNotice("Memuat periode\u2026", false);
  fetch("api/survey/" + encodeURIComponent(sid) + "/periods")
    .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(d => {
      const periods = d.periods || [];
      if (!periods.length){
        showNotice("Survei ini tidak memiliki periode yang bisa diambil.", true);
        refreshVisible();
        return;
      }
      const periodSel = document.getElementById("period");
      periodSel.innerHTML = periods.map(p =>
        '<option value="' + esc(p.id) + '"' + (p.cached ? ' data-cached="1"' : "") + ">" +
        esc(p.name || p.id) + (p.cached ? " \u2713" : "") + "</option>").join("");
      const hasWant = !!wantPid && periods.some(p => p.id === wantPid);
      let def = hasWant ? wantPid : "";
      if (!def){ const cached = periods.filter(p => p.cached); def = (cached[cached.length-1] || periods[periods.length-1]).id; }
      periodSel.value = def;
      refreshVisible();
      if (hasWant) openPeriod(wantPid); else setStep(2);
    })
    .catch(e => showNotice("Gagal memuat periode: " + e.message, true));
}

function openPeriod(pid){
  CUR.pid = pid;
  try { localStorage.setItem("fasih-period", pid); } catch(e){};
  const sel = document.getElementById("period");
  const cur = sel.options[sel.selectedIndex];
  const pname = (cur && cur.value === pid) ? cur.textContent.replace(/\s*\u2713$/, "") : pid;
  showNotice("Memuat data\u2026", false);
  fetch("api/survey/" + encodeURIComponent(CUR.sid) + "/period/" + encodeURIComponent(pid) + "/data")
    .then(r => { if (r.status === 404) return null; if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(s => {
      refreshVisible();
      if (!s){
        setRefresh("\u21BB Ambil Data", false);
        applySurvey({ id:pid, name:(META.name||CUR.sid), rows:[], columns:[], statusMap:[] });
        showNotice("Belum ada data untuk periode \u201c" + esc(pname) + "\u201d. Klik tombol \u201cAmbil Data\u201d di kanan atas untuk mengambil dari FASIH.", false);
        return;
      }
      setRefresh(REFRESH_LABEL, false);
      applySurvey(s);
    })
    .catch(e => { refreshVisible(); showNotice("Gagal memuat data: " + e.message, true); });
}

document.querySelectorAll(".tab").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.id === "panel-" + btn.dataset.tab));
  };
});

/* wizard controls */
document.getElementById("toStep2").onclick = () => {
  const sid = document.getElementById("picker").value;
  if (!sid) return;
  if (BACKEND) openSurvey(sid); else pick(sid);
};
document.getElementById("back1").onclick = () => setStep(1);
document.getElementById("toStep3").onclick = () => {
  const pid = document.getElementById("period").value;
  if (pid) openPeriod(pid);
};
document.getElementById("st1").onclick = () => setStep(1);
document.getElementById("st2").onclick = () => { if (BACKEND && document.getElementById("period").options.length) setStep(2); };
document.getElementById("st3").onclick = () => { if (CUR.pid || META.id) setStep(3); };
document.getElementById("head").addEventListener("click", e => {
  const th = e.target.closest("th"); if (!th) return;
  const k = th.dataset.k;
  state.sort = state.sort.key === k ? { key:k, dir:-state.sort.dir } : { key:k, dir:1 };
  renderTable();
});
document.getElementById("prev").onclick = () => { state.page--; renderTable(); };
document.getElementById("next").onclick = () => { state.page++; renderTable(); };
document.getElementById("psize").onchange = e => { state.pageSize = parseInt(e.target.value,10); state.page = 0; renderTable(); };

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

function dlName(){
  const d = new Date();
  const ds = d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0");
  const nm = String(META.name || "fasih").replace(/[^\w]+/g,"-").replace(/^-+|-+$/g,"").toLowerCase().slice(0,60) || "fasih";
  return "dashboard-" + nm + "-" + ds + ".png";
}

const pngBtn = document.getElementById("png");
pngBtn.onclick = async () => {
  if (typeof html2canvas !== "function"){ alert("Pustaka ekspor PNG belum termuat (butuh koneksi internet)."); return; }
  const panel = document.querySelector(".panel.active");
  if (!panel) return;
  const old = pngBtn.textContent;
  pngBtn.disabled = true; pngBtn.textContent = "Menyiapkan\u2026";
  try {
    const bg = getComputedStyle(document.body).backgroundColor;
    const canvas = await html2canvas(panel, { scale: 3, backgroundColor: bg, logging: false, useCORS: true });
    const blob = await new Promise(res => canvas.toBlob(res, "image/png"));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = dlName();
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  } catch(e){ alert("Gagal membuat PNG: " + e.message); }
  finally { pngBtn.disabled = false; pngBtn.textContent = old; }
};

/* Refresh button: only works when served by the Phase 2 backend (server.py).
   Static hosting has no api/*, so detection hides the button. */
let BACKEND = false;
let SESSION_WARN = "";
const refreshBtn = document.getElementById("refresh");
const REFRESH_LABEL = "\u21BB Perbarui";
function refreshVisible(){
  const show = (BACKEND && (CUR.sid || (META.id && !META.demo))) ? "" : "none";
  refreshBtn.style.display = show;
}
function setRefresh(t, off){ refreshBtn.classList.toggle("busy", !!off); refreshBtn.textContent = t; refreshBtn.disabled = !!off; }
const rfov = document.getElementById("rfov");
const rfstepsEl = document.getElementById("rfsteps");
const rfdetailEl = document.getElementById("rfdetail");
function showOv(v){ rfov.classList.toggle("on", !!v); }
function renderSteps(st){
  const steps = (st && st.steps) || [];
  rfstepsEl.innerHTML = steps.map(s => {
    const mark = s.done ? "\u2713" : (s.current ? "\u25CF" : "\u25CB");
    return '<li class="' + (s.done ? "done" : (s.current ? "cur" : "")) + '"><span class="rfdot">' + mark + '</span><span>' + esc(s.label) + '</span></li>';
  }).join("");
  const d = (st && st.detail) || "";
  rfdetailEl.textContent = d;
  rfdetailEl.style.display = d ? "" : "none";
}
refreshBtn.onclick = async () => {
  const sid = CUR.sid, pid = CUR.pid;
  if (!sid || !pid) return;
  const q = "api/survey/" + encodeURIComponent(sid) + "/period/" + encodeURIComponent(pid);
  setRefresh("Mengantre\u2026", true);
  showOv(true); renderSteps({ detail: "Mengirim permintaan ke server\u2026" });
  try {
    const r = await fetch(q + "/scrape", { method:"POST" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    for (let i = 0; i < 2400; i++){
      await new Promise(res => setTimeout(res, 3000));
      const st = await (await fetch(q + "/status")).json();
      if (st.state === "queued"){ setRefresh("Menunggu\u2026", true); renderSteps({ steps:[{label:"Menunggu antrean server\u2026", current:true}] }); }
      else if (st.state === "running"){ setRefresh("Mengambil\u2026", true); renderSteps(st); }
      else if (st.state === "done"){ setRefresh(REFRESH_LABEL, false); showOv(false); openSurvey(sid, pid); return; }
      else if (st.state === "error"){ setRefresh(REFRESH_LABEL, false); showOv(false); showNotice("Gagal mengambil data: " + (st.error || "?"), true); return; }
    }
    setRefresh(REFRESH_LABEL, false); showOv(false);
    showNotice("Pengambilan masih berjalan di server; muat ulang halaman nanti.", false);
  } catch(e){
    setRefresh(REFRESH_LABEL, false); showOv(false);
    showNotice("Gagal mengambil data: " + e.message, true);
  }
};
/* Session modal: paste a FASIH Cookie header so the server can refresh. */
const sessBtn = document.getElementById("setsess");
const sessModal = document.getElementById("sessmodal");
const sessInput = document.getElementById("sessinput");
const sessMsg = document.getElementById("sessmsg");
function openSess(){ sessMsg.textContent = ""; sessMsg.className = "modalmsg"; sessModal.style.display = "flex"; sessInput.focus(); }
function closeSess(){ sessModal.style.display = "none"; }
function sessVisible(){ sessBtn.style.display = BACKEND ? "" : "none"; }
sessBtn.onclick = openSess;
document.getElementById("sesscancel").onclick = closeSess;
sessModal.onclick = e => { if (e.target === sessModal) closeSess(); };
document.addEventListener("keydown", e => { if (e.key === "Escape" && sessModal.style.display === "flex") closeSess(); });
document.getElementById("sesssave").onclick = async () => {
  const v = sessInput.value.trim();
  const btn = document.getElementById("sesssave");
  if (!v){ sessMsg.className = "modalmsg err"; sessMsg.textContent = "Tempel header Cookie dulu."; return; }
  btn.disabled = true; sessMsg.className = "modalmsg"; sessMsg.textContent = "Menyimpan & memeriksa\u2026";
  try {
    const r = await fetch("api/session", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ cookie_header: v }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || j.error || ("HTTP " + r.status));
    if (j.valid){
      SESSION_WARN = ""; setRefresh(REFRESH_LABEL, false);
      document.getElementById("statusbox").style.display = "none";
      sessMsg.className = "modalmsg ok"; sessMsg.textContent = "Sesi tersimpan & valid. Memuat daftar survei\u2026";
      sessInput.value = "";
      setTimeout(() => { closeSess(); initBackend(); }, 900);
    } else {
      sessMsg.className = "modalmsg err"; sessMsg.textContent = "Sesi tersimpan tapi belum valid/kedaluwarsa. Salin ulang header Cookie dari FASIH.";
    }
  } catch(e){
    sessMsg.className = "modalmsg err"; sessMsg.textContent = "Gagal menyimpan: " + e.message;
  } finally { btn.disabled = false; }
};
const cmModal = document.getElementById("chartmodal");
const cmClose = document.getElementById("cmclose");
cmClose.onclick = () => cmModal.style.display = "none";
cmModal.onclick = (e) => { if (e.target === cmModal) cmModal.style.display = "none"; };
(async () => {
  let me = null;
  try { const r = await fetch("api/me"); if (r.ok){ me = await r.json(); BACKEND = true; } else BACKEND = false; } catch(e){ BACKEND = false; }
  refreshVisible(); sessVisible();
  if (me && me.auth && me.auth !== "open" && me.user){
    const chip = document.getElementById("userchip");
    chip.textContent = "Masuk: " + me.user;
    chip.style.display = "";
    document.getElementById("logout").style.display = "";
  }
  if (BACKEND) {
    try {
      const s = await (await fetch("api/session")).json();
      if (!s.configured){
        SESSION_WARN = "Sesi FASIH belum diatur di server. Klik \u201cAtur Sesi\u201d untuk menempel sesi dari browser sebelum daftar survei bisa dimuat.";
        showNotice(SESSION_WARN, true);
        openSess();
      }
    } catch(e){}
    initBackend();
  } else {
    initStatic();
  }
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build_site()




