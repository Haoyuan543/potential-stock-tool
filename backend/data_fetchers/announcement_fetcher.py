from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx

from backend.config import get_settings


def _tw_symbol(symbol: str) -> str:
    return symbol.split(".")[0]


def fetch_announcement_data(symbol: str) -> dict[str, Any]:
    settings = get_settings()
    stock_id = _tw_symbol(symbol)
    source = {"name": "TWSE OpenAPI / MOPS material information", "url": "https://openapi.twse.com.tw/"}
    endpoints = [
        "https://openapi.twse.com.tw/v1/opendata/t187ap04_L",
        "https://openapi.twse.com.tw/v1/opendata/t187ap04_O",
    ]
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    cutoff = date.today() - timedelta(days=30)

    for endpoint in endpoints:
        try:
            response = httpx.get(endpoint, timeout=settings.request_timeout)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                rows.extend(_normalize_rows(payload, stock_id, endpoint, cutoff))
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")

    if rows:
        rows = _dedupe(rows)
        return {"status": "ok", "data": {"announcements": rows[:20]}, "sources": [source], "missing": []}

    missing = ["Data Missing: no matching MOPS/TWSE company announcements returned in the latest open data feed."]
    if errors:
        missing.append("Data Missing: MOPS/TWSE announcement fetch errors: " + " | ".join(errors[:2]))
    return {"status": "missing", "data": {"announcements": []}, "sources": [source], "missing": missing}


def _normalize_rows(rows: list[dict[str, Any]], stock_id: str, endpoint: str, cutoff: date) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        text = " ".join(str(value) for value in row.values())
        if stock_id not in text:
            continue
        row_date = _parse_date(row)
        if row_date and row_date < cutoff:
            continue
        normalized.append(
            {
                "date": row_date.isoformat() if row_date else None,
                "company_id": _pick(row, ["公司代號", "公司代號(Code)", "公司代號 Code", "公司代號/股票代號"]),
                "company_name": _pick(row, ["公司簡稱", "公司名稱", "公司名稱 Name"]),
                "title": _pick(row, ["主旨", "公告事項", "重大訊息主旨", "Subject", "title"]) or text[:120],
                "raw": row,
                "source_endpoint": endpoint,
            }
        )
    return normalized


def _parse_date(row: dict[str, Any]) -> date | None:
    for key in ("出表日期", "發言日期", "公告日期", "日期", "Date"):
        raw = str(row.get(key) or "").strip()
        if not raw:
            continue
        for fmt in ("%Y%m%d", "%Y/%m/%d", "%Y-%m-%d"):
            try:
                return date.fromisoformat(raw) if fmt == "%Y-%m-%d" else __import__("datetime").datetime.strptime(raw, fmt).date()
            except Exception:
                pass
    return None


def _pick(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if row.get(key):
            return row.get(key)
    return None


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for row in rows:
        key = (row.get("date"), row.get("company_id"), row.get("title"))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return sorted(output, key=lambda item: item.get("date") or "", reverse=True)
