from __future__ import annotations

from pathlib import Path
from typing import Any
import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from backend.config import get_settings


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)


class JsonlStore:
    def __init__(self, filename: str) -> None:
        self.path = DATA_DIR / filename

    def append(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def replace_all(self, records: list[dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def clear(self) -> None:
        self.path.write_text("", encoding="utf-8")


class StorageError(RuntimeError):
    pass


class SupabaseJsonStore:
    def __init__(self, store_name: str) -> None:
        self.store_name = store_name

    def _settings(self):
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase storage requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return settings

    def _headers(self) -> dict[str, str]:
        settings = self._settings()
        return {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

    def _url(self) -> str:
        settings = self._settings()
        base_url = settings.supabase_url.rstrip("/")
        if base_url.endswith("/rest/v1"):
            return f"{base_url}/{settings.supabase_records_table}"
        return f"{base_url}/rest/v1/{settings.supabase_records_table}"

    def _raise_for_status(self, response: httpx.Response, action: str) -> None:
        if response.is_success:
            return
        detail = response.text.strip()
        if len(detail) > 500:
            detail = detail[:500] + "..."
        raise StorageError(f"Supabase {action} failed: HTTP {response.status_code}: {detail}")

    def probe(self) -> dict[str, Any]:
        params = {"select": "id", "limit": "1"}
        with httpx.Client(timeout=10) as client:
            response = client.get(self._url(), headers=self._headers(), params=params)
            self._raise_for_status(response, "probe")
        return {"ok": True, "table": self._settings().supabase_records_table}

    def append(self, record: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "store_name": self.store_name,
            "record_order": f"{now}-{uuid4().hex}",
            "payload": record,
        }
        with httpx.Client(timeout=20) as client:
            response = client.post(self._url(), headers=self._headers(), json=payload)
            self._raise_for_status(response, "insert")

    def all(self) -> list[dict[str, Any]]:
        params = {
            "store_name": f"eq.{self.store_name}",
            "select": "payload,record_order",
            "order": "record_order.asc",
        }
        with httpx.Client(timeout=20) as client:
            response = client.get(self._url(), headers=self._headers(), params=params)
            self._raise_for_status(response, "select")
        rows = response.json()
        return [row.get("payload") or {} for row in rows]

    def replace_all(self, records: list[dict[str, Any]]) -> None:
        self.clear()
        if not records:
            return
        now = datetime.now(timezone.utc).isoformat()
        payloads = [
            {
                "store_name": self.store_name,
                "record_order": f"{now}-{index:08d}-{uuid4().hex}",
                "payload": record,
            }
            for index, record in enumerate(records)
        ]
        with httpx.Client(timeout=20) as client:
            response = client.post(self._url(), headers=self._headers(), json=payloads)
            self._raise_for_status(response, "bulk insert")

    def clear(self) -> None:
        params = {"store_name": f"eq.{self.store_name}"}
        with httpx.Client(timeout=20) as client:
            response = client.delete(self._url(), headers=self._headers(), params=params)
            self._raise_for_status(response, "delete")


_runtime_storage_backend: str | None = None


def _normalize_backend(backend: str) -> str:
    normalized = (backend or "local").strip().lower()
    if normalized not in {"local", "supabase"}:
        raise ValueError("storage backend must be 'local' or 'supabase'.")
    return normalized


def get_runtime_storage_backend() -> str:
    return _normalize_backend(_runtime_storage_backend or get_settings().storage_backend)


def set_runtime_storage_backend(backend: str | None) -> str:
    global _runtime_storage_backend
    if backend is None:
        _runtime_storage_backend = None
        return get_runtime_storage_backend()
    _runtime_storage_backend = _normalize_backend(backend)
    return _runtime_storage_backend


def storage_status(probe: bool = False) -> dict[str, Any]:
    settings = get_settings()
    backend = get_runtime_storage_backend()
    status: dict[str, Any] = {
        "backend": backend,
        "env_default_backend": _normalize_backend(settings.storage_backend),
        "runtime_override": _runtime_storage_backend,
        "supabase_configured": bool(settings.supabase_url and settings.supabase_service_role_key),
        "supabase_records_table": settings.supabase_records_table,
    }
    if probe and backend == "supabase":
        try:
            status["supabase_probe"] = SupabaseJsonStore("health_probe").probe()
        except Exception as exc:
            status["supabase_probe"] = {"ok": False, "error": str(exc)}
    return status


class StoreProxy:
    def __init__(self, store_name: str, filename: str) -> None:
        self.store_name = store_name
        self.filename = filename
        self._local_store = JsonlStore(filename)

    def _active_store(self):
        if get_runtime_storage_backend() == "supabase":
            return SupabaseJsonStore(self.store_name)
        return self._local_store

    def append(self, record: dict[str, Any]) -> None:
        self._active_store().append(record)

    def all(self) -> list[dict[str, Any]]:
        return self._active_store().all()

    def replace_all(self, records: list[dict[str, Any]]) -> None:
        self._active_store().replace_all(records)

    def clear(self) -> None:
        self._active_store().clear()


def _store(name: str, filename: str) -> StoreProxy:
    return StoreProxy(name, filename)


prediction_store = _store("predictions", "predictions.jsonl")
report_store = _store("daily_reports", "daily_reports.jsonl")
potential_stock_store = _store("potential_stock_runs", "potential_stock_runs.jsonl")
potential_stock_ledger_store = _store("potential_stock_ledger", "potential_stock_ledger.jsonl")
potential_stock_case_store = _store("potential_stock_cases", "potential_stock_cases.jsonl")
potential_stock_settings_store = _store("potential_stock_settings", "potential_stock_settings.jsonl")
potential_stock_research_store = _store("potential_stock_research_bundles", "potential_stock_research_bundles.jsonl")
