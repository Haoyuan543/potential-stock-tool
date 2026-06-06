from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from backend.search.web_search import web_search


QUERIES = [
    "Red Sea shipping latest container",
    "Suez Canal container shipping latest",
    "Houthi shipping attacks latest",
    "Maersk Red Sea latest update",
    "Hapag-Lloyd Red Sea latest update",
    "CMA CGM Red Sea latest update",
    "Reuters Red Sea shipping container rates",
    "Lloyd's List Red Sea shipping latest",
]
ESCALATING_WORDS = ("attack", "attacks", "houthi", "missile", "drone", "escalat", "rerout", "divert", "cape of good hope")
STABLE_WORDS = ("continue", "ongoing", "remain", "stays", "suspended", "avoid")
NORMALIZING_WORDS = ("resume", "return to suez", "normalizing", "normalise", "reopen")


def build_red_sea_intelligence(news: dict[str, Any] | None = None) -> dict[str, Any]:
    search = web_search(QUERIES, max_results_per_query=3)
    rows = search.get("results", [])
    articles = (news or {}).get("red_sea_shipping_context") or []
    evidence_rows = rows + articles
    text = " ".join(
        f"{row.get('title') or ''} {row.get('snippet') or row.get('description') or ''}"
        for row in evidence_rows
    ).lower()

    escalating = _count_matches(text, ESCALATING_WORDS)
    stable = _count_matches(text, STABLE_WORDS)
    normalizing = _count_matches(text, NORMALIZING_WORDS)

    if normalizing >= max(escalating, stable) and normalizing:
        status, impact, suez_risk = "normalizing", "low", "high"
    elif escalating >= max(stable, normalizing) and escalating:
        status, impact, suez_risk = "escalating", "high", "low"
    elif stable:
        status, impact, suez_risk = "stable", "medium", "medium"
    else:
        status, impact, suez_risk = "unknown", "unknown", "unknown"

    independent_sources = {_domain(row.get("url")) for row in evidence_rows if row.get("url")}
    confidence = 0.0 if status == "unknown" else min(0.82, 0.32 + 0.09 * len(independent_sources))
    return {
        "status": status,
        "shipping_impact": impact,
        "suez_return_risk": suez_risk,
        "summary": _summary(status, impact, suez_risk, len(independent_sources)),
        "confidence": round(confidence, 2),
        "sources": search.get("sources", []),
        "evidence_count": len(evidence_rows),
        "independent_sources": sorted(source for source in independent_sources if source and source != "unknown"),
        "missing_reason": "" if status != "unknown" else "資料限制：紅海資料目前只能由新聞與公開搜尋推論，未取得官方可量化事件資料。",
    }


def _count_matches(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for word in words if word.lower() in text)


def _summary(status: str, impact: str, suez_risk: str, source_count: int) -> str:
    impact_label = {"high": "高", "medium": "中", "low": "低", "unknown": "未知"}.get(impact, impact)
    suez_label = {"high": "高", "medium": "中", "low": "低", "unknown": "未知"}.get(suez_risk, suez_risk)
    if status == "normalizing":
        return f"公開來源顯示紅海或蘇伊士航線有正常化跡象，對運價支撐降低；蘇伊士回流風險 {suez_label}，來源數 {source_count}。"
    if status == "escalating":
        return f"公開來源仍顯示紅海航運風險，繞航對貨櫃運價支撐偏高；對航運影響 {impact_label}，來源數 {source_count}。"
    if status == "stable":
        return f"公開來源顯示紅海風險仍在，但沒有明顯升溫；對航運影響 {impact_label}，蘇伊士回流風險 {suez_label}，來源數 {source_count}。"
    return "目前沒有足夠公開資料判斷紅海或蘇伊士航運狀態。"


def _domain(url: Any) -> str:
    try:
        return urlparse(str(url)).netloc.lower() or "unknown"
    except Exception:
        return "unknown"
