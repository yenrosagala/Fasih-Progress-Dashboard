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


if __name__ == "__main__":
    test_cookie()
    test_manifest()
    test_api()
    test_env_session()
    print("test_server OK")
