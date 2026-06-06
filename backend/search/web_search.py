from __future__ import annotations

import xml.etree.ElementTree as ET
import base64
from typing import Any
from urllib.parse import quote_plus, unquote

import httpx

from backend.config import get_settings
from backend.search.cache import SearchCache
from backend.search.source_ranker import rank_results


def web_search(queries: list[str], max_results_per_query: int = 5) -> dict[str, Any]:
    settings = get_settings()
    cache = SearchCache()
    all_results: list[dict[str, Any]] = []
    missing: list[str] = []
    sources: list[dict[str, str]] = []

    for query in queries:
        cache_key = f"search:v6:{query}:{max_results_per_query}"
        cached = cache.get(cache_key)
        if cached:
            all_results.extend(cached.get("results", []))
            sources.extend(cached.get("sources", []))
            continue

        result = _search_one(query, settings, max_results_per_query)
        cache.set(cache_key, result)
        all_results.extend(result.get("results", []))
        sources.extend(result.get("sources", []))
        missing.extend(result.get("missing", []))

    ranked = rank_results(_dedupe(all_results))[: max_results_per_query * max(1, len(queries))]
    return {
        "results": ranked,
        "sources": _dedupe_sources(sources) or [{"name": "Google News RSS", "url": "https://news.google.com/rss"}],
        "missing": missing,
    }


def _search_one(query: str, settings: Any, limit: int) -> dict[str, Any]:
    if settings.brave_search_api_key:
        return _brave(query, settings.brave_search_api_key, limit)
    if settings.serpapi_api_key:
        return _serpapi(query, settings.serpapi_api_key, limit)
    if settings.tavily_api_key:
        return _tavily(query, settings.tavily_api_key, limit)
    news = _google_news_rss(query, limit)
    web = _bing_html(query, limit)
    return {
        "results": _dedupe(news.get("results", []) + web.get("results", []))[: limit * 2],
        "sources": news.get("sources", []) + web.get("sources", []),
        "missing": news.get("missing", []) + web.get("missing", []),
    }


def _google_news_rss(query: str, limit: int) -> dict[str, Any]:
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    source = {"name": "Google News RSS", "url": url}
    try:
        response = httpx.get(url, timeout=get_settings().request_timeout)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        rows = []
        for item in root.findall(".//item")[:limit]:
            rows.append(
                {
                    "title": _xml_text(item, "title"),
                    "snippet": _xml_text(item, "description"),
                    "url": _xml_text(item, "link"),
                    "published_at": _xml_text(item, "pubDate"),
                    "source": "Google News RSS",
                    "query": query,
                }
            )
        return {"results": rows, "sources": [source], "missing": []}
    except Exception as exc:
        return {"results": [], "sources": [source], "missing": [f"Data Limitation: Google News RSS search failed for '{query}': {exc}"]}


def _bing_html(query: str, limit: int) -> dict[str, Any]:
    url = f"https://www.bing.com/search?q={quote_plus(query)}"
    source = {"name": "Bing Web Search HTML", "url": url}
    try:
        response = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=get_settings().request_timeout)
        response.raise_for_status()
    except Exception as exc:
        return {"results": [], "sources": [source], "missing": [f"Data Limitation: Bing HTML search failed for '{query}': {exc}"]}

    rows: list[dict[str, Any]] = []
    blocks = response.text.split('<li class="b_algo"')
    for block in blocks[1 : limit + 1]:
        href = _first_match(block, r"<h2[^>]*>\s*<a[^>]+href=\"([^\"]+)\"")
        if not href:
            href = _html_attr(block, "href")
        title = _strip_html(_first_match(block, r"<h2[^>]*>([\s\S]*?)</h2>"))
        snippet = _strip_html(_first_match(block, r"<p[^>]*>([\s\S]*?)</p>"))
        if not href or not title:
            continue
        rows.append(
            {
                "title": title,
                "snippet": snippet,
                "url": _clean_bing_url(href),
                "published_at": "",
                "source": "Bing Web Search HTML",
                "query": query,
            }
        )
    return {"results": rows, "sources": [source], "missing": []}


def _html_attr(text: str, attr: str) -> str:
    match = __import__("re").search(rf'{attr}="([^"]+)"', text)
    return match.group(1) if match else ""


def _first_match(text: str, pattern: str) -> str:
    match = __import__("re").search(pattern, text, flags=__import__("re").I)
    return match.group(1) if match else ""


def _strip_html(text: str) -> str:
    import html
    import re

    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return html.unescape(text).strip()


def _clean_bing_url(url: str) -> str:
    if "bing.com/ck/a" not in url:
        return _decode_bing_wrapped_url(url)
    marker = "u="
    if marker in url:
        encoded = url.split(marker, 1)[1].split("&", 1)[0]
        return _decode_bing_wrapped_url(unquote(encoded))
    return url


def _decode_bing_wrapped_url(url: str) -> str:
    if url.startswith("a1") and len(url) > 12:
        raw = url[2:]
        padding = "=" * (-len(raw) % 4)
        try:
            decoded = base64.urlsafe_b64decode(raw + padding).decode("utf-8", errors="ignore")
            if decoded.startswith("http"):
                return decoded
        except Exception:
            return url
    return url


def _brave(query: str, api_key: str, limit: int) -> dict[str, Any]:
    source = {"name": "Brave Search API", "url": "https://api.search.brave.com/"}
    try:
        response = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": limit, "freshness": "pd"},
            headers={"X-Subscription-Token": api_key},
            timeout=get_settings().request_timeout,
        )
        response.raise_for_status()
        rows = response.json().get("web", {}).get("results", [])
        return {
            "results": [
                {"title": item.get("title"), "snippet": item.get("description"), "url": item.get("url"), "published_at": item.get("age"), "source": "Brave Search API", "query": query}
                for item in rows[:limit]
            ],
            "sources": [source],
            "missing": [],
        }
    except Exception as exc:
        return {"results": [], "sources": [source], "missing": [f"Data Limitation: Brave Search failed for '{query}': {exc}"]}


def _serpapi(query: str, api_key: str, limit: int) -> dict[str, Any]:
    source = {"name": "SerpAPI", "url": "https://serpapi.com/"}
    try:
        response = httpx.get("https://serpapi.com/search.json", params={"q": query, "api_key": api_key, "num": limit}, timeout=get_settings().request_timeout)
        response.raise_for_status()
        rows = response.json().get("organic_results", [])
        return {
            "results": [
                {"title": item.get("title"), "snippet": item.get("snippet"), "url": item.get("link"), "published_at": item.get("date"), "source": "SerpAPI", "query": query}
                for item in rows[:limit]
            ],
            "sources": [source],
            "missing": [],
        }
    except Exception as exc:
        return {"results": [], "sources": [source], "missing": [f"Data Limitation: SerpAPI search failed for '{query}': {exc}"]}


def _tavily(query: str, api_key: str, limit: int) -> dict[str, Any]:
    source = {"name": "Tavily Search API", "url": "https://tavily.com/"}
    try:
        response = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": limit, "topic": "news"},
            timeout=get_settings().request_timeout,
        )
        response.raise_for_status()
        rows = response.json().get("results", [])
        return {
            "results": [
                {"title": item.get("title"), "snippet": item.get("content"), "url": item.get("url"), "published_at": item.get("published_date"), "source": "Tavily Search API", "query": query}
                for item in rows[:limit]
            ],
            "sources": [source],
            "missing": [],
        }
    except Exception as exc:
        return {"results": [], "sources": [source], "missing": [f"Data Limitation: Tavily search failed for '{query}': {exc}"]}


def _xml_text(node: ET.Element, tag: str) -> str:
    found = node.find(tag)
    return found.text if found is not None and found.text else ""


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for row in rows:
        key = row.get("url") or row.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _dedupe_sources(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen, out = set(), []
    for row in rows:
        key = (row.get("name"), row.get("url"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
