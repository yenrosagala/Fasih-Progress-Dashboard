"""Push the scraped dashboard data to the private Cloud data repo.

After the dashboard scrapes locally, run this: it mirrors outputs/site's data
(surveys.json + data/*.json) into a private GitHub repo. The Streamlit Cloud app
reads that repo (secrets DATA_REPO + DATA_TOKEN) and serves it, so Cloud never
needs its own FASIH cookie -- the local browser bridge supplies the session.

    python publish_data.py

Env overrides: FASIH_DATA_DIR (local clone, default ../fasih-data),
FASIH_DATA_REPO (default yenrosagala/fasih-data), FASIH_DATA_URL (clone URL,
default https://github.com/<repo>.git), FASIH_SITE_DIR (default outputs/site).
"""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _git(dest, *args):
    return subprocess.run(["git", *args], cwd=dest, check=True, text=True,
                          stdout=subprocess.DEVNULL)


def main():
    site = Path(os.getenv("FASIH_SITE_DIR") or ROOT / "outputs" / "site")
    dest = Path(os.getenv("FASIH_DATA_DIR") or ROOT.parent / "fasih-data")
    repo = os.getenv("FASIH_DATA_REPO", "yenrosagala/fasih-data")
    url = os.getenv("FASIH_DATA_URL") or f"https://github.com/{repo}.git"

    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", url, str(dest)], check=True)
        _git(dest, "checkout", "-B", "main")  # pin the branch Cloud reads
    if not (site / "surveys.json").exists():
        raise SystemExit(f"{site}/surveys.json not found -- scrape first")

    (dest / "data").mkdir(exist_ok=True)
    for src in (site / "data").glob("*.json"):
        shutil.copy2(src, dest / "data" / src.name)
    shutil.copy2(site / "surveys.json", dest / "surveys.json")

    _git(dest, "add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=dest).returncode == 0:
        print("publish_data: no changes")
        return
    # One commit, force-pushed: the repo is data-only, and snapshots are large
    # (~23 MB) so accumulating versions would bloat it fast. Rewrites are fine here.
    has_commit = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"], cwd=dest,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0
    if has_commit:
        _git(dest, "commit", "--amend", "--no-edit")
    else:
        _git(dest, "commit", "-m", "FASIH data")
    _git(dest, "push", "-f", "origin", "main")
    print(f"publish_data: pushed to {repo}")


if __name__ == "__main__":
    main()
