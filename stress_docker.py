"""Concurrent load test for the Docker site (server.py serving outputs/site).

Stdlib only. Hammers the serving layer -- the SPA shell, the manifest, a large
per-survey PII payload, and the cheap JSON APIs -- with N worker threads for a
fixed wall-clock duration, then prints throughput + latency percentiles.

It deliberately does NOT touch /api/survey/*/periods|scrape: those call FASIH,
are rate-limited per account, and would burn the real login. This measures the
serving layer only, which is what a crowd of browsers hits.

Run against a running container:
    python stress_docker.py [url] [workers] [seconds]
    python stress_docker.py http://127.0.0.1:8081 32 10
"""
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8081"
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 32
SECONDS = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0

BIG = "/data/demo-vip-horti.json"  # ~11.5 MB, the heaviest thing the SPA loads
PATHS = ["/", "/index.html", "/surveys.json", BIG, "/healthz", "/api/me"]
if os.getenv("NO_BIG") == "1":  # isolate the small-payload ceiling from the big file
    PATHS.remove(BIG)

_stop = threading.Event()
_lock = threading.Lock()
_lat = []
_codes = {}
_bytes = 0


def _one(url):
    global _bytes
    t0 = time.perf_counter()
    nbytes = 0
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            nbytes = len(r.read())
            code = r.status
    except urllib.error.HTTPError as e:
        e.read()
        code = e.code
    except Exception as e:
        code = f"ERR:{type(e).__name__}"
    dt = time.perf_counter() - t0
    with _lock:
        _lat.append(dt)
        _codes[code] = _codes.get(code, 0) + 1
        _bytes += nbytes


def _worker(base):
    i = 0
    while not _stop.is_set():
        _one(base + PATHS[i % len(PATHS)])
        i += 1


def main():
    base = URL.rstrip("/")
    for p in PATHS:  # warm-up: fail fast if a route is missing, not as a load error
        with urllib.request.urlopen(base + p, timeout=60) as r:
            r.read()
            assert r.status == 200, f"warm-up {p} -> {r.status}"

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(_worker, base) for _ in range(WORKERS)]
        time.sleep(SECONDS)
        _stop.set()
        for f in futs:
            f.result()
    dur = time.time() - t0

    _lat.sort()
    n = len(_lat)
    pct = lambda p: _lat[min(n - 1, int(n * p))] * 1000 if n else 0.0
    print(f"url={base} workers={WORKERS} duration={dur:.1f}s")
    print(f"requests={n}  rps={n / dur:.0f}  throughput={_bytes / dur / 1e6:.1f} MB/s")
    print(f"latency ms  p50={pct(.5):.1f}  p90={pct(.9):.1f}  p99={pct(.99):.1f}  max={_lat[-1] * 1000:.1f}")
    print("codes:", dict(sorted(_codes.items(), key=lambda kv: str(kv[0]))))
    bad = sum(v for k, v in _codes.items() if k != 200)
    assert n > 0, "no requests completed"
    assert bad == 0, f"non-200 responses: {_codes}"


if __name__ == "__main__":
    main()
