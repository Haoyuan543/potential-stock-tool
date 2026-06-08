from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


TW_TZ = timezone(timedelta(hours=8))


class MarketUniverseService:
    """Build stock universes from public TWSE/TPEx company basic-data APIs."""

    TWSE_COMPANY_API = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    TPEX_COMPANY_API = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
    TPEX_COMPANY_API_ALT = "https://www.tpex.org.tw/openapi/v1/t187ap03_O"
    CACHE_TTL = timedelta(hours=12)

    CATEGORY_RULES: dict[str, dict[str, Any]] = {
        "semiconductor": {
            "industry_codes": {"24"},
            "keywords": {
                "半導體", "積體電路", "晶圓", "晶片", "封裝", "矽", "記憶體", "ASIC", "DRAM",
                "Semiconductor", "Integrated Circuit", "Wafer", "Foundry", "Packaging", "Testing", "Memory",
            },
        },
        "electronics": {
            "industry_codes": {"24", "25", "27", "28", "30", "31"},
            "keywords": {
                "人工智慧", "伺服器", "Server", "電腦", "Computer", "通信", "Communication", "網通",
                "電子零組件", "光電", "散熱", "液冷", "電源", "PCB", "CCL", "Connector", "ODM", "EMS",
                "GB200", "GB300", "CoWoS", "HBM", "CPO", "ASIC",
            },
        },
        "industrial": {
            "industry_codes": {"01", "03", "10", "14", "15", "20", "21", "22", "23", "26"},
            "keywords": {"工業", "材料", "航運", "鋼鐵", "塑膠", "電機", "機械", "Shipping", "Steel", "Industrial"},
        },
        "financial": {
            "industry_codes": {"17"},
            "keywords": {"金融", "銀行", "保險", "證券", "金控", "Financial", "Bank", "Insurance"},
        },
    }

    def __init__(self, fallback_universes: dict[str, list[str]] | None = None) -> None:
        self.fallback_universes = fallback_universes or {}
        self._cache_rows: list[dict[str, Any]] = []
        self._cache_at: datetime | None = None
        self._cache_source_status: list[dict[str, Any]] = []

    async def resolve_symbols(self, universes: list[str], explicit_symbols: list[str] | None = None, limit: int = 180) -> dict[str, Any]:
        selected = [item for item in universes if item and item != "custom"] or ["semiconductor"]
        rows = await self._company_rows()
        explicit = self._normalize_symbols(explicit_symbols or [])

        scored: list[tuple[int, str, dict[str, Any]]] = []
        for row in rows:
            score = self._match_score(row, selected)
            if score <= 0:
                continue
            symbol = str(row.get("symbol") or "")
            if symbol:
                scored.append((score, symbol, row))

        scored.sort(key=lambda item: (-item[0], item[1]))
        dynamic_symbols = [symbol for _, symbol, _ in scored]
        fallback_symbols: list[str] = []
        for universe in selected:
            fallback_symbols.extend(self.fallback_universes.get(universe, []))

        merged = self._dedupe([*dynamic_symbols, *fallback_symbols, *explicit])
        limited = merged[: max(1, limit)]
        return {
            "symbols": limited,
            "full_count": len(merged),
            "dynamic_count": len(dynamic_symbols),
            "fallback_count": len(self._dedupe(fallback_symbols)),
            "selected_universes": selected,
            "source_status": self._cache_source_status,
            "generated_at": datetime.now(TW_TZ).isoformat(),
            "source": "TWSE/TPEx company basic-data OpenAPI + curated fallback",
            "truncated": len(merged) > len(limited),
        }

    async def status(self) -> dict[str, Any]:
        rows = await self._company_rows(force_refresh=True)
        counts: dict[str, int] = {}
        for universe in self.CATEGORY_RULES:
            counts[universe] = len([row for row in rows if self._match_score(row, [universe]) > 0])
        return {
            "ok": bool(rows),
            "generated_at": datetime.now(TW_TZ).isoformat(),
            "company_count": len(rows),
            "category_counts": counts,
            "source_status": self._cache_source_status,
        }

    async def _company_rows(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        now = datetime.now(TW_TZ)
        if not force_refresh and self._cache_rows and self._cache_at and now - self._cache_at < self.CACHE_TTL:
            return self._cache_rows

        rows: list[dict[str, Any]] = []
        status: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=20) as client:
            twse_rows, twse_status = await self._fetch_company_api(client, self.TWSE_COMPANY_API, "TWSE", ".TW")
            rows.extend(twse_rows)
            status.append(twse_status)

            tpex_rows, tpex_status = await self._fetch_company_api(client, self.TPEX_COMPANY_API, "TPEx", ".TWO")
            if not tpex_rows:
                tpex_rows, tpex_status = await self._fetch_company_api(client, self.TPEX_COMPANY_API_ALT, "TPEx", ".TWO")
            rows.extend(tpex_rows)
            status.append(tpex_status)

        self._cache_rows = self._dedupe_rows(rows)
        self._cache_at = now
        self._cache_source_status = status
        return self._cache_rows

    async def _fetch_company_api(self, client: httpx.AsyncClient, url: str, market: str, suffix: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        fetched_at = datetime.now(TW_TZ).isoformat()
        try:
            response = await client.get(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            raw_rows = response.json()
        except Exception as exc:  # noqa: BLE001
            return [], {"market": market, "url": url, "ok": False, "error": str(exc), "fetched_at": fetched_at}
        if not isinstance(raw_rows, list):
            return [], {"market": market, "url": url, "ok": False, "error": "response is not a list", "fetched_at": fetched_at}

        rows = [self._normalize_company_row(row, market, suffix, url, fetched_at) for row in raw_rows if isinstance(row, dict)]
        rows = [row for row in rows if row.get("symbol")]
        return rows, {"market": market, "url": url, "ok": True, "row_count": len(rows), "fetched_at": fetched_at}

    def _normalize_company_row(self, row: dict[str, Any], market: str, suffix: str, url: str, fetched_at: str) -> dict[str, Any]:
        code = self._first(row, ["公司代號", "SecuritiesCompanyCode", "Code", "公司代号"])
        industry_code = self._first(row, ["產業別", "SecuritiesIndustryCode", "IndustryCode"])
        name = self._first(row, ["公司簡稱", "CompanyAbbreviation", "公司简称", "公司名稱", "CompanyName"])
        full_name = self._first(row, ["公司名稱", "CompanyName", "公司名称"])
        english = self._first(row, ["英文簡稱", "Symbol", "EnglishName"])
        website = self._first(row, ["網址", "WebAddress", "Website"])
        code = str(code or "").strip()
        if not code or not code.isdigit():
            return {}
        return {
            "symbol": f"{code}{suffix}",
            "code": code,
            "market": market,
            "name": str(name or full_name or code).strip(),
            "full_name": str(full_name or name or "").strip(),
            "english_name": str(english or "").strip(),
            "industry_code": str(industry_code or "").strip(),
            "website": str(website or "").strip(),
            "source_url": url,
            "fetched_at": fetched_at,
            "raw": row,
        }

    def _match_score(self, row: dict[str, Any], universes: list[str]) -> int:
        text = " ".join(
            str(row.get(key) or "")
            for key in ("symbol", "name", "full_name", "english_name", "industry_code", "website")
        )
        haystack = text.lower()
        score = 0
        for universe in universes:
            rules = self.CATEGORY_RULES.get(universe)
            if not rules:
                continue
            if str(row.get("industry_code") or "") in rules["industry_codes"]:
                score += 80
            keyword_hits = [keyword for keyword in rules["keywords"] if str(keyword).lower() in haystack]
            score += min(60, len(keyword_hits) * 12)
            if row.get("symbol") in self.fallback_universes.get(universe, []):
                score += 30
        return score

    def _dedupe_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for row in rows:
            symbol = str(row.get("symbol") or "")
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            out.append(row)
        return out

    def _dedupe(self, symbols: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for symbol in self._normalize_symbols(symbols):
            if symbol not in seen:
                seen.add(symbol)
                out.append(symbol)
        return out

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        cleaned: list[str] = []
        for symbol in symbols:
            value = str(symbol or "").strip().upper()
            if not value:
                continue
            if value.isdigit():
                value = f"{value}.TW"
            cleaned.append(value)
        return cleaned

    def _first(self, row: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            if key in row and row.get(key) not in (None, ""):
                return row.get(key)
        return None
