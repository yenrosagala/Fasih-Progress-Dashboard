"""FASIH progress dashboard on Streamlit Community Cloud.

Streamlit owns the FASIH session (a secret), scrapes one survey period on demand,
and serves the existing static dashboard from streamlit_app/static/site/ so the SPA
resolves its JSON with plain relative URLs -- no backend, no CORS, no shim.

Login is the same knobs as server.py: LOGIN_USER + LOGIN_PASSWORD (process env, or
st.secrets on Cloud). The gate code is kept but currently skipped (SHOW_LOGIN=False),
so the form never shows; flip the constant to gate the app again. The FASIH cookie is
pasted at the top of the main screen, before picking a survey/period; it lands in
inputs/manual_session.json, which beats the secret until the container restarts.

Cookie, Survei and Periode live on the main screen directly above the dashboard, so
the Streamlit sidebar is hidden (it holds nothing anymore -- one line of CSS).

ponytail: the AI summary and WhatsApp button are local-only -- both need server.py.
The refresh button is not hidden: it opens a popup in the dashboard header next to
the theme toggle, which names the control bar's selection (ui_state.json) and clicks
that fetch button in the parent document, because an iframe cannot call Python and
no component bridge is registered. Upgrade path: run server.py on a reachable origin
and embed that URL, or bridge via a declared component.
Everything else -- charts, filters, PNG/PDF export, copy-summary -- is the same code
as the Docker build. The gate only hides the UI: /app/static/... is served by
Streamlit unauthenticated, so keep a Cloud app with PII private.
"""

import asyncio
import hmac
import json
import os
import shutil
import sys
import time
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
SITE_SRC = ROOT / "outputs" / "site"
SITE_DST = APP_DIR / "static" / "site"
SITE_URL = "/app/static/site/"  # Streamlit's app-static route; see .streamlit/config.toml

if Path.cwd() != ROOT:
    os.chdir(ROOT)  # repo modules read inputs/ and write outputs/ by relative path
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_site  # noqa: E402
import data_tab  # noqa: E402
from api_client import get_requests, post_requests  # noqa: E402
from config import (  # noqa: E402
    BASE_HEADERS,
    payload_survey,
    survey_datatable_url,
    surveys_base_url,
)
from importer import load_session, save_manual_session, session_probe  # noqa: E402

MANUAL_SESSION = ROOT / "inputs" / "manual_session.json"

# ponytail: login form kept but not shown for now; flip to True to gate the app again
# (the static route stays unauthenticated either way -- see the docstring).
SHOW_LOGIN = False


def _secret(name, default=""):
    """st.secrets[name]; a missing secrets.toml must never break the app."""
    try:
        return str(st.secrets[name]).strip() or default
    except Exception:
        return default


def _login_cfg():
    user = (os.environ.get("LOGIN_USER") or _secret("LOGIN_USER")).strip()
    pwd = (os.environ.get("LOGIN_PASSWORD") or _secret("LOGIN_PASSWORD")).strip()
    return user, pwd


def _gate():
    """Login like server.py: both creds set = form, neither = open (AUTH_DISABLED)."""
    user, pwd = _login_cfg()
    if not (user and pwd):
        return True
    if st.session_state.get("authed"):
        return True
    st.title("Masuk")
    with st.form("login"):
        u = st.text_input("Pengguna")
        p = st.text_input("Kata sandi", type="password")
        submitted = st.form_submit_button("Masuk")
    if submitted:
        if hmac.compare_digest(u.encode("utf-8"), user.encode("utf-8")) and hmac.compare_digest(
            p.encode("utf-8"), pwd.encode("utf-8")
        ):
            st.session_state["authed"] = True
            st.rerun()
        st.error("Pengguna atau kata sandi salah.")
    return False


def _session_blob():
    """A pasted cookie (inputs/manual_session.json) beats FASIH_SESSION, so a paste
    survives reloads; deleting the file falls back to the secret."""
    if MANUAL_SESSION.exists():
        os.environ.pop("FASIH_SESSION", None)
        return ""
    if os.environ.get("FASIH_SESSION"):
        return os.environ["FASIH_SESSION"]
    blob = _secret("FASIH_SESSION")
    if blob:
        os.environ["FASIH_SESSION"] = blob
    return os.environ.get("FASIH_SESSION", "")


def _headers_cookies():
    cookies, csrf = load_session()
    if not (cookies and csrf):
        raise RuntimeError(
            'Sesi FASIH belum diatur. Isi rahasia FASIH_SESSION '
            '(JSON {"cookie_header": "..."}), lalu muat ulang.'
        )
    return {**BASE_HEADERS, "X-XSRF-TOKEN": csrf}, cookies


@st.cache_data(ttl=60, show_spinner=False)
def _session_state(blob):
    """(ok, reason) for the current session; reason is shown when it is invalid."""
    cookies, csrf = load_session()
    if not (cookies and csrf):
        return False, ""
    return session_probe(cookies, csrf)


@st.cache_data(ttl=600, show_spinner=False)
def _surveys(blob):
    headers, cookies = _headers_cookies()
    data = asyncio.run(post_requests(survey_datatable_url, headers, cookies, payload_survey)).json()
    return [
        {"id": s.get("id"), "name": s.get("name")}
        for s in (data.get("data", {}).get("content") or [])
        if s.get("id") and s.get("name")
    ]


@st.cache_data(ttl=600, show_spinner=False)
def _periods(blob, survey_id):
    headers, cookies = _headers_cookies()
    return asyncio.run(data_tab._survey_periods(survey_id, headers, cookies))


def _scrape(survey_id, period, progress):
    """Scrape one period and write its payload + manifest under outputs/site/."""
    headers, cookies = _headers_cookies()
    meta = asyncio.run(get_requests(surveys_base_url + survey_id, headers, cookies)).json().get("data") or {}
    gid = meta.get("regionGroupId")
    if not isinstance(gid, str):
        raise RuntimeError(f"regionGroupId tidak ditemukan untuk survei {survey_id}")
    name = meta.get("name", "")
    pid = period["id"]
    df = asyncio.run(
        data_tab.collect_period(
            name, pid, gid, headers, cookies,
            period_name=period.get("name") or "", progress=progress,
        )
    )
    rows = df.to_dict(orient="records") if not df.empty else []
    build_site.write_payload(
        pid, name, "pencacahan", rows, time.strftime("%Y%m%d_%H%M%S"),
        {"start": period.get("startDate") or "", "end": period.get("endDate") or ""},
    )
    build_site.rebuild_manifest()
    return name, len(rows)


def _publish():
    """Mirror outputs/site -> static/site; skipped unless the manifest changed."""
    man_src, man_dst = SITE_SRC / "surveys.json", SITE_DST / "surveys.json"
    if not man_src.exists():
        # Fresh install (or all payloads removed): the SPA 404s on a missing
        # manifest, so write the empty one; rebuild_manifest() needs no data.
        build_site.rebuild_manifest()
    if (
        SITE_DST.exists() and man_dst.exists() and man_src.exists()
        and man_src.stat().st_mtime <= man_dst.stat().st_mtime
    ):
        return
    if SITE_DST.exists():
        shutil.rmtree(SITE_DST)
    shutil.copytree(SITE_SRC, SITE_DST)


def _embed():
    html = (SITE_DST / "index.html").read_text(encoding="utf-8")
    # A srcdoc document has no URL of its own, so <base> re-points the SPA's
    # relative fetch("surveys.json") / fetch("data/<id>.json") at the static route.
    html = html.replace("<head>", f'<head><base href="{SITE_URL}">', 1)
    # Default height='content' lets the iframe grow with the SPA (its body is
    # content-height, not 100vh); 'stretch' pinned it to a 150px strip.
    st.iframe(html, alt="Dashboard Progres FASIH")


def _run_scrape(survey_id, period):
    with st.status("Mengambil data dari FASIH\u2026", expanded=True) as box:
        bar = st.progress(0.0, text="menyiapkan\u2026")

        def _prog(done, total):
            bar.progress(done / total if total else 0.0, text=f"{done}/{total} wilayah")

        try:
            name, n = _scrape(survey_id, period, _prog)
        except Exception as e:
            box.update(label="Gagal mengambil data", state="error")
            st.error(str(e))
            return
        box.update(label=f"{n:,} baris \u00b7 {name}", state="complete")
    _publish()
    st.rerun()


def _cookie_panel(ok):
    """Paste-the-cookie flow (the Docker build's session dialog), above the pickers."""
    with st.expander(
        "Sesi FASIH \u2713 aktif" if ok else "Sesi FASIH \u2014 tempel cookie",
        expanded=not ok,
    ):
        st.caption(
            "1. Buka FASIH di browser \u2192 tekan F12 \u2192 tab Network \u2192 klik request "
            "apa pun \u2192 tab Headers \u2192 baris Cookie \u2192 salin SELURUH nilainya.\n"
            "2. Tempel di kolom bawah, lalu Simpan. Disimpan ke "
            f"{MANUAL_SESSION.relative_to(ROOT).as_posix()} \u2014 hapus file itu untuk "
            "kembali ke rahasia FASIH_SESSION.\n"
            "3. Streamlit Cloud: FASIH_SESSION = {\"cookie_header\": \"...\"} di "
            "Settings \u2192 Secrets; LOGIN_USER + LOGIN_PASSWORD juga bisa di situ."
        )
        raw = st.text_area(
            "Cookie header FASIH",
            key="cookie_in",
            height=110,
            placeholder="XSRF-TOKEN=...; fasih_session=...",
        )
        if st.button("Simpan cookie"):
            try:
                save_manual_session(raw)
            except ValueError as e:
                st.error(f"Cookie tidak tersimpan: {e}")
                return
            st.cache_data.clear()
            st.rerun()


def _write_ui_state(label, saved):
    """Publish the control bar's selection for the embedded SPA's refresh popup.

    The SPA has its own picker, so the menu names what Python will actually scrape
    instead of guessing. Best-effort: a missing or stale file only costs a generic
    menu label, never a crash.
    """
    try:
        SITE_DST.mkdir(parents=True, exist_ok=True)
        (SITE_DST / "ui_state.json").write_text(
            json.dumps({"label": label, "saved": bool(saved)}), encoding="utf-8"
        )
    except OSError:
        pass


def _controls(blob):
    """Survei/Periode pickers + fetch button in a single filter row above the
    dashboard (mirrors the SPA's .filters bar); nothing is left for the sidebar."""
    try:
        _headers_cookies()  # pasted file, else FASIH_SESSION secret (local runs)
        has_session = True
    except RuntimeError:
        has_session = False
    ok, reason = _session_state(blob) if has_session else (False, "")
    _cookie_panel(ok)
    if not has_session:
        st.warning(
            "Sesi FASIH belum diatur \u2014 tempel cookie di panel di atas, "
            "lalu muat ulang halaman."
        )
        return
    if not ok:
        st.error(
            f"Sesi FASIH tidak valid atau sudah kedaluwarsa "
            f"(status: {reason or 'n/a'}) \u2014 tempel cookie baru di panel di atas, "
            "lalu muat ulang halaman."
        )
        return
    try:
        surveys = _surveys(blob)
    except Exception as e:
        st.error(f"Gagal memuat daftar survei: {e}")
        return
    if not surveys:
        st.warning("Tidak ada survei pada akun ini.")
        return

    def _label(p):
        start = (p.get("startDate") or "")[:10]
        end = (p.get("endDate") or "")[:10]
        return f"{p.get('name') or p['id']} \u00b7 {start}\u2013{end}"

    with st.container(border=True):
        pick_a, pick_b, action = st.columns(
            [2, 2.4, 1.4], vertical_alignment="bottom"
        )
        with pick_a:
            i = st.selectbox("Survei", range(len(surveys)), format_func=lambda k: surveys[k]["name"])
        survey_id = surveys[i]["id"]
        try:
            periods = _periods(blob, survey_id)
        except Exception as e:
            st.error(f"Gagal memuat periode: {e}")
            return
        if not periods:
            st.warning("Survei ini tidak punya periode.")
            return
        with pick_b:
            j = st.selectbox("Periode", range(len(periods)), format_func=lambda k: _label(periods[k]))
        period = periods[j]
        payload = SITE_SRC / "data" / f"{period['id']}.json"
        saved = payload.exists()
        _write_ui_state(f"{surveys[i]['name']} \u00b7 {_label(period)}", saved)
        with action:
            if st.button(
                "Muat ulang data periode ini" if saved else "Ambil data periode ini",
                type="primary",
                use_container_width=True,
            ):
                _run_scrape(survey_id, period)
    if saved:
        when = time.strftime("%d/%m %H:%M", time.localtime(payload.stat().st_mtime))
        st.caption(f"Data tersimpan \u00b7 diambil {when} \u00b7 tombol \u21bb di dashboard memakai pilihan ini.")
    else:
        st.caption("Data periode ini belum diambil \u00b7 klik tombol di sebelahnya, atau tombol \u21bb di dashboard.")


def main():
    st.set_page_config(page_title="Dashboard Progres FASIH", layout="wide")
    # Streamlit has no API to drop the sidebar and every control now lives on the
    # main screen, so hide the empty rail instead of leaving a blank panel to open.
    # The same block repaints Streamlit's widgets with the SPA's tokens (build_site
    # _SHELL :root / .pick / .refgo / .card) so the control bar and the embedded
    # dashboard read as one surface.
    st.markdown(
        """<style>
[data-testid='stSidebar']{display:none}
[data-testid='stApp'],[data-testid='stAppViewContainer'],
[data-testid='stMain']{background:#0f172a}
/* SPA body uses the OS UI font (build_site.py body{font:14px/1.5 system-ui}),
   Streamlit defaults to "Source Sans" - force the system stack to match.
   Headings are scoped by Streamlit with a 2-id selector, so they need the
   !important to outrank it. */
:root,[data-testid='stApp']{--font:system-ui,"Segoe UI",Roboto,sans-serif}
[data-testid='stApp'],[data-testid='stApp'] *{font-family:system-ui,"Segoe UI",Roboto,sans-serif}
[data-testid='stApp'] h1,[data-testid='stApp'] h2,[data-testid='stApp'] h3,
[data-testid='stApp'] h4,[data-testid='stApp'] h5,[data-testid='stApp'] h6,
[data-testid='stApp'] .stMarkdown p,[data-testid='stApp'] [data-testid='stWidgetLabel'] p{
font-family:system-ui,"Segoe UI",Roboto,sans-serif !important}
[data-testid='stApp'] code,[data-testid='stApp'] pre,[data-testid='stApp'] kbd{
font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace !important}
/* The * override above also hits Streamlit's Material icon spans, turning
   ligatures like "keyboard_arrow_right" into literal text - restore the font. */
[data-testid='stApp'] [data-testid='stIconMaterial']{
font-family:"Material Symbols Rounded" !important}
/* Drop the 60px empty header rail (the seam above the controls). */
[data-testid='stHeader']{display:none}
[data-testid='stMainBlockContainer'],.block-container{padding:.75rem 1.25rem 4rem;max-width:100%}
[data-testid='stAppViewContainer']{font-size:14px}
[data-testid='stVerticalBlock']{gap:.6rem}
[data-testid='stHeading'] h1{font-size:18px;padding:0;margin:0 0 .4rem}
[data-testid='stWidgetLabel'] p{font-size:12px;color:#94a3b8}
[data-testid='stCaptionContainer']{color:#94a3b8;font-size:12px}
[data-testid='stExpander']{background:#1e293b;border:1px solid #334155;border-radius:10px}
[data-testid='stExpander'] summary{font-size:13px}
[data-testid='stVerticalBlockBorderWrapper']{background:#1e293b;border-color:#334155;border-radius:10px}
[data-baseweb='select'],
[data-baseweb='input'],
[data-baseweb='textarea']{background:#1e293b;border-color:#334155;border-radius:8px}
[data-baseweb='select']:hover,
[data-baseweb='input']:hover,
[data-baseweb='textarea']:hover{border-color:#38bdf8}
[data-testid='stButton'] button{border-radius:8px;padding:.6rem 1rem;font-size:13px;
transition:border-color .15s ease,color .15s ease,background .15s ease}
[data-testid='stButton'] button:not([kind='primary']){background:#1e293b;border-color:#334155;color:#e2e8f0}
[data-testid='stButton'] button[kind='primary']{background:#38bdf8;color:#04263a;border:0;font-weight:700}
[data-testid='stButton'] button[kind='primary']:hover{filter:brightness(1.08)}
</style>""",
        unsafe_allow_html=True,
    )
    if SHOW_LOGIN and not _gate():
        return  # no publish, no controls, no iframe until logged in
    blob = _session_blob()
    _publish()
    _controls(blob)
    _embed()


main()
