"""AI backend for the Progress tab summary (OpenRouter).

One backend keeps this simple: OpenRouter's OpenAI-compatible chat completions
endpoint, with a model fallback list. Reads env at call time so tests can patch
it. Only pre-aggregated numbers are ever sent from the dashboard.
"""
import os
import time

import httpx

URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODELS = ["openai/gpt-4o-mini"]
# App attribution headers OpenRouter recommends; some routes throttle without them.
HEADERS = {"HTTP-Referer": "http://localhost:8080", "X-Title": "FASIH Dashboard"}
# A reply shorter than this is junk (a routed model emitting a guard string like
# "User Safety: safe"); try the next model instead.
MIN_TEXT = 40


class AuthError(RuntimeError):
    """Credential rejected (401/403) - the key itself is bad, don't retry it."""


def api_key():
    return os.getenv("OPENROUTER_API_KEY", "")


def models():
    raw = (os.getenv("OPENROUTER_MODELS") or "").replace("\n", ",")
    return [m.strip() for m in raw.split(",") if m.strip()] or list(DEFAULT_MODELS)


def enabled():
    return bool(api_key())


async def summarize(prompt, attempt_timeout=30, total_timeout=60):
    """Return (text, backend_label). Models are tried in order; first usable reply wins.

    Each attempt is capped at attempt_timeout and the whole chain at total_timeout,
    so a slow or hanging model can't make one click wait for minutes.
    """
    key = api_key()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY belum diset")
    deadline = time.monotonic() + total_timeout
    errors = []
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **HEADERS}
    async with httpx.AsyncClient(timeout=attempt_timeout) as client:
        for model in models():
            if time.monotonic() > deadline:
                raise RuntimeError(f"Waktu habis ({total_timeout}s). " + " | ".join(errors[-2:]))
            try:
                body = {"model": model, "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 700}
                r = await client.post(URL, json=body, headers=headers)
                if r.status_code in (401, 403):
                    raise AuthError(f"openrouter HTTP {r.status_code}: kunci ditolak")
                if r.status_code != 200:
                    raise RuntimeError(f"openrouter {model} HTTP {r.status_code}: {r.text[:160]}")
                ch = (r.json() or {}).get("choices") or []
                text = (ch[0].get("message", {}).get("content") or "").strip() if ch else ""
                if len(text) < MIN_TEXT:
                    raise RuntimeError(f"openrouter {model}: respons kosong/terlalu pendek ({len(text)} chars)")
                return text, f"openrouter:{model}"
            except AuthError:
                raise
            except Exception as e:  # noqa: BLE001 - try the next model
                errors.append(str(e))
    raise RuntimeError("Semua model AI gagal. " + " | ".join(errors[-3:]))
