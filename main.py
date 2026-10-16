import pandas as pd
import asyncio
import argparse
import os
import time
from importer import get_cookies_and_csrf, get_payload, COOKIE_CACHE_PATH
from config import (
    BASE_HEADERS,
    payload_survey,
    survey_datatable_url,
    surveys_base_url,
    survey_periods_url,
    myinfo_url,
    region_level1_url,
    report_progress_assignment_url,
    report_user_assignment_url,
    progress_status_order,
    assignment_status_order,
    pemutakhiran_base_url,
    pemutakhiran_payload,
    pemutakhiran_status_order,
)
from api_client import post_requests, get_requests
from adjust_survey import adjust_period, adjust_sample, adjust_deadline
from transformer import json_to_df, pemutakhiran_json_to_df
from data_loader import get_survey_name
from plotter import generate_plots_2, generate_kabupaten_status_donut_dashboard
from survey_selector import select_surveys, select_survey_periods
from generate_pivot import main as generate_pivot

async def main():
    os.makedirs("outputs/csv", exist_ok=True)
    start_time = time.time()

    cookies, csrf_token = get_cookies_and_csrf()
    headers = {**BASE_HEADERS, "X-XSRF-TOKEN": csrf_token}

    # Fetch survey list (POST)
    response = await post_requests(survey_datatable_url, headers, cookies, payload_survey)
    json_data = response.json()

    survey_collection_df = pd.DataFrame(json_data['data']['content'])

    # Let user pick which surveys to scrape and tag their type
    survey_config = await select_surveys(survey_collection_df['name'].tolist())
    selected_names = [e['name'] for e in survey_config]
    pencacahan_names = [e['name'] for e in survey_config if e['type'] == 'pencacahan']
    pemutakhiran_names = [e['name'] for e in survey_config if e['type'] == 'pemutakhiran']

    survey_collection_df = survey_collection_df[
        survey_collection_df['name'].isin(selected_names)
    ].reset_index(drop=True)

    survey_id_dict = {i: j for i, j in zip(survey_collection_df['id'], survey_collection_df['name'])}
    for col in ["regionGroupId", "survey_period_id", "startDate", "endDate"]:
        if col not in survey_collection_df.columns:
            survey_collection_df[col] = pd.NA

    max_concurrency = int(os.getenv("FASIH_MAX_CONCURRENCY", "10"))
    semaphore = asyncio.Semaphore(max_concurrency)
    print(f"🌐 Request concurrency: {max_concurrency}")

    # Load previously saved survey collection to compare dates
    _prev_csv = "outputs/csv/survey_collection_deadline_adjusted.csv"
    prev_survey_df = pd.read_csv(_prev_csv) if os.path.exists(_prev_csv) else pd.DataFrame()
    date_changes = []

    def fmt(d):
        try:
            return pd.to_datetime(d).strftime('%d %b %Y')
        except:
            return str(d)

    survey_metadata = {}
    periods_by_survey = {}

    # Fetch metadata (GET) concurrently
    async def fetch_metadata(i, j):
        async with semaphore:
            try:
                survey_response, periods_response = await asyncio.gather(
                    get_requests(surveys_base_url + str(i), headers=headers, cookies=cookies),
                    get_requests(survey_periods_url + str(i), headers=headers, cookies=cookies),
                )
                survey_data = survey_response.json()["data"]
                periods = periods_response.json()["data"]
                survey_metadata[j] = survey_data
                periods_by_survey[j] = periods

                print(f"✅ Status 200 | {j}")
            except Exception as e:
                print(f"❌ Error for {j}: {e}")

    # Run all metadata requests concurrently
    tasks = [fetch_metadata(i, j) for i, j in survey_id_dict.items()]
    await asyncio.gather(*tasks)

    survey_config = await select_survey_periods(survey_config, periods_by_survey)
    selected_names = [e['name'] for e in survey_config]
    pencacahan_names = [e['name'] for e in survey_config if e['type'] == 'pencacahan']
    pemutakhiran_names = [e['name'] for e in survey_config if e['type'] == 'pemutakhiran']
    config_by_name = {entry["name"]: entry for entry in survey_config}

    for survey_id, survey_name in survey_id_dict.items():
        survey_data = survey_metadata.get(survey_name)
        periods = periods_by_survey.get(survey_name, [])
        selected_period_id = config_by_name.get(survey_name, {}).get("surveyPeriodId")
        selected_period = next(
            (period for period in periods if period.get("id") == selected_period_id),
            None,
        )
        if not survey_data or not selected_period:
            continue

        new_start = selected_period["startDate"]
        new_end = selected_period["endDate"]

        survey_collection_df.loc[
            survey_collection_df["id"] == survey_id,
            ["regionGroupId", "survey_period_id", "startDate", "endDate"]
        ] = [
            survey_data["regionGroupId"],
            selected_period["id"],
            new_start,
            new_end,
        ]

        # Collect date changes to print in summary later
        if not prev_survey_df.empty and 'name' in prev_survey_df.columns:
            prev_row = prev_survey_df[prev_survey_df['name'] == survey_name]
            if not prev_row.empty:
                old_start = prev_row['startDate'].values[0]
                old_end = prev_row['endDate'].values[0]
                if str(old_start) != str(new_start) or str(old_end) != str(new_end):
                    date_changes.append((survey_name, old_start, old_end, new_start, new_end))

    missing_period_mask = survey_collection_df['survey_period_id'].isna()
    if missing_period_mask.any():
        skipped_names = survey_collection_df.loc[missing_period_mask, 'name'].tolist()
        print("\n⚠️ Skipping surveys with missing metadata after retries:")
        for name in skipped_names:
            print(f"  - {name}")
        survey_collection_df = survey_collection_df.loc[~missing_period_mask].reset_index(drop=True)
        pencacahan_names = [name for name in pencacahan_names if name in survey_collection_df['name'].tolist()]
        pemutakhiran_names = [name for name in pemutakhiran_names if name in survey_collection_df['name'].tolist()]

    if survey_collection_df.empty:
        raise RuntimeError("No selected surveys have usable metadata. Try again later or select fewer surveys.")

    # Update period and save
    try:
        survey_collection_df = adjust_period(survey_collection_df)
    except Exception as e:
        print(f"⚠️ adjust_period() failed: {e}")
        # You could log the traceback if needed
        import traceback
        traceback.print_exc()
    finally:
        timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
        survey_collection_df.to_csv(f"outputs/csv/survey_collection_{timestamp}.csv", index=False)
        print("\n📁 Data saved to output folder.\n")

    # Get province sample for each survey asynchronously with semaphore
    prov_sampel = {}

    async def fetch_prov_sample(surveyPeriodId):
        async with semaphore:
            url = myinfo_url + surveyPeriodId
            response = await get_requests(url, headers, cookies)
            json_data = response.json()['data']
            groupId = survey_collection_df.loc[survey_collection_df['survey_period_id']==surveyPeriodId, 'regionGroupId']
            prov_sampel[surveyPeriodId] = json_data['regionId']
            print(f"Survey Period ID: {surveyPeriodId}, Group ID: {groupId.values[0]}, Region ID: {json_data['regionId']}")

    pencacahan_period_ids = survey_collection_df.loc[
        survey_collection_df['name'].isin(pencacahan_names), 'survey_period_id'
    ].tolist()
    prov_tasks = [fetch_prov_sample(surveyPeriodId) for surveyPeriodId in pencacahan_period_ids]
    await asyncio.gather(*prov_tasks)

    rows = []

    # Fetch region1_id concurrently with semaphore
    async def fetch_region1_id(surveyPeriodId, prov_id):
        async with semaphore:
            response = None
            try:
                groupId = survey_collection_df.loc[survey_collection_df['survey_period_id'] == surveyPeriodId, 'regionGroupId'].iloc[0]
                url = region_level1_url + groupId
                response = await get_requests(url, headers=headers, cookies=cookies)

                if not response.content:
                    print(f"⚠️  Empty response for surveyPeriodId={surveyPeriodId}, prov_id={prov_id} — skipping.")
                    return None

                json_data = response.json()
                level1_df = pd.DataFrame(json_data['data'])
                matches = level1_df.loc[level1_df['fullCode'] == prov_id, 'id']
                if matches.empty:
                    print(f"⚠️  No region match for prov_id={prov_id} in surveyPeriodId={surveyPeriodId} — skipping.")
                    return None
                region1_id = matches.iloc[0]
                print(f"Processed survey period ID {surveyPeriodId}: {prov_id} - Region 1 ID: {region1_id}")
                return {
                    'surveyPeriodId': surveyPeriodId,
                    'prov_id': prov_id,
                    'region1Id': region1_id
                }
            except Exception as e:
                import traceback
                raw_body = response.text[:300] if response is not None else "<no response>"
                print(
                    f"❌ Error in fetch_region1_id(surveyPeriodId={surveyPeriodId}, prov_id={prov_id})\n"
                    f"   Exception type : {type(e).__name__}\n"
                    f"   Exception msg  : {e}\n"
                    f"   HTTP status    : {response.status_code if response is not None else 'N/A'}\n"
                    f"   Response body  : {raw_body}\n"
                    f"   Traceback:\n{traceback.format_exc()}"
                )
                return None

    region1_tasks = []
    for surveyPeriodId, prov_list in prov_sampel.items():
        if prov_list is None:
            continue
        for prov_id in prov_list:
            region1_tasks.append(fetch_region1_id(surveyPeriodId, prov_id))
    region1_results = await asyncio.gather(*region1_tasks)
    rows.extend([r for r in region1_results if r is not None])

    temp_df = pd.DataFrame(rows)


    urls = [report_progress_assignment_url, report_user_assignment_url]
    report_assignment_df = pd.DataFrame()

    async def fetch_progress_assignment(rowx, url):
        async with semaphore:
            await asyncio.sleep(0.3)
            region1Id = rowx['region1Id']
            surveyPeriodId = rowx['surveyPeriodId']
            prov_id = rowx.get('prov_id', 'unknown')
            survey_name = get_survey_name(survey_collection_df, surveyPeriodId)

            try:
                payload = get_payload(region1Id, surveyPeriodId)
                response = await post_requests(url, headers, cookies, payload)
                print(f"Status {response.status_code} | {survey_name} - {prov_id}")

                if response.status_code != 200:
                    print(f"❌ Failed for {survey_name}, {prov_id}")
                    return None

                tab = json_to_df(response.json(), prov_id, survey_name)
                tab["type"] = "user_assignment" if url == report_user_assignment_url else "progress"
                return tab

            except Exception as e:
                print(f"❗Error processing {survey_name} ({prov_id}): {e}")
                return None

    # Run both URLs concurrently — each URL has its own rate limit so interleaving reduces per-URL burst
    print(f"\n🚀 Fetching data from {urls[0]} and {urls[1]} concurrently...")
    report_tasks = [
        fetch_progress_assignment(rowx, url)
        for url in urls
        for _, rowx in temp_df.iterrows()
    ]
    report_results = await asyncio.gather(*report_tasks)
    report_results = [r for r in report_results if r is not None]
    if report_results:
        report_assignment_df = pd.concat([report_assignment_df, *report_results], ignore_index=True)

    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
    # Adjustment for Sampel and Deadlines
    try:
        report_assignment_df = adjust_sample(report_assignment_df)
        survey_collection_df = adjust_deadline(survey_collection_df)
    except Exception as e:
        print(f"⚠️ Adjustment step failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        report_assignment_df.to_csv(f"outputs/csv/report_assignment_{timestamp}.csv", index=False)
        report_assignment_df.to_csv(f"outputs/csv/report_assignment.csv", index=False)
        survey_collection_df.to_csv(f"outputs/csv/survey_collection_deadline_adjusted.csv", index=False)
        print(f"\n📁 Data saved to output folder.\n")

    # Pemutakhiran flow
    report_pemutakhiran_df = pd.DataFrame()
    if pemutakhiran_names:
        print("\n🚀 Fetching pemutakhiran data...")

        async def fetch_pemutakhiran(survey_name, survey_period_id):
            async with semaphore:
                url = pemutakhiran_base_url + survey_period_id
                try:
                    response = await post_requests(url, headers, cookies, pemutakhiran_payload)
                    print(f"Status {response.status_code} | {survey_name}")
                    if response.status_code != 200:
                        print(f"❌ Failed pemutakhiran: {survey_name}")
                        return None
                    data = response.json().get('data', [])
                    tab = pemutakhiran_json_to_df(data, survey_name)
                    return tab
                except Exception as e:
                    print(f"❗ Error pemutakhiran {survey_name}: {e}")
                    return None

        pemutakhiran_rows = survey_collection_df[
            survey_collection_df['name'].isin(pemutakhiran_names)
        ][['name', 'survey_period_id']].itertuples(index=False)

        pemutakhiran_tasks = [
            fetch_pemutakhiran(row.name, row.survey_period_id)
            for row in pemutakhiran_rows
        ]
        pemutakhiran_results = await asyncio.gather(*pemutakhiran_tasks)
        pemutakhiran_results = [r for r in pemutakhiran_results if r is not None]
        if pemutakhiran_results:
            report_pemutakhiran_df = pd.concat(pemutakhiran_results, ignore_index=True)
            report_pemutakhiran_df.to_csv(f"outputs/csv/report_pemutakhiran_{timestamp}.csv", index=False)
            print(f"\n📁 Pemutakhiran data saved.\n")

    # Always overwrite the canonical pemutakhiran CSV so stale data from a
    # previous run never leaks into the pivot report on the next run.
    report_pemutakhiran_df.to_csv("outputs/csv/report_pemutakhiran.csv", index=False)

    # Plot combined chart (pencacahan + pemutakhiran together)
    survey_collection_df = pd.read_csv('outputs/csv/survey_collection_deadline_adjusted.csv')
    combined_progress_df = pd.DataFrame()

    if pencacahan_names:
        report_assignment_df = pd.read_csv('outputs/csv/report_assignment.csv')
        progress_assignment_df = report_assignment_df[report_assignment_df['type'] == "progress"].copy()
        user_assignment_df = report_assignment_df[report_assignment_df['type'] != "progress"].copy()
        combined_progress_df = pd.concat([combined_progress_df, progress_assignment_df], ignore_index=True)
        generate_plots_2(user_assignment_df, survey_collection_df, assignment_status_order, 2, pencacahan_names)

    if not report_pemutakhiran_df.empty:
        combined_progress_df = pd.concat([combined_progress_df, report_pemutakhiran_df], ignore_index=True)

    if not combined_progress_df.empty:
        combined_status_order = progress_status_order + pemutakhiran_status_order
        generate_plots_2(combined_progress_df, survey_collection_df, combined_status_order, 1, selected_names)
        generate_kabupaten_status_donut_dashboard(
            combined_progress_df,
            survey_collection_df,
            combined_status_order,
            selected_names,
        )



    generate_pivot()

    if pencacahan_names:
        from data_tab import collect_data_tab, save_data_tab
        from dashboard import build_dashboard
        from build_site import build_site

        print("\n>> Fetching data-tab sample list...")
        data_df = await collect_data_tab(
            survey_collection_df, pencacahan_names, headers, cookies
        )
        if not data_df.empty:
            save_data_tab(data_df)
            build_dashboard()
            build_site()

    if date_changes:
        print("\n📋 Survey Period Changes:")
        for name, old_start, old_end, new_start, new_end in date_changes:
            print(f"  • {name}")
            print(f"    {fmt(new_start)} – {fmt(new_end)}  →  {fmt(old_start)} – {fmt(old_end)}")

    end_time = time.time()
    duration = end_time - start_time
    minutes = int(duration // 60)
    seconds = int(duration % 60)
    print(f"\n⏱️  Scraping completed in {minutes}m {seconds}s")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--relogin", action="store_true", help="Force fresh login, ignoring cached session")
    parser.add_argument("--title", type=str, help="Set the primary chart title (saved for future runs)")
    parser.add_argument("--user-title", type=str, help="Set the user assignment chart title (saved for future runs)")
    parser.add_argument("--kab-status-title", type=str, help="Set the kabupaten status donut chart title (saved for future runs)")
    args = parser.parse_args()

    if args.relogin and os.path.exists(COOKIE_CACHE_PATH):
        os.remove(COOKIE_CACHE_PATH)
        print("🗑️  Cached session cleared.\n")

    if args.title or args.user_title or args.kab_status_title:
        import json
        from survey_selector import CONFIG_PATH
        cfg = json.load(open(CONFIG_PATH)) if os.path.exists(CONFIG_PATH) else {}
        if args.title:
            cfg["chart_title"] = args.title
            print(f"📝 Chart title set to: {args.title}\n")
        if args.user_title:
            cfg["user_assignment_title"] = args.user_title
            print(f"📝 User assignment title set to: {args.user_title}\n")
        if args.kab_status_title:
            cfg["kabupaten_status_title"] = args.kab_status_title
            print(f"📝 Kabupaten status chart title set to: {args.kab_status_title}\n")
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    asyncio.run(main())
