from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


TW_TZ = timezone(timedelta(hours=8))


PUBLIC_DATA_SOURCES: list[dict[str, Any]] = [
    {
        "id": "finmind",
        "name": "FinMind Taiwan market API",
        "category": "market_data",
        "source_url": "https://api.finmindtrade.com/docs",
        "requires_key": "optional",
        "access_difficulty": 1,
        "fallback_rank": 1,
        "freshness": "daily/intraday depending dataset",
        "method": "json_api",
        "covers": ["price", "institutional", "monthly_revenue"],
    },
    {
        "id": "twse_openapi_material",
        "name": "TWSE OpenAPI material information",
        "category": "official_disclosure",
        "source_url": "https://openapi.twse.com.tw/v1/opendata/t187ap04_L",
        "requires_key": "no",
        "access_difficulty": 1,
        "fallback_rank": 2,
        "freshness": "official open data",
        "method": "json_api",
        "covers": ["official_mops", "material_information"],
    },
    {
        "id": "tpex_openapi_material",
        "name": "TPEx OpenAPI material information",
        "category": "official_disclosure",
        "source_url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O",
        "requires_key": "no",
        "access_difficulty": 1,
        "fallback_rank": 3,
        "freshness": "official open data",
        "method": "json_api",
        "covers": ["official_mops", "material_information"],
    },
    {
        "id": "twse_exchange_alerts",
        "name": "TWSE notice and disposition OpenAPI",
        "category": "exchange_alert",
        "source_url": "https://openapi.twse.com.tw/v1/announcement/notice",
        "requires_key": "no",
        "access_difficulty": 1,
        "fallback_rank": 4,
        "freshness": "official open data",
        "method": "json_api",
        "covers": ["attention", "disposition", "risk"],
    },
    {
        "id": "tpex_exchange_alerts",
        "name": "TPEx attention and disposition OpenAPI",
        "category": "exchange_alert",
        "source_url": "https://www.tpex.org.tw/openapi/v1/tpex_trading_attention",
        "requires_key": "no",
        "access_difficulty": 1,
        "fallback_rank": 5,
        "freshness": "official open data",
        "method": "json_api",
        "covers": ["attention", "disposition", "risk"],
    },
    {
        "id": "mops_material_web",
        "name": "MOPS material information web query",
        "category": "official_disclosure",
        "source_url": "https://mops.twse.com.tw/mops/web/t05st01",
        "requires_key": "no",
        "access_difficulty": 2,
        "fallback_rank": 6,
        "freshness": "official web",
        "method": "html_form",
        "covers": ["official_mops", "material_information"],
    },
    {
        "id": "mops_conference_web",
        "name": "MOPS investor conference web query",
        "category": "ir",
        "source_url": "https://mops.twse.com.tw/mops/web/t100sb07",
        "requires_key": "no",
        "access_difficulty": 2,
        "fallback_rank": 7,
        "freshness": "official web",
        "method": "html_form",
        "covers": ["conference_material", "ir"],
    },
    {
        "id": "company_ir",
        "name": "Company investor relations pages",
        "category": "ir",
        "source_url": "",
        "requires_key": "no",
        "access_difficulty": 3,
        "fallback_rank": 8,
        "freshness": "company dependent",
        "method": "html_link",
        "covers": ["ir", "presentation", "earnings"],
    },
    {
        "id": "newsapi",
        "name": "NewsAPI everything endpoint",
        "category": "news",
        "source_url": "https://newsapi.org/docs/endpoints/everything",
        "requires_key": "yes",
        "access_difficulty": 3,
        "fallback_rank": 9,
        "freshness": "near real-time when configured",
        "method": "json_api",
        "covers": ["news", "events"],
    },
    {
        "id": "stock_driven_web_search",
        "name": "Stock-specific web search",
        "category": "web_search",
        "source_url": "",
        "requires_key": "depends",
        "access_difficulty": 4,
        "fallback_rank": 10,
        "freshness": "search-provider dependent",
        "method": "search_api",
        "covers": ["supply_chain", "news", "market_context"],
    },
    {
        "id": "yahoo_finance_chart",
        "name": "Yahoo Finance chart endpoint",
        "category": "us_market_context",
        "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/",
        "requires_key": "no",
        "access_difficulty": 4,
        "fallback_rank": 11,
        "freshness": "market dependent",
        "method": "json_api",
        "covers": ["us_leader_price", "adr", "sector_etf"],
    },
    {
        "id": "dom_network_extraction",
        "name": "Playwright DOM and network extraction",
        "category": "web_fallback",
        "source_url": "",
        "requires_key": "no",
        "access_difficulty": 5,
        "fallback_rank": 12,
        "freshness": "page dependent",
        "method": "browser_dom",
        "covers": ["webpage_text", "tables", "network_json"],
    },
    {
        "id": "screenshot_vision_fallback",
        "name": "Screenshot extraction fallback",
        "category": "last_resort",
        "source_url": "",
        "requires_key": "openai_vision",
        "access_difficulty": 6,
        "fallback_rank": 13,
        "freshness": "page dependent",
        "method": "browser_screenshot",
        "covers": ["human_visible_page_state"],
    },
]


def now_tw_iso() -> str:
    return datetime.now(TW_TZ).isoformat()


def source_catalog() -> list[dict[str, Any]]:
    return sorted((dict(item) for item in PUBLIC_DATA_SOURCES), key=lambda item: int(item["fallback_rank"]))


def source_metadata_for(source: str = "", tier: str = "", url: str | None = None) -> dict[str, Any]:
    source_text = f"{source} {tier} {url or ''}".lower()
    selected = None
    for item in source_catalog():
        haystacks = [
            str(item.get("id") or "").lower(),
            str(item.get("name") or "").lower(),
            str(item.get("category") or "").lower(),
            str(item.get("source_url") or "").lower(),
        ]
        if any(value and value in source_text for value in haystacks):
            selected = item
            break

    if selected is None:
        if tier in {"official_mops"}:
            selected = source_catalog()[1]
        elif tier == "exchange_alert":
            selected = source_catalog()[3]
        elif tier in {"company_ir", "conference_material"}:
            selected = next(item for item in source_catalog() if item["id"] == "company_ir")
        elif tier == "supply_chain_search":
            selected = next(item for item in source_catalog() if item["id"] == "stock_driven_web_search")
        elif tier == "news":
            selected = next(item for item in source_catalog() if item["id"] == "newsapi")
        else:
            selected = next(item for item in source_catalog() if item["id"] == "dom_network_extraction")

    source_url = url or selected.get("source_url") or ""
    return {
        "source_id": selected.get("id"),
        "source_name": selected.get("name"),
        "source_category": selected.get("category"),
        "source_url": source_url,
        "requires_key": selected.get("requires_key"),
        "access_difficulty": selected.get("access_difficulty"),
        "fallback_rank": selected.get("fallback_rank"),
        "retrieval_method": selected.get("method"),
        "freshness": selected.get("freshness"),
        "fetched_at": now_tw_iso(),
    }


def annotate_payload(payload: Any, source: str = "", tier: str = "", url: str | None = None) -> Any:
    if not isinstance(payload, dict):
        payload = {"summary": payload}
    return {**payload, **source_metadata_for(source=source, tier=tier, url=url)}
