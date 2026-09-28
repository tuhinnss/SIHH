"""Shared helpers: polite HTTP (1 req/s, disk cache, backoff)."""
import hashlib
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
CACHE = RAW / "http_cache"
_last = 0.0


def polite_get_json(url: str, params: dict | None = None, retries: int = 5) -> dict:
    """GET JSON with on-disk cache, >=1s between network calls, exponential backoff."""
    global _last
    key = hashlib.sha256((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    CACHE.mkdir(parents=True, exist_ok=True)
    delay = 2.0
    for attempt in range(retries):
        wait = 1.0 - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()
        try:
            r = requests.get(url, params=params, timeout=90,
                             headers={"User-Agent": "SpecSure-SIH26108-prototype"})
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise ValueError(data["error"])
            path.write_text(json.dumps(data))
            return data
        except (requests.RequestException, ValueError):
            if attempt == retries - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")
