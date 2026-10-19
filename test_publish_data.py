"""Self-check for publish_data against a local bare repo (no network).

Runs main() twice with changed data and asserts the pushed branch is `main`,
the JSON lands where Cloud reads it, and history stays a single commit (the
force-push that keeps the private data repo from bloating).

Run: python test_publish_data.py
"""

import os
import subprocess
import tempfile
from pathlib import Path

import publish_data


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                          capture_output=True).stdout


def test_publish():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        remote = tmp / "remote.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)],
                       check=True, capture_output=True)
        site = tmp / "site"
        (site / "data").mkdir(parents=True)
        (site / "surveys.json").write_text('{"surveys":[1]}', encoding="utf-8")
        (site / "data" / "x.json").write_text('{"rows":1}', encoding="utf-8")

        os.environ.update(
            FASIH_SITE_DIR=str(site),
            FASIH_DATA_DIR=str(tmp / "clone"),
            FASIH_DATA_URL=str(remote),
        )
        try:
            publish_data.main()
            # Cloud reads branch `main`; the data files are where _sync_data looks.
            assert _git(remote, "branch", "--list", "main").strip()
            assert _git(remote, "show", "main:surveys.json").strip() == '{"surveys":[1]}'
            assert _git(remote, "show", "main:data/x.json").strip() == '{"rows":1}'

            (site / "data" / "x.json").write_text('{"rows":2}', encoding="utf-8")
            publish_data.main()
            assert _git(remote, "rev-list", "--count", "main").strip() == "1", \
                "second push must amend, not grow the data repo"
            assert _git(remote, "show", "main:data/x.json").strip() == '{"rows":2}'
        finally:
            for k in ("FASIH_SITE_DIR", "FASIH_DATA_DIR", "FASIH_DATA_URL"):
                os.environ.pop(k, None)
    print("ok: publish_data mirrors data to branch `main` and keeps one commit")


if __name__ == "__main__":
    test_publish()
