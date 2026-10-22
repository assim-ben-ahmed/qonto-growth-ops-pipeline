"""Small client for the public French company API (recherche-entreprises.api.gouv.fr).

Three production habits in ~60 lines:
- rate limiting (never more than N requests per second),
- a local JSON cache (reruns don't hit the API again),
- retries with backoff on 429 / 5xx / network errors.
"""
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)


class CompanyApiClient:
    def __init__(self, base_url: str, cache_dir: Path, max_rps: float = 5,
                 timeout: float = 10, max_retries: int = 3) -> None:
        self.base_url = base_url
        self.cache_dir = cache_dir
        self.min_interval = 1.0 / max_rps
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_call = 0.0
        self.stats = {"api_calls": 0, "cache_hits": 0, "errors": 0}

    def _cache_path(self, key: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", key)
        return self.cache_dir / f"{safe}.json"

    def _wait_for_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()

    def get(self, params: dict[str, Any], cache_key: str) -> dict[str, Any] | None:
        """GET the API with caching. Returns the JSON body, or None if every retry failed."""
        path = self._cache_path(cache_key)
        if path.exists():
            self.stats["cache_hits"] += 1
            return json.loads(path.read_text(encoding="utf-8"))

        for attempt in range(1, self.max_retries + 1):
            self._wait_for_rate_limit()
            try:
                self.stats["api_calls"] += 1
                resp = requests.get(self.base_url, params=params, timeout=self.timeout)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                body = resp.json()
                path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
                return body
            except (requests.RequestException, ValueError) as exc:
                wait = 2 ** attempt  # 2s, 4s, 8s
                log.warning("API error for %s (attempt %d/%d): %s - retrying in %ds",
                            cache_key, attempt, self.max_retries, exc, wait)
                time.sleep(wait)

        self.stats["errors"] += 1
        log.error("Giving up on %s after %d attempts", cache_key, self.max_retries)
        return None
