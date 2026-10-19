"""Self-check for the Streamlit entrypoint's non-trivial bits.

Imports streamlit_app/app.py with a stubbed Streamlit (no runtime, no browser)
and asserts the things the Cloud deploy rests on:
1. _publish() mirrors outputs/site -> streamlit_app/static/site (the served folder).
2. The embedded iframe HTML is the SPA plus exactly one injected <base href>.
3. The login gate code is kept and still blocks when invoked, while the app
   skips it by default (SHOW_LOGIN=False) even with creds configured.
4. _write_ui_state() publishes the control bar's selection the popup menu reads.
5. The cookie/survei/periode controls render on the MAIN screen: both pickers
   called, the st.sidebar context never entered (CSS hides it instead), and the
   fetch button still carries the "data periode" label the popup matches.

Run: python test_streamlit_app.py
"""

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE_SRC = ROOT / "outputs" / "site"
SITE_DST = ROOT / "streamlit_app" / "static" / "site"


class _Ctx:
    """Context manager for every st.<block>; `entered` records each __enter__."""

    def __init__(self, entered=None):
        self.entered = entered

    def __enter__(self):
        if self.entered is not None:
            self.entered.append(True)
        return self

    def __exit__(self, *exc):
        return False


def _load_app(clear_login=True):
    seen = {}
    fake = types.ModuleType("streamlit")
    fake.cache_data = lambda **kw: (lambda fn: fn)
    fake.secrets = {}
    fake.session_state = {}
    fake.sidebar = _Ctx(seen.setdefault("sidebar_entered", []))
    fake.form = lambda key: _Ctx()
    fake.expander = lambda *a, **kw: _Ctx()
    fake.container = lambda **kw: seen.update(container=kw) or _Ctx()
    fake.columns = lambda spec, **kw: [_Ctx() for _ in spec]
    fake.markdown = lambda html, **kw: seen.setdefault("markdown", []).append(html)
    fake.selectbox = lambda label, *a, **kw: seen.setdefault("selects", []).append(label) or 0
    fake.set_page_config = lambda **kw: None
    fake.title = lambda *a, **kw: seen.setdefault("title", a)
    fake.warning = lambda *a, **kw: seen.setdefault("warning", a)
    fake.error = lambda *a, **kw: seen.setdefault("error", a)
    fake.info = lambda *a, **kw: None
    fake.caption = lambda *a, **kw: None
    fake.text_input = lambda *a, **kw: ""
    fake.text_area = lambda *a, **kw: ""
    fake.form_submit_button = lambda *a, **kw: False
    fake.button = lambda label, **kw: seen.setdefault("buttons", []).append(label) or False
    fake.rerun = lambda: (_ for _ in ()).throw(RuntimeError("rerun"))
    fake.iframe = lambda html, **kw: seen.update(iframe=html)
    sys.modules["streamlit"] = fake

    # Hermetic: no real session, so the app takes its no-network path even on a
    # machine that has inputs/manual_session.json.
    fake_importer = types.ModuleType("importer")
    fake_importer.load_session = lambda: (None, None)
    fake_importer.session_valid = lambda *a: False
    fake_importer.session_probe = lambda *a: (False, "")
    fake_importer.save_manual_session = lambda *a, **kw: None
    fake_importer.get_cookies_and_csrf = lambda *a, **kw: (None, None)
    sys.modules["importer"] = fake_importer
    if clear_login:
        for k in ("LOGIN_USER", "LOGIN_PASSWORD"):
            os.environ.pop(k, None)
    sys.path.insert(0, str(ROOT))

    spec = importlib.util.spec_from_file_location("st_app", ROOT / "streamlit_app" / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, seen


def main():
    src_html = (SITE_SRC / "index.html").read_text(encoding="utf-8")
    assert "<base" not in src_html, "the source SPA must stay untouched (inject at render time)"

    _mod, seen = _load_app()

    assert (SITE_DST / "index.html").exists(), "_publish() did not mirror index.html"
    if (SITE_SRC / "surveys.json").exists():
        assert (SITE_DST / "surveys.json").exists(), "_publish() did not mirror the manifest"
    print("ok: _publish() mirrored outputs/site -> streamlit_app/static/site")

    html = seen.get("iframe")
    assert html, "app never called st.iframe"
    assert html.count("<base ") == 1, f"expected exactly one base tag, got {html.count('<base ')}"
    assert '<head><base href="/app/static/site/">' in html, "base tag not injected after <head>"
    assert 'id="picker"' in html, "embedded HTML is not the dashboard SPA"
    assert len(html) > len(src_html), "embedded HTML lost content"
    print("ok: iframe HTML = SPA + one <base> pointing at the static route")

    assert seen.get("warning"), "expected the no-session warning instead of a crash"
    print("ok: no-session path shows the operator warning instead of crashing")

    # The popup refresh menu fetches this file through <base>, so it must be there.
    _mod._write_ui_state("Survei Uji \u00b7 01/01\u201331/01", True)
    state = json.loads((SITE_DST / "ui_state.json").read_text(encoding="utf-8"))
    assert state == {"label": "Survei Uji \u00b7 01/01\u201331/01", "saved": True}, state
    (SITE_DST / "ui_state.json").unlink(missing_ok=True)  # test artifact, not data
    print("ok: ui_state.json for the popup menu is written as valid JSON")

    # Controls live on the main screen: give the app a happy session and re-run it.
    _mod._headers_cookies = lambda: None
    _mod._session_state = lambda blob: (True, "")
    _mod._surveys = lambda blob: [{"id": "s1", "name": "Survei Uji"}]
    _mod._periods = lambda blob, sid: [
        {"id": "p1", "name": "Januari", "startDate": "2026-01-01", "endDate": "2026-01-31"}
    ]
    _mod.main()
    assert seen.get("selects") == ["Survei", "Periode"], seen.get("selects")
    assert not seen.get("sidebar_entered"), "controls must not render inside st.sidebar"
    assert any("stSidebar" in m and "display:none" in m for m in seen.get("markdown", [])), \
        "the emptied sidebar must be hidden with CSS"
    assert seen.get("container", {}).get("border"), "controls must sit in one bordered card"
    assert any("data periode" in b.lower() for b in seen.get("buttons", [])), \
        f"popup contract broken, buttons={seen.get('buttons')}"
    (SITE_DST / "ui_state.json").unlink(missing_ok=True)  # written by this run
    print("ok: cookie/survei/periode controls render on the main screen (sidebar unused, hidden)")

    # Session guard: a period already taken this visit must not be scraped again.
    mod3, seen3 = _load_app()
    mod3._headers_cookies = lambda: None
    mod3._session_state = lambda blob: (True, "")
    mod3._surveys = lambda blob: [{"id": "s1", "name": "Survei Uji"}]
    mod3._periods = lambda blob, sid: [
        {"id": "p1", "name": "Januari", "startDate": "2026-01-01", "endDate": "2026-01-31"}
    ]
    mod3.st.session_state["scraped"] = {"p1": "s1"}  # the visitor already took p1
    mod3.st.button = lambda label, **kw: (
        seen3.setdefault("buttons", []).append(label) or "data periode" in label.lower()
    )
    mod3.st.info = lambda msg, **kw: seen3.update(info=msg)
    scraped = []
    mod3._run_scrape = lambda sid, p: scraped.append(sid)
    mod3.main()
    assert any("sudah diambil" in b.lower() for b in seen3.get("buttons", [])), \
        f"already-taken period must be relabelled, buttons={seen3.get('buttons')}"
    assert not scraped, "an already-taken period must not be scraped again this visit"
    assert seen3.get("info"), "the guard must tell the visitor the period was already taken"
    (SITE_DST / "ui_state.json").unlink(missing_ok=True)  # written by this run
    print("ok: session guard skips re-scraping a period already taken this visit")

    # Viewer mode: DATA_REPO + DATA_TOKEN set -> serve pushed data, no scrape UI.
    mod2, seen2 = _load_app()
    mod2._secret = lambda n, d="": {"DATA_REPO": "me/fasih-data", "DATA_TOKEN": "tok"}.get(n, d)
    mod2._sync_data = lambda repo, token: 3
    mod2.main()
    assert seen2.get("iframe"), "viewer mode must still embed the SPA"
    assert not seen2.get("selects"), f"viewer mode must not render pickers: {seen2.get('selects')}"
    assert not [b for b in seen2.get("buttons", []) if "data periode" in b.lower()], \
        "viewer mode must not show the fetch button"
    print("ok: viewer mode (DATA_REPO/DATA_TOKEN) serves pushed data, skips scrape controls")

    # Gate kept but skipped: creds set, default SHOW_LOGIN=False -> app runs,
    # while _gate() itself must still block when called.
    os.environ["LOGIN_USER"], os.environ["LOGIN_PASSWORD"] = "tester", "s3cret"
    try:
        _mod, seen = _load_app(clear_login=False)
        assert not _mod.SHOW_LOGIN, "default keeps the login form hidden"
        assert seen.get("iframe"), "SHOW_LOGIN=False must let the app past the gate"
        assert seen.get("title") != ("Masuk",), "login form must not render"
        assert _mod._gate() is False, "the kept _gate() code must still block"
        print("ok: login code kept (_gate still blocks) but skipped while SHOW_LOGIN=False")
    finally:
        os.environ.pop("LOGIN_USER", None)
        os.environ.pop("LOGIN_PASSWORD", None)


if __name__ == "__main__":
    main()
