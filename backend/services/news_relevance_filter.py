from __future__ import annotations

from typing import Any


KEYWORDS = {
    "長榮": 0.35,
    "長榮海運": 0.4,
    "2603": 0.35,
    "evergreen marine": 0.35,
    "scfi": 0.25,
    "運價": 0.25,
    "freight": 0.22,
    "紅海": 0.2,
    "red sea": 0.2,
    "法說": 0.18,
    "配息": 0.18,
    "填息": 0.18,
    "etf": 0.16,
    "外資": 0.16,
    "投信": 0.16,
    "貨櫃": 0.2,
    "航運": 0.18,
}

POSITIVE = ("上漲", "走揚", "轉強", "旺季", "填息", "positive", "rise", "growth", "strong")
NEGATIVE = ("下跌", "走弱", "衰退", "風險", "賣超", "減碼", "negative", "fall", "weak", "risk")


def filter_relevant_news(news: dict[str, Any]) -> dict[str, Any]:
    articles = news.get("articles") or []
    scored = [_score_article(item) for item in articles]
    scored = sorted(scored, key=lambda item: item["relevance_score"], reverse=True)
    primary = [item for item in scored if item["relevance_score"] >= 0.6]
    low_weight = [item for item in scored if 0.6 <= item["relevance_score"] < 0.8]
    return {
        "articles": primary,
        "low_weight_articles": low_weight,
        "excluded_count": len([item for item in scored if item["relevance_score"] < 0.6]),
        "all_scored": scored[:40],
        "missing_reason": "" if primary else "Data Limitation: no high-relevance news after relevance filtering; lower relevance articles are excluded from core analysis.",
    }


def _score_article(item: dict[str, Any]) -> dict[str, Any]:
    title = item.get("title") or ""
    desc = item.get("description") or item.get("snippet") or ""
    text = f"{title} {desc}".lower()
    score = 0.0
    reasons: list[str] = []
    for keyword, weight in KEYWORDS.items():
        if keyword.lower() in text:
            score += weight
            reasons.append(keyword)
    if item.get("source_score"):
        score += min(0.12, float(item.get("source_score") or 0) / 100)
    score = min(1.0, score)
    has_positive = any(word.lower() in text for word in POSITIVE)
    has_negative = any(word.lower() in text for word in NEGATIVE)
    sentiment = "mixed" if has_positive and has_negative else "positive" if has_positive else "negative" if has_negative else "neutral"
    return {
        "title": title,
        "url": item.get("url"),
        "source": item.get("source"),
        "published_at": item.get("published_at"),
        "relevance_score": round(score, 2),
        "sentiment": sentiment,
        "reason": "、".join(reasons) if reasons else "未命中長榮/運價/紅海/法人/ETF 核心關鍵字。",
    }
