"""Self-check for build_site.py output. Run: python test_site.py

Fails if: a data payload isn't strict JSON (the NaN bug), the manifest and
data/ files disagree, or status bucketing stops matching the raw aliases.
"""
import json
import os

import build_site

SITE = build_site.SITE_DIR


def strict_json(path):
    with open(path, encoding="utf-8") as f:
        return json.loads(f.read())  # json.loads rejects NaN/Infinity


def canon(v, status_map):
    s = str(v if v is not None else "").strip().upper()
    if not s:
        return "other"
    for d in status_map:
        if any(a in s for a in d["aliases"]):
            return d["key"]
    return "other"


def counts(rows, status_map):
    o = {}
    for r in rows:
        k = canon(r.get("status"), status_map)
        o[k] = o.get(k, 0) + 1
    return o


def check_js():
    """Parse the inline scripts with node when available.

    A JS syntax error (e.g. a duplicate `const`) silently kills every handler,
    so the page renders but never fetches anything. Node is optional: without
    it this check is skipped.
    """
    import re
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node")
    if not node:
        print("  js: node not found, skipped")
        return
    with open(os.path.join(SITE, "index.html"), encoding="utf-8") as f:
        blocks = re.findall(r"<script>(.*?)</script>", f.read(), re.S)
    assert blocks, "no inline script in index.html"
    for i, js in enumerate(blocks):
        fd, path = tempfile.mkstemp(suffix=".js")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(js)
            r = subprocess.run([node, "--check", path], capture_output=True, text=True)
            assert r.returncode == 0, f"inline script {i} syntax error:\n{r.stderr}"
        finally:
            os.remove(path)
    print(f"  js: {len(blocks)} inline script(s) parse")


def main():
    build_site.build_site()

    manifest = strict_json(os.path.join(SITE, "surveys.json"))
    assert manifest["surveys"], "manifest empty"
    for s in manifest["surveys"]:
        path = os.path.join(SITE, "data", f'{s["id"]}.json')
        assert os.path.exists(path), f"missing payload {path}"
        payload = strict_json(path)
        assert payload["columns"], f'{s["id"]}: no columns'
        assert len(payload["rows"]) == s["rows"], f'{s["id"]}: row count drift'
        assert payload["statusMap"], f'{s["id"]}: no statusMap'

    # SITASI: raw OPEN/DRAFT must bucket to open/draft (nothing else).
    sitasi = next(x for x in manifest["surveys"] if not x["demo"])
    p = strict_json(os.path.join(SITE, "data", f'{sitasi["id"]}.json'))
    c = counts(p["rows"], p["statusMap"])
    assert set(c) == {"open", "draft"}, f"sitasi buckets: {sorted(c)}"
    assert c["open"] + c["draft"] == len(p["rows"]), "sitasi bucket sum mismatch"
    print(f"  sitasi: {c}")

    # Demo: spreads across all six buckets, no 'other'.
    demo = next(x for x in manifest["surveys"] if x["demo"])
    d = strict_json(os.path.join(SITE, "data", f'{demo["id"]}.json'))
    dc = counts(d["rows"], d["statusMap"])
    assert "other" not in dc, f"demo leaked to other: {dc.get('other')}"
    assert len(dc) == 6, f"demo buckets: {sorted(dc)}"
    print(f"  demo: {dc}")

    check_js()

    print("test_site OK")


if __name__ == "__main__":
    main()
