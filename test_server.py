"""Self-check for server.py: cookie signing, manifest rebuild, job/API flow.

No network: the scraper is stubbed, so nothing touches FASIH. Run: python test_server.py
"""
import hashlib
import hmac
import json
import os
import time

os.environ["AUTH_DISABLED"] = "1"

import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def test_cookie():
    v = server._sign("a@b.co")
    assert server._verify(v) == "a@b.co"
    assert server._verify(v + "x") is None, "tampered signature must be rejected"
    assert server._verify("garbage") is None
    assert server._verify(None) is None
    exp = int(time.time()) - 10
    msg = f"a@b.co|{exp}"
    sig = hmac.new(server.SESSION_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
    assert server._verify(f"{msg}|{sig}") is None, "expired token must be rejected"
    print("cookie: ok")


def test_manifest():
    items = server.build_site.rebuild_manifest()
    assert isinstance(items, list) and items, "manifest should list payloads"
    assert server.build_site._DEMO_ID in {i["id"] for i in items}, "demo payload missing"
    assert items[-1]["demo"] is True, "demo should sort last"
    assert all("rows" in i and "hasData" in i for i in items)
    print("manifest:", [(i["id"][:8], i["rows"]) for i in items])


def test_api():
    import asyncio

    calls = []

    async def stub(sid):
        await asyncio.sleep(0.05)
        calls.append(sid)
        return 7, "20260101_120000"

    server._refresh_survey = stub
    with TestClient(server.app) as c:
        assert c.get("/healthz").json() == {"ok": True}
        assert c.get("/api/me").json()["email"]
        assert c.post("/api/survey/unknown-id/refresh").status_code == 404
        assert c.post(f"/api/survey/{server.build_site._DEMO_ID}/refresh").status_code == 400

        sid = next(s["surveyPeriodId"] for s in server.build_site._load_cfg() if s.get("surveyPeriodId"))
        assert c.get(f"/api/survey/{sid}/status").json()["state"] == "idle"
        assert c.post(f"/api/survey/{sid}/refresh").json()["status"] == "queued"

        st = {}
        for _ in range(100):
            st = c.get(f"/api/survey/{sid}/status").json()
            if st["state"] in ("done", "error"):
                break
            time.sleep(0.05)
        assert st["state"] == "done", st
        assert st["rows"] == 7 and st["generated"] == "20260101_120000"
        assert calls == [sid], "worker should run exactly the queued job"
    print("api: ok")


def test_env_session():
    import importer

    os.environ["FASIH_SESSION"] = json.dumps({"cookies": {"a": "1"}, "csrf_token": "tok"})
    assert importer.load_session() == ({"a": "1"}, "tok"), "env session should win"

    os.environ["FASIH_SESSION"] = json.dumps({"cookie_header": "x-xsrf-token=abc; other=1"})
    cookies, csrf = importer.load_session()
    assert cookies.get("other") == "1" and csrf == "abc", (cookies, csrf)

    os.environ["FASIH_SESSION"] = "not json"
    assert importer.load_session() != ({"a": "1"}, "tok"), "bad env should fall through"

    del os.environ["FASIH_SESSION"]
    print("env session: ok")


def test_manual_session():
    import tempfile

    import importer

    orig = importer.MANUAL_SESSION_PATH
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    importer.MANUAL_SESSION_PATH = path
    try:
        cookies, csrf = importer.save_manual_session("x-xsrf-token=tok; SEMAR=abc=def; other=1; note=ar\u2192ow")
        assert cookies == {"x-xsrf-token": "tok", "SEMAR": "abc=def", "other": "1", "note": "ar\u2192ow"}, cookies
        assert csrf == "tok", csrf
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["csrf_token"] == "tok" and data["cookie_header"].startswith("x-xsrf-token=")
        assert data["cookies"]["note"] == "ar\u2192ow", "non-cp1252 char must survive round-trip"

        os.environ.pop("FASIH_SESSION", None)
        assert importer.load_session() == (cookies, csrf), "saved session must load back"

        try:
            importer.save_manual_session("")
            raise AssertionError("empty header must raise ValueError")
        except ValueError:
            pass

        server.session_valid = lambda c, t: True  # stub the FASIH network check
        with TestClient(server.app) as c:
            assert c.post("/api/session", json={"cookie_header": "a=1"}).json() == {"configured": True, "valid": True}
            assert c.post("/api/session", json={"cookie_header": ""}).status_code == 400
    finally:
        importer.MANUAL_SESSION_PATH = orig
        try:
            os.remove(path)
        except OSError:
            pass
    print("manual session: ok")


def test_steps():
    sid = "steps-test"
    server._stage(sid, 0)
    job = server._jobs[sid]
    assert len(job["steps"]) == len(server.REFRESH_STEPS) == 6
    assert job["steps"][0]["current"] and not job["steps"][0]["done"]
    assert all(not s["done"] for s in job["steps"])

    server._stage(sid, 3, "2/5 wilayah")
    job = server._jobs[sid]
    assert all(s["done"] for s in job["steps"][:3]), "earlier steps marked done"
    assert job["steps"][3]["current"] and not job["steps"][3]["done"]
    assert all(not s["done"] and not s["current"] for s in job["steps"][4:])
    assert job["detail"] == "2/5 wilayah"

    with TestClient(server.app) as c:
        assert c.get(f"/api/survey/{sid}/status").json()["detail"] == "2/5 wilayah"
    print("steps: ok")


def test_periods():
    import asyncio

    import build_site
    import data_tab

    row = {"codeIdentity": "C1", "data1": "x",
           "region": {"level1": {"fullCode": "11", "name": "P1"}}}
    rec = data_tab.flatten_row(row, "S", "2026 - Triwulan 1")
    assert rec["periode"] == "2026 - Triwulan 1", rec
    assert rec["data1"] == "x" and rec["prov"] == "P1", rec

    cols = {c["key"]: c["label"] for c in build_site._columns({"name": "S", "periode": "P", "codeIdentity": "C"})}
    assert cols.get("periode") == "Periode", cols

    class _Resp:
        def __init__(self, data):
            self._d = data

        def json(self):
            return {"data": self._d}

    async def fake_get(url, headers, cookies, params=None):
        return _Resp([
            {"id": "b", "name": "T2", "startDate": "2026-02-01"},
            {"id": "a", "name": "T1", "startDate": "2026-01-01"},
            {"id": 123, "name": "bad"},
        ])

    async def fail_get(url, headers, cookies, params=None):
        raise RuntimeError("boom")

    orig = data_tab._get
    try:
        data_tab._get = fake_get
        got = asyncio.run(data_tab._survey_periods("SURVEY", {}, {}))
        assert [p["id"] for p in got] == ["a", "b"], got  # oldest first, non-str id dropped

        data_tab._get = fail_get
        assert asyncio.run(data_tab._survey_periods("SURVEY", {}, {})) == [], "lookup failure -> fall back"
        assert asyncio.run(data_tab._survey_periods("", {}, {})) == []
    finally:
        data_tab._get = orig
    print("periods: ok")


def test_on_demand():
    """Survey list -> periods -> single-period scrape/status/data, network stubbed."""
    import asyncio
    import tempfile

    import data_tab

    class _Resp:
        def __init__(self, d): self._d = d

        def json(self): return self._d

    posts = []

    async def fake_post(url, headers, cookies, payload):
        posts.append(url)
        return _Resp({"data": {"content": [
            {"id": "S1", "name": "Survei Satu"},
            {"id": "S2", "name": "Survei Dua"},
            {"name": "no-id"},
        ]}})

    pcalls = []

    async def fake_periods(sid, headers, cookies):
        pcalls.append(sid)
        return [{"id": "P1", "name": "TW1", "startDate": "2026-01-01", "endDate": "2026-03-31"}]

    calls = []

    async def stub_period(sid, pid, key):
        await asyncio.sleep(0.02)
        server._stage(key, 0)
        server._stage(key, len(server.PERIOD_STEPS), "5 baris")
        calls.append((sid, pid))
        return 5, "20260101_000000"

    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
    with open(os.path.join(tmp, "data", "P1.json"), "w", encoding="utf-8") as f:
        json.dump({"id": "P1", "name": "Survei Satu", "rows": [1, 2]}, f)

    orig = (server.post_requests, server._session_headers, data_tab._survey_periods,
            server._refresh_period, server.SITE_DIR)

    async def fake_headers():
        return {}, {}

    try:
        server._clear_caches()
        server.post_requests = fake_post
        server._session_headers = fake_headers
        data_tab._survey_periods = fake_periods
        server._refresh_period = stub_period
        server.SITE_DIR = tmp

        with TestClient(server.app) as c:
            assert c.get("/api/surveys").json()["surveys"] == [
                {"id": "S1", "name": "Survei Satu"}, {"id": "S2", "name": "Survei Dua"}]
            assert c.get("/api/surveys").json()["surveys"] == [
                {"id": "S1", "name": "Survei Satu"}, {"id": "S2", "name": "Survei Dua"}], "cache miss"
            assert len(posts) == 1, "warm survey list must not re-fetch FASIH"

            per = c.get("/api/survey/S1/periods").json()["periods"]
            assert per == [{"id": "P1", "name": "TW1", "startDate": "2026-01-01",
                            "endDate": "2026-03-31", "cached": True}], per
            assert c.get("/api/survey/S1/periods").status_code == 200, "warm period list"
            assert len(pcalls) == 1, "warm period list must not re-fetch FASIH"

            assert c.get("/api/survey/S1/period/P1/data").status_code == 200
            assert c.get("/api/survey/S1/period/PX/data").status_code == 404
            assert c.get("/api/survey/S1/period/P1/status").json()["state"] == "idle"

            assert c.post("/api/survey/S1/period/P1/scrape").json()["status"] == "queued"
            st = {}
            for _ in range(100):
                st = c.get("/api/survey/S1/period/P1/status").json()
                if st["state"] in ("done", "error"):
                    break
                time.sleep(0.03)
            assert st["state"] == "done" and st["rows"] == 5, st
            assert calls == [("S1", "P1")], "worker must run exactly the queued period"
            assert len(st["steps"]) == len(server.PERIOD_STEPS) == 3, st
            assert st["steps"][-1]["done"] is True
    finally:
        (server.post_requests, server._session_headers, data_tab._survey_periods,
         server._refresh_period, server.SITE_DIR) = orig
    print("on-demand: ok")


def test_login():
    """Password login gate: page, redirect, bad creds, good creds, session cookie."""
    os.environ.pop("AUTH_DISABLED", None)
    orig = (server.LOGIN_USER, server.LOGIN_PASSWORD)
    server.LOGIN_USER, server.LOGIN_PASSWORD = "tester", "secret"
    try:
        with TestClient(server.app) as c:
            r = c.get("/login")
            assert r.status_code == 200 and "Masuk" in r.text, r.status_code

            r = c.get("/", follow_redirects=False)
            assert r.status_code in (302, 307) and "/login" in r.headers.get("location", ""), r.status_code
            assert c.get("/api/me").status_code == 401, "unauthenticated API must be 401"

            r = c.post("/login", data={"username": "tester", "password": "nope"}, follow_redirects=False)
            assert r.status_code == 303 and "error=1" in r.headers.get("location", ""), r.headers.get("location")

            r = c.post("/login", data={"username": "tester", "password": "secret"}, follow_redirects=False)
            assert r.status_code == 303 and server.SESSION_COOKIE in r.headers.get("set-cookie", ""), r.headers

            me = c.get("/api/me").json()
            assert me["user"] == "tester" and me["auth"] == "password", me
    finally:
        server.LOGIN_USER, server.LOGIN_PASSWORD = orig
        os.environ["AUTH_DISABLED"] = "1"
    print("login: ok")


def test_period_dates():
    """A period scrape must store the FASIH start/end dates in the payload, so the
    dashboard can show the remaining time (elapsed/left days)."""
    import asyncio
    import tempfile

    import build_site
    import data_tab
    import pandas as pd

    class _Resp:
        def json(self): return {"data": {"name": "Survei Satu", "regionGroupId": "G1"}}

    async def _async(v):
        return v

    async def fake_headers():
        return {}, {}

    async def fake_periods(sid, headers, cookies):
        return [{"id": "P1", "name": "TW1", "startDate": "2026-01-01", "endDate": "2026-03-31"}]

    async def fake_collect(name, pid, gid, headers, cookies, period_name="", progress=None):
        return pd.DataFrame([{"a": 1}])

    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "data"), exist_ok=True)

    orig = (server.get_requests, server._session_headers, data_tab._survey_periods,
            data_tab.collect_period, build_site.SITE_DIR)
    try:
        server._clear_caches()
        server.get_requests = lambda *a, **k: _async(_Resp())
        server._session_headers = fake_headers
        data_tab._survey_periods = fake_periods
        data_tab.collect_period = fake_collect
        build_site.SITE_DIR = tmp

        rows, _ = asyncio.run(server._refresh_period("S1", "P1", "S1:P1"))
        assert rows == 1, rows
        with open(os.path.join(tmp, "data", "P1.json"), encoding="utf-8") as f:
            payload = json.load(f)
        assert payload["period"] == {"start": "2026-01-01", "end": "2026-03-31"}, payload["period"]
        assert payload["rows"] == [{"a": 1}]
    finally:
        (server.get_requests, server._session_headers, data_tab._survey_periods,
         data_tab.collect_period, build_site.SITE_DIR) = orig
    print("period-dates: ok")


def test_summarize():
    """AI summary endpoint: gated on the key, rejects empty stats, forwards only the
    aggregates to OpenRouter. No network (the httpx AsyncClient is stubbed)."""
    import ai as ai_mod

    seen = []

    class _Resp:
        def __init__(self, status=200, payload=None):
            self.status_code = status
            self.text = "ok"
            self._p = payload or {}

        def json(self):
            return self._p

    def _ok(content):
        return _Resp(200, {"choices": [{"message": {"content": content}}]})

    class _Client:
        """Stub AsyncClient: replies come from a class-level queue, one per call."""

        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            seen.append({"url": url, "body": json, "headers": headers})
            return self._reply.pop(0)

    stats = {"jumlah_sampel": 100, "persen_submit_plus": 42.5, "sisa_hari": 3}
    keys = ("OPENROUTER_API_KEY", "OPENROUTER_MODELS")
    saved = {k: os.environ.get(k) for k in keys}
    orig_client = ai_mod.httpx.AsyncClient

    def _env(**kw):
        for k, v in kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    try:
        _env(OPENROUTER_API_KEY=None, OPENROUTER_MODELS=None)
        with TestClient(server.app) as c:
            assert c.get("/api/me").json()["ai"] is False
            assert c.post("/api/summarize", json={"stats": stats}).status_code == 503

        _env(OPENROUTER_API_KEY="sk-test", OPENROUTER_MODELS="m1,m2")
        ai_mod.httpx.AsyncClient = _Client
        with TestClient(server.app) as c:
            assert c.get("/api/me").json()["ai"] is True
            assert c.post("/api/summarize", json={}).status_code == 400
            assert c.post("/api/summarize", json={"stats": {}}).status_code == 400

            # happy path: the first model answers
            good = "Progres survei berjalan baik: 100 sampel, submit 42.5%, sisa 3 hari.\n- Poin satu."
            _Client._reply = [_ok(good)]
            r = c.post("/api/summarize", json={"stats": stats})
            assert r.status_code == 200, r.text
            assert r.json() == {"summary": good, "model": "openrouter:m1"}
            # the key travels in a header, never the URL, and the prompt carries the numbers
            assert seen[-1]["url"] == ai_mod.URL and "sk-test" not in seen[-1]["url"]
            assert seen[-1]["headers"]["Authorization"] == "Bearer sk-test"
            assert seen[-1]["headers"]["HTTP-Referer"]
            assert "42.5" in seen[-1]["body"]["messages"][0]["content"]

            # a junk / too-short reply falls through to the next model
            good2 = "Ringkasan kedua: progres stabil, perlu perhatian pada akhir periode kerja."
            _Client._reply = [_ok("User Safety: safe"), _ok(good2)]
            r = c.post("/api/summarize", json={"stats": stats})
            assert r.status_code == 200 and r.json()["model"] == "openrouter:m2", r.text
            assert r.json()["summary"] == good2

            # a rejected key fails fast instead of walking the whole model list
            n = len(seen)
            _Client._reply = [_Resp(401, {"error": {"message": "unauthorized"}}),
                              _ok("harusnya tidak terpakai")]
            r = c.post("/api/summarize", json={"stats": stats})
            assert r.status_code == 502 and "401" in r.json()["detail"], r.text
            assert len(seen) == n + 1, "must stop at the first 401"
    finally:
        ai_mod.httpx.AsyncClient = orig_client
        _env(**{k: saved[k] for k in keys})
    print("summarize: ok")


def test_cross_loop_locks():
    """The throttle/limiter locks are module-level, but the Streamlit app calls
    asyncio.run() per action (fresh loop each time). A lock bound to a previous
    loop must rebind on a contended acquire instead of raising "bound to a
    different event loop" -- which killed the second click after a rerun."""
    import asyncio

    import api_client
    import data_tab

    async def _throttle_burst():
        api_client._last_request_at = asyncio.get_running_loop().time()  # force a wait
        await asyncio.gather(*[api_client._throttle() for _ in range(4)])

    lim = data_tab._ensure_limiter()
    saved = lim.max_calls, lim.period, lim._times

    async def _limiter_burst():
        lim.max_calls, lim.period = 1, 0.01   # window full -> holder sleeps in lock
        lim._times = [asyncio.get_running_loop().time()]
        await asyncio.gather(*[lim.acquire() for _ in range(2)])

    orig_interval = api_client._REQUEST_INTERVAL
    api_client._REQUEST_INTERVAL = 0.05
    try:
        for _ in range(2):  # second loop is the one that used to explode
            asyncio.run(_throttle_burst())
            asyncio.run(_limiter_burst())
    finally:
        api_client._REQUEST_INTERVAL = orig_interval
        lim.max_calls, lim.period, lim._times = saved
    print("cross-loop locks: ok")


if __name__ == "__main__":
    test_cookie()
    test_manifest()
    test_api()
    test_env_session()
    test_manual_session()
    test_steps()
    test_periods()
    test_on_demand()
    test_login()
    test_period_dates()
    test_summarize()
    test_cross_loop_locks()
    print("test_server OK")
