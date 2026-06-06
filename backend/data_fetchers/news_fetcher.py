from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend.config import get_settings
from backend.search.search_queries import build_queries
from backend.search.web_search import web_search


KEYWORDS = "長榮 2603 運價 SCFI 紅海 法說 配息 Evergreen Marine freight rate SCFI Red Sea"


def fetch_news_data(symbol: str) -> dict[str, Any]:
    settings = get_settings()
    stock_id = symbol.split(".")[0]
    sources: list[dict[str, str]] = []
    missing: list[str] = []
    articles: list[dict[str, Any]] = []

    if settings.news_api_key:
        newsapi = _fetch_newsapi(settings.news_api_key, symbol, stock_id)
        sources.extend(newsapi["sources"])
        articles.extend(newsapi["articles"])
        missing.extend(newsapi["missing"])
    else:
        missing.append("Data Missing: NEWS_API_KEY is not configured; using web search fallback.")

    search = web_search(build_queries(symbol, max_queries=5), max_results_per_query=5)
    sources.extend(search["sources"])
    missing.extend(search["missing"])
    articles.extend(_search_results_to_articles(search["results"]))

    articles = _dedupe(articles)[:40]
    red_sea = [item for item in articles if _contains(item, ["red sea", "紅海", "houthi", "胡塞"])]
    if not articles:
        missing.append("Data Missing: no news articles returned from NewsAPI or web search fallback.")
    return {
        "status": "ok" if articles else "missing",
        "data": {"articles": articles, "red_sea_shipping_context": red_sea, "keywords": KEYWORDS},
        "sources": _dedupe_sources(sources) or [{"name": "Web Search Fallback", "url": "https://news.google.com/rss"}],
        "missing": missing,
    }


def _fetch_newsapi(api_key: str, symbol: str, stock_id: str) -> dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    query = f"({symbol} OR {stock_id} OR 長榮海運 OR 長榮 OR Evergreen Marine OR Red Sea OR shipping freight OR SCFI)"
    params = {"q": query, "from": since, "sortBy": "publishedAt", "language": "zh", "apiKey": api_key, "pageSize": 30}
    source = {"name": "NewsAPI", "url": "https://newsapi.org/"}
    try:
        response = httpx.get("https://newsapi.org/v2/everything", params=params, timeout=get_settings().request_timeout)
        response.raise_for_status()
        rows = response.json().get("articles") or []
    except Exception as exc:
        return {"articles": [], "sources": [source], "missing": [f"Data Missing: NewsAPI fetch failed: {exc}"]}
    return {"articles": [_normalize_newsapi(item) for item in rows], "sources": [source], "missing": []}


def _normalize_newsapi(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title"),
        "description": item.get("description"),
        "url": item.get("url"),
        "published_at": item.get("publishedAt"),
        "source": (item.get("source") or {}).get("name"),
        "evidence_type": "exact_source_article",
    }


def _search_results_to_articles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "title": row.get("title"),
            "description": row.get("snippet"),
            "url": row.get("url"),
            "published_at": row.get("published_at"),
            "source": row.get("source"),
            "query": row.get("query"),
            "source_score": row.get("source_score"),
            "evidence_type": "web_search_result",
        }
        for row in rows
    ]


def _contains(item: dict[str, Any], words: list[str]) -> bool:
    text = f"{item.get('title') or ''} {item.get('description') or ''}".lower()
    return any(word.lower() in text for word in words)


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for row in rows:
        key = row.get("url") or row.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _dedupe_sources(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen, output = set(), []
    for row in rows:
        key = (row.get("name"), row.get("url"))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output
