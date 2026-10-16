#!/usr/bin/env python3
import argparse
import json
import platform
import shutil
import subprocess
from pathlib import Path


OUTPUT_PATH = Path("inputs/manual_session.json")


def parse_cookie_header(cookie_header: str) -> dict[str, str]:
    cookies = {}
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = value.strip()
    return cookies


def extract_csrf_token(cookies: dict[str, str]) -> str | None:
    for name, value in cookies.items():
        if name.lower() in {"x-xsrf-token", "xsrf-token"}:
            return value
    return None


def read_clipboard() -> str:
    system = platform.system().lower()
    if system == "darwin":
        command = ["pbpaste"]
    elif system == "windows":
        command = ["powershell", "-NoProfile", "-Command", "Get-Clipboard"]
    else:
        if shutil.which("pbpaste") is not None:
            command = ["pbpaste"]
        elif shutil.which("xclip") is not None:
            command = ["xclip", "-selection", "clipboard", "-o"]
        elif shutil.which("xsel") is not None:
            command = ["xsel", "--clipboard", "--output"]
        else:
            raise RuntimeError(
                "Clipboard command not available; pass --cookie-header or pipe the header on stdin."
            )

    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create inputs/manual_session.json from a Cookie header.")
    parser.add_argument("--cookie-header", help="Raw Cookie header copied from DevTools.")
    parser.add_argument("--from-clipboard", action="store_true", help="Read the Cookie header from the clipboard.")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Output JSON path.")
    args = parser.parse_args()

    cookie_header = args.cookie_header
    if not cookie_header and args.from_clipboard:
        cookie_header = read_clipboard()
    if not cookie_header and not args.from_clipboard:
        cookie_header = read_clipboard()
    if not cookie_header:
        cookie_header = input().strip()

    cookie_header = cookie_header.strip()
    if not cookie_header:
        raise SystemExit("Empty Cookie header.")

    cookies = parse_cookie_header(cookie_header)
    payload = {"cookie_header": cookie_header}
    if cookies:
        payload["cookies"] = cookies
    csrf_token = extract_csrf_token(cookies)
    if csrf_token:
        payload["csrf_token"] = csrf_token

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    print(f"Wrote {output_path}")
    print(f"Cookies parsed: {len(cookies)}")
    print(f"CSRF token present: {bool(csrf_token)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
