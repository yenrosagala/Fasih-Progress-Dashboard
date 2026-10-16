"""Phase 2 backend: serve the multi-survey site + on-demand FASIH refresh.

Run:
    python server.py                      # http://127.0.0.1:8080
    python -m uvicorn server:app --port 8080

Auth (Google Workspace SSO) engages automatically when GOOGLE_CLIENT_ID and
GOOGLE_CLIENT_SECRET are set; otherwise the app runs in open dev mode. Set
AUTH_DISABLED=1 to force open mode even with credentials present.

Env:
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET   OAuth creds (enables SSO)
    GOOGLE_HD                                allowed Workspace domain, e.g. bps.go.id
    PUBLIC_BASE_URL                          external base URL for the OAuth redirect
    SESSION_SECRET                           cookie signing key (random per boot if unset)
    SESSION_TTL                              cookie lifetime seconds (default 8h)
    HOST, PORT                               bind address (default 127.0.0.1:8080)
"""
import asyncio
import hashlib
import hmac
import os
import secrets
import time
import urllib.parse
from contextlib import asynccontextmanager

import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import build_site
import data_tab
from api_client import get_requests, post_requests
from config import (
    BASE_HEADERS,
    payload_survey,
    survey_datatable_url,
    survey_periods_url,
    surveys_base_url,
)
from importer import load_session, save_manual_session, session_valid

SITE_DIR = build_site.SITE_DIR
SURVEY_CSV = "outputs/csv/survey_collection_deadline_adjusted.csv"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

SESSION_COOKIE = "fasih_session"
SESSION_TTL = int(os.getenv("SESSION_TTL", str(8 * 3600)))
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_hex(32)


def _auth_disabled():
    if os.getenv("AUTH_DISABLED") == "1":
        return True
    return not (os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def _base_url(request):
    return os.getenv("PUBLIC_BASE_URL") or f"{request.url.scheme}://{request.url.netloc}"


def _secure_cookie(request):
    return _base_url(request).startswith("https")


def _sign(email):
    exp = int(time.time()) + SESSION_TTL
    msg = f"{email}|{exp}"
    sig = hmac.new(SESSION_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}|{sig}"


def _verify(val):
    if not val:
        return None
    try:
        email, exp, sig = val.rsplit("|", 2)
    except ValueError:
        return None
    good = hmac.new(SESSION_SECRET.encode(), f"{email}|{exp}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good) or int(exp) < time.time():
        return None
    return email


def current_user(request):
    if _auth_disabled():
        return os.getenv("DEV_USER", "dev@local")
    return _verify(request.cookies.get(SESSION_COOKIE))


# --------------------------------------------------------------------------
# refresh jobs: single serialized worker (FASIH rate-limits per account, so
# concurrent scrapes would just trip the limiter). In-memory state only.
# ponytail: state lost on restart; the regenerated data/<id>.json is durable.
# --------------------------------------------------------------------------
_jobs = {}
_queue = None


REFRESH_STEPS = [
    "Memvalidasi konfigurasi survei",
    "Membaca data sampel dasar",
    "Memuat & memeriksa sesi FASIH",
    "Mengambil data dari FASIH",
    "Menyimpan hasil",
    "Memperbarui daftar survei",
]

# A single on-demand period scrape is shorter than a full survey refresh.
PERIOD_STEPS = [
    "Memuat & memeriksa sesi FASIH",
    "Mengambil daftar sampel dari FASIH",
    "Menyimpan hasil",
]


def _stage(key, idx, detail=""):
    job = _jobs.setdefault(key, {})
    labels = job.get("steplist") or REFRESH_STEPS
    job["steps"] = [{"label": lbl, "done": i < idx, "current": i == idx}
                    for i, lbl in enumerate(labels)]
    job["detail"] = detail or (labels[idx] if idx < len(labels) else "")


async def _worker():
    while True:
        key = await _queue.get()
        job = _jobs.setdefault(key, {})
        job.update(state="running", started=time.time())
        try:
            if job.get("kind") == "period":
                n, generated = await _refresh_period(job["sid"], job["pid"], key)
            else:
                n, generated = await _refresh_survey(key)
            job.update(state="done", rows=n, generated=generated, finished=time.time())
        except Exception as e:
            job.update(state="error", error=f"{type(e).__name__}: {e}", finished=time.time())
        finally:
            _queue.task_done()


@asynccontextmanager
async def lifespan(app):
    global _queue
    _queue = asyncio.Queue()  # fresh per startup, bound to this loop
    task = asyncio.create_task(_worker())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="FASIH Analytics", lifespan=lifespan)


async def _refresh_survey(sid):
    _stage(sid, 0)
    cfg = build_site._load_cfg()
    entry = next((s for s in cfg if s.get("surveyPeriodId") == sid), None)
    if not entry:
        raise RuntimeError(f"survey {sid} not in survey_config.json")
    name = entry.get("name", "")

    _stage(sid, 1)
    if not os.path.exists(SURVEY_CSV):
        raise RuntimeError(f"{SURVEY_CSV} not found; run main.py once to produce it")
    df = pd.read_csv(SURVEY_CSV)
    row = df[df["survey_period_id"] == sid]
    if row.empty:
        raise RuntimeError(f"survey {sid} not in {SURVEY_CSV}; run main.py once")

    _stage(sid, 2)
    cookies, csrf = load_session()
    if not (cookies and csrf):
        raise RuntimeError("Sesi FASIH belum diatur di server. Isi inputs/manual_session.json atau variabel FASIH_SESSION, lalu mulai ulang server.")
    if not session_valid(cookies, csrf):
        raise RuntimeError("Sesi FASIH sudah kedaluwarsa. Perbarui inputs/manual_session.json atau FASIH_SESSION, lalu coba lagi.")

    headers = {**BASE_HEADERS, "X-XSRF-TOKEN": csrf}

    def _prog(done, total):
        _stage(sid, 3, f"{done}/{total} wilayah")

    _stage(sid, 3, "menyiapkan\u2026")
    data_df = await data_tab.collect_data_tab(row, [name], headers, cookies, progress=_prog)
    rows = data_df.to_dict(orient="records") if not data_df.empty else []

    _stage(sid, 4, f"{len(rows)} baris")
    generated = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    period = {"start": entry.get("surveyPeriodStartDate", ""), "end": entry.get("surveyPeriodEndDate", "")}
    build_site.write_payload(sid, name, entry.get("type", ""), rows, generated, period)
    _stage(sid, 5)
    build_site.rebuild_manifest()
    return len(rows), generated


def _session_headers():
    """(headers, cookies) for FASIH calls, or raise a user-facing error."""
    cookies, csrf = load_session()
    if not (cookies and csrf):
        raise RuntimeError("Sesi FASIH belum diatur di server. Isi inputs/manual_session.json atau variabel FASIH_SESSION, lalu mulai ulang server.")
    if not session_valid(cookies, csrf):
        raise RuntimeError("Sesi FASIH sudah kedaluwarsa. Perbarui inputs/manual_session.json atau FASIH_SESSION, lalu coba lagi.")
    return {**BASE_HEADERS, "X-XSRF-TOKEN": csrf}, cookies


async def _refresh_period(sid, pid, key):
    """On-demand scrape of exactly one survey period; caches data/<pid>.json."""
    _stage(key, 0)
    headers, cookies = _session_headers()

    meta = (await get_requests(surveys_base_url + sid, headers, cookies)).json().get("data") or {}
    gid = meta.get("regionGroupId")
    if not isinstance(gid, str):
        raise RuntimeError(f"regionGroupId tidak ditemukan untuk survei {sid}")
    name = meta.get("name", "")

    pname = ""
    for p in await data_tab._survey_periods(sid, headers, cookies):
        if p.get("id") == pid:
            pname = p.get("name") or ""
            break

    _stage(key, 1, "menyiapkan\u2026")

    def _prog(done, total):
        _stage(key, 1, f"{done}/{total} wilayah")

    df = await data_tab.collect_period(name, pid, gid, headers, cookies, period_name=pname, progress=_prog)
    rows = df.to_dict(orient="records") if not df.empty else []

    _stage(key, 2, f"{len(rows)} baris")
    generated = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    build_site.write_payload(pid, name, "pencacahan", rows, generated, {"start": "", "end": ""})
    build_site.rebuild_manifest()
    _stage(key, len(PERIOD_STEPS), f"{len(rows)} baris")
    return len(rows), generated


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/api/me")
async def me(request: Request):
    return {"email": current_user(request)}


@app.get("/api/session")
async def api_session():
    cookies, csrf = load_session()
    return {"configured": bool(cookies and csrf)}


@app.post("/api/session")
async def set_session(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    header = (body or {}).get("cookie_header", "")
    try:
        cookies, csrf = save_manual_session(header)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"configured": True, "valid": bool(session_valid(cookies, csrf))}


@app.post("/api/survey/{sid}/refresh")
async def refresh(sid: str):
    if sid == build_site._DEMO_ID:
        raise HTTPException(400, "demo survey cannot be refreshed")
    if sid not in {s.get("surveyPeriodId") for s in build_site._load_cfg()}:
        raise HTTPException(404, "unknown survey")
    cur = _jobs.get(sid, {}).get("state")
    if cur in ("queued", "running"):
        return {"status": cur}
    _jobs[sid] = {"state": "queued", "queued": time.time()}
    await _queue.put(sid)
    return {"status": "queued"}


@app.get("/api/survey/{sid}/status")
async def status(sid: str):
    return _jobs.get(sid, {"state": "idle"})


# --------------------------------------------------------------------------
# on-demand flow: list surveys -> pick one -> list its periods -> pick one ->
# scrape only that period. The survey list is names-only (no sample data), so
# opening the page is cheap; real data is fetched per chosen period.
# --------------------------------------------------------------------------
@app.get("/api/surveys")
async def api_surveys():
    headers, cookies = _session_headers()
    resp = await post_requests(survey_datatable_url, headers, cookies, payload_survey)
    content = resp.json().get("data", {}).get("content", [])
    surveys = [{"id": s.get("id"), "name": s.get("name")} for s in content if s.get("id") and s.get("name")]
    return {"surveys": surveys}


@app.get("/api/survey/{sid}/periods")
async def api_periods(sid: str):
    headers, cookies = _session_headers()
    periods = await data_tab._survey_periods(sid, headers, cookies)
    out = []
    for p in periods:
        pid = p.get("id")
        out.append({
            "id": pid, "name": p.get("name") or "",
            "startDate": p.get("startDate") or "", "endDate": p.get("endDate") or "",
            "cached": os.path.exists(os.path.join(SITE_DIR, "data", f"{pid}.json")),
        })
    return {"periods": out}


@app.get("/api/survey/{sid}/period/{pid}/data")
async def api_period_data(sid: str, pid: str):
    path = os.path.join(SITE_DIR, "data", f"{pid}.json")
    if not os.path.exists(path):
        raise HTTPException(404, "no cached data for this period")
    return FileResponse(path, media_type="application/json")


@app.post("/api/survey/{sid}/period/{pid}/scrape")
async def scrape_period(sid: str, pid: str):
    key = f"{sid}:{pid}"
    cur = _jobs.get(key, {}).get("state")
    if cur in ("queued", "running"):
        return {"status": cur, "key": key}
    _jobs[key] = {"kind": "period", "sid": sid, "pid": pid, "steplist": PERIOD_STEPS,
                  "state": "queued", "queued": time.time()}
    await _queue.put(key)
    return {"status": "queued", "key": key}


@app.get("/api/survey/{sid}/period/{pid}/status")
async def scrape_period_status(sid: str, pid: str):
    return _jobs.get(f"{sid}:{pid}", {"state": "idle"})


@app.get("/auth/login")
async def login(request: Request):
    if _auth_disabled():
        return RedirectResponse("/")
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": _base_url(request) + "/auth/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    if os.getenv("GOOGLE_HD"):
        params["hd"] = os.environ["GOOGLE_HD"]
    resp = RedirectResponse(GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params))
    resp.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=600,
                    secure=_secure_cookie(request))
    return resp


@app.get("/auth/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    if _auth_disabled():
        return RedirectResponse("/")
    if not code or state != request.cookies.get("oauth_state"):
        return PlainTextResponse("invalid oauth state", status_code=400)
    async with httpx.AsyncClient(timeout=30) as c:
        tok = await c.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": _base_url(request) + "/auth/callback",
            "grant_type": "authorization_code",
        })
        tok.raise_for_status()
        ui = await c.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
        ui.raise_for_status()
        info = ui.json()
    email = info.get("email", "")
    hd = os.getenv("GOOGLE_HD")
    if hd and info.get("hd") != hd:
        return PlainTextResponse(f"{email} is not in the allowed domain {hd}", status_code=403)
    resp = RedirectResponse("/")
    resp.set_cookie(SESSION_COOKIE, _sign(email), httponly=True, samesite="lax",
                    max_age=SESSION_TTL, secure=_secure_cookie(request))
    resp.delete_cookie("oauth_state")
    return resp


@app.get("/auth/logout")
async def logout():
    resp = RedirectResponse("/")
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    path = request.url.path
    if _auth_disabled() or path.startswith("/auth/") or path == "/healthz":
        return await call_next(request)
    if not current_user(request):
        if path.startswith("/api/"):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return RedirectResponse("/auth/login")
    return await call_next(request)


os.makedirs(SITE_DIR, exist_ok=True)
app.mount("/", StaticFiles(directory=SITE_DIR, html=True), name="site")


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST") or ("0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
    uvicorn.run(app, host=host, port=int(os.getenv("PORT", "8080")))
