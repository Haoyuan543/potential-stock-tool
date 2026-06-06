from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx

from backend.config import get_settings
from backend.search.web_search import web_search


def _tw_symbol(symbol: str) -> str:
    return symbol.split(".")[0]


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _finmind_get(dataset: str, stock_id: str, start: str, token: str = "") -> list[dict[str, Any]]:
    params = {"dataset": dataset, "data_id": stock_id, "start_date": start}
    if token:
        params["token"] = token
    response = httpx.get("https://api.finmindtrade.com/api/v4/data", params=params, timeout=get_settings().request_timeout)
    response.raise_for_status()
    return response.json().get("data") or []


def fetch_fundamental_data(symbol: str) -> dict[str, Any]:
    settings = get_settings()
    stock_id = _tw_symbol(symbol)
    start = (date.today() - timedelta(days=760)).isoformat()
    missing: list[str] = []
    sources = [
        {"name": "FinMind TaiwanStockMonthRevenue", "url": "https://api.finmindtrade.com/docs"},
        {"name": "FinMind TaiwanStockDividend", "url": "https://api.finmindtrade.com/docs"},
        {"name": "FinMind TaiwanStockPER", "url": "https://api.finmindtrade.com/docs"},
        {"name": "FinMind TaiwanStockFinancialStatements", "url": "https://api.finmindtrade.com/docs"},
    ]
    data: dict[str, Any] = {
        "monthly_revenue": [],
        "latest_monthly_revenue": None,
        "monthly_revenue_yoy": None,
        "eps": None,
        "eps_record": None,
        "dividend_yield": None,
        "per": None,
        "pbr": None,
        "dividend_rate": None,
        "company_announcements": [],
        "investor_conference": [],
    }

    try:
        rows = _finmind_get("TaiwanStockMonthRevenue", stock_id, start, settings.finmind_token)
        data["monthly_revenue"] = rows[-24:]
        if rows:
            latest = rows[-1]
            data["latest_monthly_revenue"] = latest
            latest_month = str(latest.get("date") or latest.get("revenue_year_month") or "")[-5:]
            latest_revenue = _safe_float(latest.get("revenue") or latest.get("month_revenue"))
            prior = next(
                (
                    row
                    for row in reversed(rows[:-1])
                    if str(row.get("date") or row.get("revenue_year_month") or "").endswith(latest_month)
                ),
                None,
            )
            prior_revenue = _safe_float((prior or {}).get("revenue") or (prior or {}).get("month_revenue"))
            if latest_revenue is not None and prior_revenue:
                data["monthly_revenue_yoy"] = (latest_revenue - prior_revenue) / prior_revenue * 100
            else:
                missing.append("Data Missing: monthly revenue YoY base period unavailable.")
        else:
            missing.append("Data Missing: no monthly revenue returned from FinMind.")
    except Exception as exc:
        missing.append(f"Data Missing: monthly revenue fetch failed: {exc}")

    try:
        dividend_rows = _finmind_get("TaiwanStockDividend", stock_id, start, settings.finmind_token)
        if dividend_rows:
            data["dividend_rate"] = dividend_rows[-1]
        else:
            missing.append("Data Missing: no dividend records returned from FinMind.")
    except Exception as exc:
        missing.append(f"Data Missing: dividend fetch failed from FinMind: {exc}")

    try:
        per_rows = _finmind_get("TaiwanStockPER", stock_id, start, settings.finmind_token)
        if per_rows:
            latest_per = per_rows[-1]
            data["dividend_yield"] = _safe_float(latest_per.get("dividend_yield"))
            data["per"] = _safe_float(latest_per.get("PER"))
            data["pbr"] = _safe_float(latest_per.get("PBR"))
        else:
            missing.append("Data Missing: no PER/PBR/dividend_yield records returned from FinMind.")
    except Exception as exc:
        missing.append(f"Data Missing: PER/PBR/dividend_yield fetch failed from FinMind: {exc}")

    try:
        statement_rows = _finmind_get("TaiwanStockFinancialStatements", stock_id, start, settings.finmind_token)
        eps_rows = [row for row in statement_rows if _looks_like_eps(row)]
        if eps_rows:
            latest_eps = eps_rows[-1]
            data["eps_record"] = latest_eps
            data["eps"] = _safe_float(latest_eps.get("value"))
        else:
            missing.append("Data Missing: EPS unavailable from FinMind TaiwanStockFinancialStatements.")
    except Exception as exc:
        missing.append(f"Data Missing: EPS fetch failed from FinMind: {exc}")

    if data["dividend_yield"] is None:
        missing.append("Data Missing: dividend yield unavailable.")
    if data["dividend_rate"] is None:
        missing.append("Data Missing: dividend amount unavailable.")

    _enrich_company_context(stock_id, data, sources, missing)
    return {"status": "partial" if missing else "ok", "data": data, "sources": sources, "missing": missing}


def _looks_like_eps(row: dict[str, Any]) -> bool:
    raw = str(row.get("type") or row.get("name") or "")
    normalized = raw.upper()
    return normalized == "EPS" or "EPS" in normalized or "每股盈餘" in raw or "基本每股盈餘" in raw


def _enrich_company_context(stock_id: str, data: dict[str, Any], sources: list[dict[str, Any]], missing: list[str]) -> None:
    search = web_search(
        [
            f"{stock_id} 長榮 海運 公司公告 法說會 配息 EPS",
            "長榮海運 法說會 簡報 配息 公告 月營收 EPS",
            "Evergreen Marine investor relations dividend announcement EPS presentation",
        ],
        max_results_per_query=4,
    )
    sources.extend(search.get("sources", []))
    rows = search.get("results", [])
    announcements = [row for row in rows if _contains_any(row, ("公告", "重大訊息", "配息", "除息", "dividend", "announcement", "material"))]
    conferences = [row for row in rows if _contains_any(row, ("法說", "法說會", "簡報", "investor", "presentation", "conference"))]
    data["company_announcements"] = announcements[:8]
    data["investor_conference"] = conferences[:8]
    if not announcements:
        missing.append("Data Limitation: company announcements were not confirmed by search fallback; use MOPS / company IR for final check.")
    if not conferences:
        missing.append("Data Limitation: investor conference materials were not confirmed by search fallback.")
    missing.extend(search.get("missing", []))


def _contains_any(row: dict[str, Any], words: tuple[str, ...]) -> bool:
    text = f"{row.get('title') or ''} {row.get('snippet') or ''} {row.get('url') or ''}".lower()
    return any(word.lower() in text for word in words)
