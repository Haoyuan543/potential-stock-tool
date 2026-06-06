from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


TRUSTED_DOMAINS = {
    "sse.net.cn": 100,
    "finmindtrade.com": 95,
    "twse.com.tw": 95,
    "mops.twse.com.tw": 95,
    "money.udn.com": 88,
    "udn.com": 86,
    "ctee.com.tw": 86,
    "moneydj.com": 84,
    "cnyes.com": 84,
    "news.cnyes.com": 84,
    "ettoday.net": 82,
    "ltn.com.tw": 80,
    "reuters.com": 86,
    "bloomberg.com": 86,
    "yahoo.com": 74,
    "news.google.com": 45,
}

KEYWORDS = [
    "scfi",
    "運價",
    "美西",
    "美東",
    "歐洲",
    "紅海",
    "長榮",
    "evergreen",
    "freight",
    "us west",
    "us east",
    "europe",
]


def rank_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(results, key=_score, reverse=True)


def _score(row: dict[str, Any]) -> int:
    url = row.get("url") or ""
    host = urlparse(url).netloc.lower()
    score = 40
    for domain, value in TRUSTED_DOMAINS.items():
        if domain in host:
            score = max(score, value)
    text = f"{row.get('title') or ''} {row.get('snippet') or ''}".lower()
    for keyword in KEYWORDS:
        if keyword.lower() in text:
            score += 3
    row["source_score"] = min(score, 100)
    return row["source_score"]
