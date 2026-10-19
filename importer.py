import json
import os
import time
import urllib.request
import httpx
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from config import LOGIN_URL, SURVEY_PAGE_URL, survey_datatable_url

COOKIE_CACHE_PATH = "inputs/session_cache.json"
MANUAL_SESSION_PATH = "inputs/manual_session.json"
_TEST_URL = survey_datatable_url
_TEST_PAYLOAD = {"pageNumber": 0, "pageSize": 1, "sortBy": "CREATED_AT", "sortDirection": "DESC", "keywordSearch": ""}


def _save_session(cookies_dict, csrf_token):
    os.makedirs("inputs", exist_ok=True)
    with open(COOKIE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"cookies": cookies_dict, "csrf_token": csrf_token}, f)


def _load_session():
    if os.path.exists(COOKIE_CACHE_PATH):
        with open(COOKIE_CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("cookies"), data.get("csrf_token")
    return None, None


def _parse_cookie_header(cookie_header):
    cookies = {}
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = value.strip()
    return cookies


def _csrf_from_cookies(cookies):
    from urllib.parse import unquote
    for name, value in cookies.items():
        if name.lower() in ["x-xsrf-token", "xsrf-token"]:
            return unquote(value)
    return None


def _parse_session_blob(data):
    cookies = data.get("cookies")
    cookie_header = data.get("cookie_header")
    if not cookies and cookie_header:
        cookies = _parse_cookie_header(cookie_header)
    csrf_token = data.get("csrf_token") or _csrf_from_cookies(cookies or {})
    return cookies, csrf_token


def save_manual_session(cookie_header):
    """Persist a pasted FASIH Cookie header to inputs/manual_session.json.

    Same on-disk shape as make_manual_session.py, so load_session() picks it up
    on the next call (no restart needed). Returns (cookies, csrf_token).
    Raises ValueError when the header has no parseable cookies.
    """
    cookie_header = (cookie_header or "").strip()
    cookies = _parse_cookie_header(cookie_header) if cookie_header else {}
    if not cookies:
        raise ValueError("Header Cookie kosong atau tidak valid.")
    csrf_token = None
    for name, value in cookies.items():
        if name.lower() in {"x-xsrf-token", "xsrf-token"}:
            csrf_token = value
            break
    payload = {"cookie_header": cookie_header, "cookies": cookies}
    if csrf_token:
        payload["csrf_token"] = csrf_token
    os.makedirs("inputs", exist_ok=True)
    with open(MANUAL_SESSION_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return cookies, csrf_token


def _load_manual_session():
    if not os.path.exists(MANUAL_SESSION_PATH):
        return None, None

    with open(MANUAL_SESSION_PATH, encoding="utf-8") as f:
        return _parse_session_blob(json.load(f))


def _load_env_session():
    raw = os.getenv("FASIH_SESSION")
    if not raw:
        return None, None
    try:
        return _parse_session_blob(json.loads(raw))
    except ValueError:
        return None, None


def _cdp_call(ws_url, method, timeout=5):
    """One-shot Chrome DevTools Protocol request; returns the result dict."""
    import websocket  # websocket-client, already a selenium dependency

    # Chrome 111+ rejects a CDP websocket whose Origin isn't allow-listed; dropping
    # the Origin header sidesteps --remote-allow-origins entirely.
    ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": method}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                return msg.get("result") or {}
    finally:
        ws.close()


def _cookies_from_cdp(raw):
    """Keep only bps.go.id cookies from a CDP cookie list, and pull the XSRF token."""
    cookies = {
        c["name"]: c["value"]
        for c in raw
        if (c.get("domain") or "").lstrip(".") == "bps.go.id"
        or (c.get("domain") or "").lstrip(".").endswith(".bps.go.id")
    }
    return cookies, _csrf_from_cookies(cookies)


def _hosted_bridge_session():
    """Read the FASIH session from a hosted bridge server over HTTPS.

    Contract (reverse-engineered from the live service; the token comes from the
    bridge operator — see README/notes, tokens are never guessed):

        GET {FASIH_BRIDGE_URL}/status
        Header: X-Bridge-Token: {FASIH_BRIDGE_TOKEN}
        -> 200 JSON shaped like inputs/manual_session.json
           ({cookies} or {cookie_header}, csrf_token optional)

    Returns (cookies, csrf) or (None, None); never raises, so callers fall
    through to the local CDP bridge / manual/cache. Both env vars must be set.
    """
    base = (os.getenv("FASIH_BRIDGE_URL") or "").rstrip("/")
    token = os.getenv("FASIH_BRIDGE_TOKEN")
    if not base or not token:
        return None, None
    try:
        req = urllib.request.Request(
            base + "/status",
            headers={"X-Bridge-Token": token, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
    except Exception:
        return None, None
    return _parse_session_blob(data if isinstance(data, dict) else {})


def browser_session(port=None, host="127.0.0.1"):
    """The "browser bridge": read live FASIH cookies without pasting them.

    Tries the hosted HTTPS bridge (FASIH_BRIDGE_URL + FASIH_BRIDGE_TOKEN) first —
    it needs no local browser, so it works on a server. Otherwise falls back to a
    running Chrome over CDP (--remote-debugging-port, see start_bridge.cmd).
    Returns (cookies, csrf), or (None, None) when neither bridge yields cookies.

    ponytail: Network.getAllCookies is CDP-deprecated but still shipped and needs no
    target bookkeeping; swap for Storage.getCookies (the browser-target fallback
    below already uses it) if it ever disappears.
    """
    host_cookies, host_csrf = _hosted_bridge_session()
    if host_cookies:
        return host_cookies, host_csrf

    port = int(port or os.getenv("FASIH_CDP_PORT") or 9222)
    base = f"http://{host}:{port}"

    def _get(path):
        with urllib.request.urlopen(base + path, timeout=2) as r:
            return json.loads(r.read())

    try:
        pages = [t for t in _get("/json") if t.get("type") == "page"]
    except Exception:
        return None, None

    raw = []
    for t in pages:  # any page target exposes every browser cookie
        try:
            raw = _cdp_call(t["webSocketDebuggerUrl"], "Network.getAllCookies").get("cookies") or []
            break
        except Exception:
            continue
    if not raw:  # headless / no page open: the browser target still has them
        try:
            raw = _cdp_call(_get("/json/version").get("webSocketDebuggerUrl"), "Storage.getCookies").get("cookies") or []
        except Exception:
            return None, None

    cookies, csrf = _cookies_from_cdp(raw)
    return (cookies, csrf) if cookies else (None, None)


def _session_check(cookies_dict, csrf_token):
    """Probe FASIH once. Returns (ok, note); note is a short reason for logs/UI."""
    from config import BASE_HEADERS
    headers = {
        **BASE_HEADERS,
        "X-XSRF-TOKEN": csrf_token,
    }
    try:
        response = httpx.post(
            _TEST_URL,
            headers=headers,
            cookies=cookies_dict,
            json=_TEST_PAYLOAD,
            timeout=httpx.Timeout(30, connect=15.0),
        )
        print(f"   Session check status: {response.status_code}")
        body = response.text[:2000].lower()
        if "bot-" in body or "sistem kami mendeteksi koneksi anda sebagai bot" in body:
            print(
                "   BPS/FASIH returned a bot-detection page. "
                "Stop running the script and check access manually in a normal browser."
            )
            return False, "bot-page"
        return response.status_code == 200, str(response.status_code)
    except Exception as e:
        print(f"   Session check failed ({type(e).__name__}): {e}")
        return False, type(e).__name__


def _session_valid(cookies_dict, csrf_token):
    return _session_check(cookies_dict, csrf_token)[0]


def load_session():
    """Server-safe session load: FASIH_SESSION env, then manual file, then cache.

    Never opens a browser. Returns (cookies, csrf) or (None, None). FASIH_SESSION
    holds the same JSON as inputs/manual_session.json, so a platform secret can
    supply the session without committing a file. The CLI's get_cookies_and_csrf()
    falls back to Selenium, which is unusable on a server, so the backend uses
    this instead and reports a clear "session expired" error to the operator.
    """
    cookies, csrf = _load_env_session()
    if cookies and csrf:
        return cookies, csrf
    if os.getenv("FASIH_BRIDGE") or os.getenv("FASIH_BRIDGE_URL"):
        cookies, csrf = browser_session()
        if cookies and csrf:
            return cookies, csrf
    cookies, csrf = _load_manual_session()
    if cookies and csrf:
        return cookies, csrf
    return _load_session()


def session_valid(cookies, csrf):
    """Cheap FASIH reachability/auth probe. Returns bool."""
    return _session_valid(cookies, csrf) if (cookies and csrf) else False


def session_probe(cookies, csrf):
    """(ok, note) — like session_valid(), but carries a short reason for the UI
    ('200', '401', 'bot-page', 'ConnectError', or '' when there is no session)."""
    return _session_check(cookies, csrf) if (cookies and csrf) else (False, "")


def get_cookies_and_csrf():
    manual_cookies, manual_csrf_token = _load_manual_session()
    if manual_cookies and manual_csrf_token:
        print("🔄 Checking manual browser session...")
        if _session_valid(manual_cookies, manual_csrf_token):
            print("✅ Manual browser session valid.\n")
            _save_session(manual_cookies, manual_csrf_token)
            return manual_cookies, manual_csrf_token
        print("⚠️  Manual browser session is not valid.\n")

    cookies, csrf_token = _load_session()
    if cookies and csrf_token:
        print("🔄 Checking cached session...")
        if _session_valid(cookies, csrf_token):
            print("✅ Cached session valid, skipping login.\n")
            return cookies, csrf_token
        print("⚠️  Cached session expired, re-logging in...\n")

    print("🌉 Checking browser bridge (Chrome --remote-debugging-port)...")
    bridge_cookies, bridge_csrf = browser_session()
    if bridge_cookies and bridge_csrf and _session_valid(bridge_cookies, bridge_csrf):
        print("✅ Browser bridge session valid.\n")
        _save_session(bridge_cookies, bridge_csrf)
        return bridge_cookies, bridge_csrf
    print("⚠️  Browser bridge unavailable or invalid; falling back to manual login.\n")

    options = webdriver.ChromeOptions()
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    print("🔐 Opening browser... please log in manually.")
    driver.get(LOGIN_URL)
    input("✅ After logging in completely, press ENTER to continue...")

    # Navigate to the survey page so FASIH issues app cookies after manual login.
    driver.get(SURVEY_PAGE_URL)
    time.sleep(5)

    selenium_cookies = driver.get_cookies()
    driver.quit()

    from urllib.parse import unquote
    csrf_token = None
    for cookie in selenium_cookies:
        if cookie['name'].lower() in ['x-xsrf-token', 'xsrf-token']:
            # F5 WAF sometimes URL-encodes the XSRF value
            csrf_token = unquote(cookie['value'])
            break

    cookies_dict = {cookie['name']: cookie['value'] for cookie in selenium_cookies}

    print(f"💾 Captured {len(cookies_dict)} cookies. CSRF present: {bool(csrf_token)}")
    _save_session(cookies_dict, csrf_token)
    print("💾 Session cached for next run.\n")
    return cookies_dict, csrf_token


def get_payload(region1Id, surveyPeriodId):
    return {
        "filterTargetType":"TARGET_ONLY",
        "region1Id": region1Id,
        "region2Id": None,
        "region3Id": None,
        "region4Id": None,
        "region5Id": None,
        "region6Id": None,
        "region7Id": None,
        "region8Id": None,
        "region9Id": None,
        "region10Id": None,
        "surveyPeriodId": surveyPeriodId,
        "assignmentErrorStatusType": -1,
        "assignmentStatusAlias": None,
        "data1": None,
        "data2": None,
        "data3": None,
        "data4": None,
        "data5": None,
        "data6": None,
        "data7": None,
        "data8": None,
        "data9": None,
        "data10": None,
        "userIdResponsibility": None,
        "currentUserId": None,
        "regionId": None
        }
