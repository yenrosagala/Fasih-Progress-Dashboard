"""Self-check for the browser bridge's pure bits (no Chrome, no network).

Run: python test_importer_bridge.py
"""

import json
import os
import urllib.request

from importer import _cookies_from_cdp, _hosted_bridge_session


def test_cookie_filter():
    raw = [
        {"name": "XSRF-TOKEN", "value": "abc%3D", "domain": ".fasih-sm.bps.go.id"},
        {"name": "JSESSIONID", "value": "j1", "domain": "fasih-sm.bps.go.id"},
        {"name": "TRK", "value": "noise", "domain": ".google.com"},
        {"name": "EVIL", "value": "noise", "domain": "notbps.go.id"},
    ]
    cookies, csrf = _cookies_from_cdp(raw)
    assert cookies == {"XSRF-TOKEN": "abc%3D", "JSESSIONID": "j1"}, cookies
    assert csrf == "abc=", csrf  # XSRF value is URL-decoded
    assert _cookies_from_cdp([]) == ({}, None)
    print("ok: browser-bridge cookie filter keeps only bps.go.id + decodes XSRF")


class _Resp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def read(self):
        return self._body


def test_hosted_bridge():
    seen = {}

    def fake(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.headers)
        return _Resp(json.dumps({"cookie_header": "XSRF-TOKEN=abc%3D; JSESSIONID=j1"}).encode())

    os.environ["FASIH_BRIDGE_URL"] = "https://bridge.example/"
    os.environ["FASIH_BRIDGE_TOKEN"] = "tok"
    orig = urllib.request.urlopen
    urllib.request.urlopen = fake
    try:
        cookies, csrf = _hosted_bridge_session()
    finally:
        urllib.request.urlopen = orig
        os.environ.pop("FASIH_BRIDGE_URL", None)
        os.environ.pop("FASIH_BRIDGE_TOKEN", None)

    assert seen["url"] == "https://bridge.example/status", seen
    assert "tok" in seen["headers"].values(), seen  # X-Bridge-Token sent
    assert cookies == {"XSRF-TOKEN": "abc%3D", "JSESSIONID": "j1"}, cookies
    assert csrf == "abc=", csrf  # derived from the cookie when the bridge omits it
    assert _hosted_bridge_session() == (None, None)  # env cleared -> no-op, never raises
    print("ok: hosted bridge parses /status, sends X-Bridge-Token, no-ops without env")


if __name__ == "__main__":
    test_cookie_filter()
    test_hosted_bridge()
