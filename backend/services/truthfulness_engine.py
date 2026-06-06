from __future__ import annotations

from typing import Any


P0_KEYWORDS = (
    "SCFI",
    "運價",
    "航線",
    "美西",
    "美東",
    "歐洲線",
    "紅海",
    "股價",
    "法人",
    "OHLCV",
)


def build_truthfulness(payload: dict[str, Any], data_quality: dict[str, Any]) -> dict[str, Any]:
    exact = data_quality.get("exact_data") or []
    scraped = data_quality.get("scraped_data") or []
    inferred = data_quality.get("search_inferred_data") or []
    stale = data_quality.get("stale_or_suspicious_data") or []
    missing = data_quality.get("missing_data") or []
    conflict = data_quality.get("conflict_data") or []

    total = max(1, len(exact) + len(scraped) + len(inferred) + len(stale) + len(missing) + len(conflict))
    exact_share = len(exact) / total
    scraped_share = len(scraped) / total
    inferred_share = len(inferred) / total
    stale_share = len(stale) / total
    missing_share = len(missing) / total
    conflict_share = len(conflict) / total
    p0_missing = _p0_missing_count(missing)

    score = 52
    score += exact_share * 38
    score += scraped_share * 18
    score += min(inferred_share, 0.25) * 10
    score -= max(0, inferred_share - 0.25) * 22
    score -= stale_share * 22
    score -= missing_share * 28
    score -= conflict_share * 40
    score -= p0_missing * 10
    score = max(0, min(100, round(score)))

    warnings: list[str] = []
    if inferred_share > 0.25:
        warnings.append("搜尋推論資料占比偏高，不能做強烈多空結論。")
    if stale:
        warnings.append("存在過期或可疑資料，操作建議必須保守。")
    if p0_missing:
        warnings.append(f"核心資料缺漏 {p0_missing} 項，長榮判斷需降級。")
    if conflict:
        warnings.append("資料之間存在衝突，需先排除衝突再提高信心。")
    if payload.get("data_freshness", {}).get("warning"):
        warnings.append("股價不是即時資料，盤中決策需另行確認即時價格。")

    return {
        "truthfulness_score": score,
        "data_coverage": payload.get("local_scores", {}).get("data_coverage"),
        "exact_data_share": round(exact_share, 2),
        "scraped_data_share": round(scraped_share, 2),
        "search_inferred_share": round(inferred_share, 2),
        "stale_data_share": round(stale_share, 2),
        "missing_data_share": round(missing_share, 2),
        "conflict_data_share": round(conflict_share, 2),
        "p0_missing_count": p0_missing,
        "warnings": warnings,
    }


def _p0_missing_count(items: list[str]) -> int:
    return sum(1 for item in items if any(keyword in item for keyword in P0_KEYWORDS))
