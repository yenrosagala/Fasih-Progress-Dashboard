import json
import os
from datetime import date
from InquirerPy import inquirer

CONFIG_PATH = "inputs/survey_config.json"


def load_survey_config() -> list:
    """Returns list of {name, type} dicts."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            entries = json.load(f).get("selected_surveys", [])
        # Handle old format (list of strings)
        if entries and isinstance(entries[0], str):
            return [{"name": n, "type": "pencacahan"} for n in entries]
        return entries
    return []


def load_selected_surveys() -> list:
    """Returns list of selected survey names (backward compat for plotter.py)."""
    return [entry["name"] for entry in load_survey_config()]


def save_survey_config(config: list):
    os.makedirs("inputs", exist_ok=True)
    # Preserve existing top-level fields (e.g. chart_title) when re-saving
    existing = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            existing = json.load(f)

    # Persist survey details (other_jadwal, startDate, endDate, title) in a
    # backup dict keyed by survey name so they survive account switches.
    detail_keys = (
        "title",
        "startDate",
        "endDate",
        "other_jadwal",
        "surveyPeriodId",
        "surveyPeriodName",
        "surveyPeriodStartDate",
        "surveyPeriodEndDate",
    )
    backup = existing.get("_survey_details_backup", {})
    for entry in existing.get("selected_surveys", []):
        name = entry.get("name")
        if name:
            details = {k: entry[k] for k in detail_keys if k in entry}
            if details:
                backup[name] = {**backup.get(name, {}), **details}
    for entry in config:
        name = entry.get("name")
        if name:
            details = {k: entry[k] for k in detail_keys if k in entry}
            if details:
                backup[name] = {**backup.get(name, {}), **details}

    existing.update({
        "selected_surveys": config,
        "last_updated": str(date.today()),
        "_survey_details_backup": backup,
    })
    with open(CONFIG_PATH, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


async def select_surveys(all_surveys: list) -> list:
    """
    Step 1: Checkbox to pick which surveys to monitor.
    Step 2: Checkbox to tag which of those are pemutakhiran (rest = pencacahan).
    Returns list of {name, type} dicts. Saves to survey_config.json.
    """
    prev_config = {entry["name"]: entry["type"] for entry in load_survey_config()}

    # Step 1: Select surveys
    choices = [
        {"name": name, "value": name, "enabled": name in prev_config}
        for name in all_surveys
    ]

    selected_names = await inquirer.checkbox(
        message="Select surveys to monitor (Space = toggle, A = all, I = invert, Enter = confirm):",
        choices=choices,
        cycle=False,
        transformer=lambda result: f"{len(result)} survey(s) selected",
    ).execute_async()

    if not selected_names:
        print("\n⚠️  No surveys selected.\n")
        return []

    # Step 2: Tag pemutakhiran surveys
    prev_pemutakhiran = {name for name, t in prev_config.items() if t == "pemutakhiran"}
    pemutakhiran_choices = [
        {"name": name, "value": name, "enabled": name in prev_pemutakhiran}
        for name in selected_names
    ]

    pemutakhiran_names = await inquirer.checkbox(
        message="Which of these are PEMUTAKHIRAN? (unchecked = pencacahan, Enter to confirm):",
        choices=pemutakhiran_choices,
        cycle=False,
        transformer=lambda result: f"{len(result)} pemutakhiran tagged",
    ).execute_async()

    # Preserve existing schedule fields (startDate, endDate, other_jadwal) across re-selections.
    # Also pull from _survey_details_backup so fields survive account switches.
    detail_keys = (
        "title",
        "startDate",
        "endDate",
        "other_jadwal",
        "surveyPeriodId",
        "surveyPeriodName",
        "surveyPeriodStartDate",
        "surveyPeriodEndDate",
    )
    existing_cfg = json.load(open(CONFIG_PATH)) if os.path.exists(CONFIG_PATH) else {}
    backup = existing_cfg.get("_survey_details_backup", {})
    prev_schedule = {
        entry["name"]: {k: entry[k] for k in detail_keys if k in entry}
        for entry in load_survey_config()
    }
    for name, details in backup.items():
        if name not in prev_schedule:
            prev_schedule[name] = details

    pemutakhiran_set = set(pemutakhiran_names)
    config = []
    for name in selected_names:
        entry = {"name": name, "type": "pemutakhiran" if name in pemutakhiran_set else "pencacahan"}
        entry.update(prev_schedule.get(name, {}))  # preserves title, startDate, endDate, other_jadwal
        config.append(entry)

    # Step 3: Confirm chart title
    existing_cfg = json.load(open(CONFIG_PATH)) if os.path.exists(CONFIG_PATH) else {}
    current_title = existing_cfg.get("chart_title", "Monitoring Statistik Industri")

    chart_title = await inquirer.text(
        message="Chart title (Enter to keep current):",
        default=current_title,
    ).execute_async()

    # Step 4: Select color palette
    palette_names = ["Ocean", "Professional", "Warm", "Pastel", "Pastel_v2", "Vivid", "Muted", "DarkMode", "HighContrast"]
    current_palette = existing_cfg.get("palette", "Pastel")

    selected_palette = await inquirer.select(
        message="Select color palette for the dashboard:",
        choices=palette_names,
        default=current_palette,
    ).execute_async()

    save_survey_config(config)

    # Save chart title and palette back to top-level config
    with open(CONFIG_PATH) as f:
        full_cfg = json.load(f)
    full_cfg["chart_title"] = chart_title
    full_cfg["palette"] = selected_palette
    with open(CONFIG_PATH, "w") as f:
        json.dump(full_cfg, f, indent=2, ensure_ascii=False)

    pencacahan_count = sum(1 for e in config if e["type"] == "pencacahan")
    pemutakhiran_count = sum(1 for e in config if e["type"] == "pemutakhiran")
    print(f"\n✅ Saved: {pencacahan_count} pencacahan + {pemutakhiran_count} pemutakhiran | Title: {chart_title} | Palette: {selected_palette}\n")
    return config


def _period_sort_key(period):
    return (
        period.get("startDate") or "",
        period.get("endDate") or "",
        period.get("createdAt") or "",
    )


async def select_survey_periods(survey_config: list, periods_by_survey: dict) -> list:
    """
    Let the user choose one survey period per selected survey.
    Stores the chosen period id/name separately from startDate/endDate, which are
    reserved for manual chart deadline overrides.
    """
    updated_config = []

    for entry in survey_config:
        survey_name = entry["name"]
        periods = periods_by_survey.get(survey_name, [])
        if not periods:
            print(f"⚠️  No periods available for {survey_name}; keeping previous period config if any.")
            updated_config.append(entry)
            continue

        periods = sorted(periods, key=_period_sort_key, reverse=True)
        periods_by_id = {period["id"]: period for period in periods}
        previous_period_id = entry.get("surveyPeriodId")
        default_period_id = previous_period_id if previous_period_id in periods_by_id else periods[0]["id"]

        selected_period_id = await inquirer.select(
            message=f"Select period for {survey_name}:",
            choices=[
                {
                    "name": period.get("name") or period["id"],
                    "value": period["id"],
                }
                for period in periods
            ],
            default=default_period_id,
        ).execute_async()

        selected_period = periods_by_id[selected_period_id]
        updated_entry = {
            **entry,
            "surveyPeriodId": selected_period["id"],
            "surveyPeriodName": selected_period.get("name"),
            "surveyPeriodStartDate": selected_period.get("startDate"),
            "surveyPeriodEndDate": selected_period.get("endDate"),
        }
        updated_config.append(updated_entry)

    save_survey_config(updated_config)
    print("\n✅ Survey period choices saved to inputs/survey_config.json\n")
    return updated_config
