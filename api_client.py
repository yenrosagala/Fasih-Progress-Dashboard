# api_client.py
import httpx
import asyncio
import random
import os

_REQUEST_INTERVAL = float(os.getenv("FASIH_REQUEST_INTERVAL", "0"))
_request_lock = asyncio.Lock()
_last_request_at = 0.0

# Network-level errors that are safe to retry
_RETRYABLE_ERRORS = (
    httpx.ReadError,
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

def _make_client(timeout: float) -> httpx.AsyncClient:
    """
    Create an AsyncClient that:
    - Forces HTTP/1.1  (FASIH server does not advertise HTTP/2
      via ALPN, which causes ReadError when httpx defaults to h2)
    - Uses a split timeout: short connect phase, generous read phase
    """
    t = httpx.Timeout(timeout, connect=15.0)
    return httpx.AsyncClient(http2=False, timeout=t)


class BotBlockError(RuntimeError):
    pass


async def _throttle():
    global _last_request_at
    async with _request_lock:
        now = asyncio.get_running_loop().time()
        wait_for = _REQUEST_INTERVAL - (now - _last_request_at)
        if wait_for > 0:
            await asyncio.sleep(wait_for)
        _last_request_at = asyncio.get_running_loop().time()


def _raise_for_bot_block(response: httpx.Response):
    body = response.text[:2000].lower()
    if "bot-" in body or "sistem kami mendeteksi koneksi anda sebagai bot" in body:
        raise BotBlockError(
            "BPS/FASIH returned a bot-detection page. Stop running the script, "
            "open FASIH manually in a normal browser, and report the BOT code via HaloSIS if needed."
        )


async def post_requests(url, headers, cookies, payload, timeout=90, max_retries=5, base_delay=2):
    for attempt in range(max_retries):
        try:
            async with _make_client(timeout) as client:
                await _throttle()
                response = await client.post(url, headers=headers, cookies=cookies, json=payload)
                _raise_for_bot_block(response)
                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"⏳ HTTP {response.status_code} received, retrying in {delay:.1f}s "
                          f"(attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(delay)
                    continue
                if response.status_code == 405 and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"⏳ 405 received, retrying in {delay}s (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                return response
        except _RETRYABLE_ERRORS as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"⚠️  Network error ({type(e).__name__}), retrying in {delay:.1f}s "
                      f"(attempt {attempt + 1}/{max_retries})...")
                await asyncio.sleep(delay)
            else:
                print(f"❌ Network error after {max_retries} attempts: {e}")
                raise


async def get_requests(url, headers, cookies, params=None, timeout=90, max_retries=5, base_delay=2):
    for attempt in range(max_retries):
        try:
            async with _make_client(timeout) as client:
                await _throttle()
                response = await client.get(url, headers=headers, cookies=cookies, params=params)
                _raise_for_bot_block(response)
                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"⏳ HTTP {response.status_code} received, retrying in {delay:.1f}s "
                          f"(attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(delay)
                    continue
                if response.status_code == 405 and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"⏳ 405 received, retrying in {delay}s (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                return response
        except _RETRYABLE_ERRORS as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"⚠️  Network error ({type(e).__name__}), retrying in {delay:.1f}s "
                      f"(attempt {attempt + 1}/{max_retries})...")
                await asyncio.sleep(delay)
            else:
                print(f"❌ Network error after {max_retries} attempts: {e}")
                raise
