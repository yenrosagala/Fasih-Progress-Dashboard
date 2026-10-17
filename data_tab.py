import asyncio
import json
import os

import pandas as pd

from api_client import get_requests, post_requests
from config import (
    BASE_HEADERS,
    datatable_all_user_url,
    myinfo_url,
    region_level1_url,
    region_level2_url,
    survey_periods_url,
)
from importer import get_cookies_and_csrf

OUTPUT_CSV = "outputs/csv/data_sample.csv"
OUTPUT_JSON = "outputs/data_sample.json"

# Server caps: length <= 150 (else 400) and start < 1000 (else 0 rows), so a single
# query partition returns at most ~1000 rows. We partition by kabupaten (each well
# under 1000 for SITASI) to page everything.
# ponytail: fixed at kabupaten; partition deeper (region3Id/kecamatan) if a
# kabupaten ever reaches 1000 rows.
PAGE_SIZE = 150
MAX_WINDOW = 1000

# The API allows ~20 requests then puts the caller in a ~45-60s cooldown (no
# Retry-After header). We stay just under that with a rolling-window limiter.
RATE_MAX_CALLS = int(os.getenv("FASIH_DATA_TAB_RATE", "18"))
RATE_PERIOD = float(os.getenv("FASIH_DATA_TAB_PERIOD", "60"))

_DATA_COLUMNS = [{"data": c, "orderable": True}
                 for c in ["id", "codeIdentity"] + [f"data{i}" for i in range(1, 11)]]

_limiter = None


class _RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self._times = []
        self._lock = None
        self._lock_loop = None

    async def acquire(self):
        loop = asyncio.get_running_loop()
        if self._lock_loop is not loop:
            # ponytail: asyncio.Lock binds to the loop that first waits on it and
            # raises "bound to a different event loop" after; the Streamlit app runs
            # a fresh loop per asyncio.run(), so swap the lock per loop (the rolling
            # _times window stays valid -- loop.time() is monotonic across loops).
            # Upgrade path: one persistent event loop for the whole app.
            self._lock, self._lock_loop = asyncio.Lock(), loop
        async with self._lock:
            while True:
                now = loop.time()
                self._times = [t for t in self._times if now - t < self.period]
                if len(self._times) < self.max_calls:
                    self._times.append(now)
                    return
                await asyncio.sleep(self.period - (now - self._times[0]) + 0.5)


def _ensure_limiter():
    global _limiter
    if _limiter is None:
        _limiter = _RateLimiter(RATE_MAX_CALLS, RATE_PERIOD)
    return _limiter


async def _get(url, headers, cookies):
    await _ensure_limiter().acquire()
    return await get_requests(url, headers, cookies)


async def _post(url, headers, cookies, payload):
    await _ensure_limiter().acquire()
    return await post_requests(url, headers, cookies, payload)


def build_payload(survey_period_id, region1_id=None, region2_id=None, start=0, length=PAGE_SIZE):
    extra = {
        "surveyPeriodId": survey_period_id,
        "assignmentErrorStatusType": -1,
        "sampleType": 1,
        "filterTargetType": "TARGET_ONLY",
    }
    if region1_id:
        extra["region1Id"] = region1_id
    if region2_id:
        extra["region2Id"] = region2_id
    return {
        "start": start,
        "length": length,
        "columns": _DATA_COLUMNS,
        "order": [],
        "search": {"value": "", "regex": False},
        "assignmentExtraParam": extra,
    }


def _region_levels(region):
    levels, node = {}, region
    for i in range(1, 6):
        node = (node or {}).get(f"level{i}")
        if not node:
            break
        levels[i] = node
    return levels


def flatten_row(row, survey_name, period_name=""):
    lv = _region_levels(row.get("region") or {})

    def g(i, key):
        return (lv.get(i) or {}).get(key)

    rec = {
        "name": survey_name,
        "periode": period_name,
        "codeIdentity": row.get("codeIdentity"),
        "status": row.get("assignmentStatusAlias"),
        "petugas": row.get("currentUserFullname"),
        "peran": row.get("currentUserSurveyRoleName"),
        "mode": ",".join(row.get("mode") or []),
        "prov_code": g(1, "fullCode"), "prov": g(1, "name"),
        "kab_code": g(2, "fullCode"), "kab": g(2, "name"),
        "kec_code": g(3, "fullCode"), "kec": g(3, "name"),
        "desa_code": g(4, "fullCode"), "desa": g(4, "name"),
        "sls_code": g(5, "fullCode"), "sls": g(5, "name"),
        "sumError": row.get("sumError"),
        "sumRemark": row.get("sumRemark"),
        "sumClean": row.get("sumClean"),
        "done": row.get("done"),
        "dateCreated": row.get("dateCreated"),
        "dateModified": row.get("dateModified"),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
    }
    for k in row:
        if k.startswith("data") and k[4:].isdigit():
            rec[k] = row.get(k)
    return rec


async def _collect_partition(survey_name, survey_period_id, region1_id, region2_id, label,
                             headers, cookies, semaphore, seen, period_name=""):
    async with semaphore:
        records, start, total = [], 0, 0
        while True:
            payload = build_payload(survey_period_id, region1_id, region2_id, start, PAGE_SIZE)
            j = (await _post(datatable_all_user_url, headers, cookies, payload)).json()
            batch = j.get("searchData") or []
            total = j.get("totalHit", 0)
            for r in batch:
                rid = r.get("id")
                if rid not in seen:
                    seen.add(rid)
                    records.append(flatten_row(r, survey_name, period_name))
            start += len(batch)
            if not batch or start >= total or start >= MAX_WINDOW:
                break
        if total >= MAX_WINDOW:
            print(f"    WARN {label}: {total} rows >= {MAX_WINDOW}, may be truncated")
        return records


async def _collect_one(survey_name, survey_period_id, region_group_id, headers, cookies, semaphore, seen,
                       progress=None, period_name=""):
    myinfo = (await _get(myinfo_url + survey_period_id, headers, cookies)).json().get("data", {})
    prov_codes = myinfo.get("regionId") or []
    lv1 = (await _get(region_level1_url + region_group_id, headers, cookies)).json().get("data", [])
    prov_by_code = {r.get("fullCode"): r for r in lv1}

    tasks = []
    for prov_code in prov_codes:
        prov = prov_by_code.get(prov_code)
        if not prov:
            continue
        kab_list = (await _get(region_level2_url + region_group_id + "&level1Id=" + prov["id"],
                               headers, cookies)).json().get("data", [])
        if kab_list:
            for kab in kab_list:
                label = f"{prov.get('name')} / {kab.get('name')}"
                tasks.append(_collect_partition(survey_name, survey_period_id, prov["id"], kab["id"],
                                                label, headers, cookies, semaphore, seen, period_name))
        else:
            tasks.append(_collect_partition(survey_name, survey_period_id, prov["id"], None,
                                            prov.get("name"), headers, cookies, semaphore, seen, period_name))

    total = len(tasks)
    done = 0

    async def _run(coro):
        nonlocal done
        try:
            return await coro
        finally:
            done += 1
            if progress:
                progress(done, total)

    results = await asyncio.gather(*[_run(t) for t in tasks])
    records = [rec for lst in results for rec in lst]
    print(f"  data-tab | {survey_name}: {len(records)} rows")
    return records


async def _survey_periods(survey_id, headers, cookies):
    """All periods for a survey (name + id), oldest first. Empty if lookup fails."""
    if not isinstance(survey_id, str) or not survey_id:
        return []
    try:
        data = (await _get(survey_periods_url + survey_id, headers, cookies)).json().get("data") or []
    except Exception as e:
        print(f"    WARN periods lookup failed for {survey_id}: {e}")
        return []
    data = [p for p in data if isinstance(p.get("id"), str)]
    data.sort(key=lambda p: (p.get("startDate") or "", p.get("name") or ""))
    return data


async def collect_data_tab(survey_collection_df, names, headers, cookies, progress=None):
    _ensure_limiter()
    semaphore = asyncio.Semaphore(int(os.getenv("FASIH_DATA_TAB_CONCURRENCY", "3")))
    seen = set()
    frames = []
    for _, s in survey_collection_df.iterrows():
        if s["name"] not in names:
            continue
        gid = s.get("regionGroupId")
        if not isinstance(gid, str):
            continue
        # Scrape every period the survey has (a survey can span Triwulan/Month
        # periods); each row is tagged with its period name so it shows as a filter.
        periods = await _survey_periods(s.get("id"), headers, cookies)
        if not periods:
            spid = s.get("survey_period_id")
            periods = [{"id": spid, "name": ""}] if isinstance(spid, str) else []
        for p in periods:
            records = await _collect_one(s["name"], p["id"], gid, headers, cookies, semaphore, seen,
                                         progress, period_name=p.get("name") or "")
            if records:
                frames.append(pd.DataFrame(records))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


async def collect_period(survey_name, survey_period_id, region_group_id, headers, cookies,
                         period_name="", progress=None):
    """Scrape a single survey period on demand (the server's picker flow)."""
    _ensure_limiter()
    semaphore = asyncio.Semaphore(int(os.getenv("FASIH_DATA_TAB_CONCURRENCY", "3")))
    seen = set()
    records = await _collect_one(survey_name, survey_period_id, region_group_id, headers, cookies,
                                 semaphore, seen, progress, period_name=period_name)
    return pd.DataFrame(records) if records else pd.DataFrame()


def save_data_tab(df):
    os.makedirs("outputs/csv", exist_ok=True)
    ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    df.to_csv(f"outputs/csv/data_sample_{ts}.csv", index=False)
    df.to_csv(OUTPUT_CSV, index=False)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"generated": ts, "rows": df.to_dict(orient="records")}, f, ensure_ascii=False)
    print(f"  saved {OUTPUT_CSV} + {OUTPUT_JSON} ({len(df)} rows)")


def main():
    from survey_selector import load_survey_config
    df = pd.read_csv("outputs/csv/survey_collection_deadline_adjusted.csv")
    names = [e["name"] for e in load_survey_config() if e.get("type") == "pencacahan"]
    cookies, csrf = get_cookies_and_csrf()
    headers = {**BASE_HEADERS, "X-XSRF-TOKEN": csrf}
    data_df = asyncio.run(collect_data_tab(df, names, headers, cookies))
    if not data_df.empty:
        save_data_tab(data_df)
    else:
        print("  no data-tab rows collected")
    from dashboard import build_dashboard
    build_dashboard()


if __name__ == "__main__":
    main()
