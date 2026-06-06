from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.search.web_search import web_search


WATCHLIST = ["00878", "00919", "0056", "00940", "00929"]
ETF_SOURCES = {
    "00878": "https://www.cathaysite.com.tw/ETF/00878/",
    "00919": "https://www.capitalfund.com.tw/etf/product/00919",
    "0056": "https://www.yuantaetfs.com/product/detail/0056",
    "00940": "https://www.yuantaetfs.com/product/detail/00940",
    "00929": "https://www.fhtrust.com.tw/ETF/00929",
}
POSITIVE_WORDS = ("inflow", "holding", "constituent", "add", "increase", "納入", "持有", "加碼", "買進")
NEGATIVE_WORDS = ("outflow", "reduce", "removed", "sell", "decrease", "剔除", "減碼", "賣出")


def build_etf_flow(symbol: str, news_relevance: dict[str, Any] | None = None) -> dict[str, Any]:
    stock_id = symbol.split(".")[0]
    queries = [
        f"{stock_id} 長榮 ETF 00878 00919 0056 00940 00929 持股 權重",
        "長榮海運 ETF 成分股 權重 00878 00919 0056 00940 00929",
        "2603 Evergreen Marine ETF holding Taiwan",
    ]
    search = web_search(queries, max_results_per_query=4)
    rows = search.get("results", [])
    text = " ".join(f"{row.get('title') or ''} {row.get('snippet') or ''}" for row in rows).lower()
    mentioned = [code for code in WATCHLIST if code in text]
    relevant_news = news_relevance.get("articles", []) if news_relevance else []
    news_mentions = [item for item in relevant_news if "etf" in f"{item.get('title')} {item.get('reason')}".lower()]

    flow = "unknown"
    confidence = 0.0
    coverage_credit = 0.0
    if mentioned:
        confidence = min(0.45, 0.2 + 0.06 * len(set(mentioned)) + 0.03 * len(news_mentions))
        if any(word.lower() in text for word in POSITIVE_WORDS):
            flow = "inferred_bullish"
        elif any(word.lower() in text for word in NEGATIVE_WORDS):
            flow = "inferred_bearish"
        else:
            flow = "neutral"
        coverage_credit = 0.5 if flow.startswith("inferred") else 0.35

    if flow == "unknown":
        missing_reason = "資料不足：尚未取得 ETF 每日持股變化、權重變化與基金規模變化。"
    else:
        missing_reason = (
            "資料限制：ETF 訊號目前來自官網連結與公開搜尋推論；"
            "尚未取得持股變化與基金規模變化，因此信心上限為 0.45，不能大幅加分。"
        )

    sources = [{"name": f"ETF 官方頁 {code}", "url": ETF_SOURCES[code], "as_of": "stale/unknown"} for code in WATCHLIST]
    sources.extend(search.get("sources", []))
    return {
        "etf_flow": flow,
        "top_etfs": mentioned[:5],
        "holding_change": None,
        "aum_change": None,
        "confidence": round(confidence, 2),
        "coverage_credit": coverage_credit,
        "score_boost_allowed": False,
        "sources": sources,
        "as_of": datetime.now(timezone.utc).date().isoformat() if mentioned else None,
        "stale": True,
        "missing_reason": missing_reason,
    }
