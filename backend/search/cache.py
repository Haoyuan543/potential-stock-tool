from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CACHE_FILE = ROOT / "data" / "search_cache.json"
TZ = timezone(timedelta(hours=8))


class SearchCache:
    def __init__(self, ttl_minutes: int = 30) -> None:
        self.ttl = timedelta(minutes=ttl_minutes)

    def get(self, key: str) -> dict[str, Any] | None:
        rows = self._load()
        row = rows.get(key)
        if not row:
            return None
        try:
            timestamp = datetime.fromisoformat(row["timestamp"])
        except Exception:
            return None
        if datetime.now(TZ) - timestamp > self.ttl:
            return None
        return row.get("value")

    def set(self, key: str, value: dict[str, Any]) -> None:
        rows = self._load()
        rows[key] = {"timestamp": datetime.now(TZ).isoformat(), "value": value}
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> dict[str, Any]:
        if not CACHE_FILE.exists():
            return {}
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
