from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx

from backend.config import get_settings


def _tw_symbol(symbol: str) -> str:
    return symbol.split(".")[0]


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fetch_institutional_data(symbol: str) -> dict[str, Any]:
    settings = get_settings()
    stock_id = _tw_symbol(symbol)
    start = (date.today() - timedelta(days=75)).isoformat()
    params = {"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "data_id": stock_id, "start_date": start}
    if settings.finmind_token:
        params["token"] = settings.finmind_token

    source = {"name": "FinMind 三大法人買賣超", "url": "https://api.finmindtrade.com/docs"}
    try:
        response = httpx.get("https://api.finmindtrade.com/api/v4/data", params=params, timeout=settings.request_timeout)
        response.raise_for_status()
        rows = response.json().get("data") or []
    except Exception as exc:
        return {"status": "missing", "data": {}, "sources": [source], "missing": [f"Data Missing: FinMind institutional fetch failed: {exc}"]}

    if not rows:
        return {"status": "missing", "data": {}, "sources": [source], "missing": ["Data Missing: no institutional data returned. FINMIND_TOKEN may be required."]}

    daily: dict[str, dict[str, float]] = {}
    unmatched_names: set[str] = set()
    for row in rows:
        day_key = row.get("date")
        name = str(row.get("name") or row.get("institutional_investors") or "")
        normalized = name.lower().replace(" ", "_")
        net = _safe_float(row.get("buy")) - _safe_float(row.get("sell"))
        day = daily.setdefault(day_key, {"foreign": 0.0, "trust": 0.0, "dealer": 0.0, "total": 0.0})
        if any(token in normalized for token in ("foreign", "foreign_investor", "foreign_dealer_self")) or any(token in name for token in ("外資", "外陸資")):
            day["foreign"] += net
        elif any(token in normalized for token in ("investment_trust", "trust")) or "投信" in name:
            day["trust"] += net
        elif any(token in normalized for token in ("dealer", "dealer_self", "dealer_hedging")) or "自營商" in name:
            day["dealer"] += net
        else:
            unmatched_names.add(name)
        day["total"] += net

    trend_rows = [{"date": day_key, **values} for day_key, values in sorted(daily.items())]
    trust_zero_count = sum(1 for row in trend_rows[-20:] if row["trust"] == 0)
    suspicious_zero_data = trust_zero_count >= min(10, len(trend_rows[-20:])) if trend_rows else False

    missing: list[str] = []
    if suspicious_zero_data:
        missing.append("Data Warning: investment trust data is suspiciously zero for many days; verify with TWSE or broker data.")
    if unmatched_names:
        preview = ", ".join(sorted(name for name in unmatched_names if name)[:5])
        missing.append(f"Data Limitation: some institutional categories were not recognized: {preview}")

    data = {
        "latest": trend_rows[-1] if trend_rows else {},
        "trend": trend_rows[-20:],
        "foreign_streak": _streak([row["foreign"] for row in trend_rows]),
        "trust_streak": _streak([row["trust"] for row in trend_rows]),
        "dealer_streak": _streak([row["dealer"] for row in trend_rows]),
        "consecutive_trend": _streak([row["total"] for row in trend_rows]),
        "flow_sums": {
            "foreign": _window_sums(trend_rows, "foreign"),
            "trust": _window_sums(trend_rows, "trust"),
            "dealer": _window_sums(trend_rows, "dealer"),
            "total": _window_sums(trend_rows, "total"),
        },
        "unit": "shares",
        "display_unit": "lots",
        "suspicious_zero_data": {"trust": suspicious_zero_data},
    }
    return {"status": "partial" if missing else "ok", "data": data, "sources": [source], "missing": missing}


def _window_sums(rows: list[dict[str, float]], field: str) -> dict[str, float]:
    return {f"{window}d": sum(row[field] for row in rows[-window:]) for window in (1, 3, 5, 10)}


def _streak(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"direction": "Data Missing", "days": 0}
    direction = "buy" if values[-1] > 0 else "sell" if values[-1] < 0 else "flat"
    days = 0
    for value in reversed(values):
        if direction == "buy" and value > 0:
            days += 1
        elif direction == "sell" and value < 0:
            days += 1
        elif direction == "flat" and value == 0:
            days += 1
        else:
            break
    return {"direction": direction, "days": days}
