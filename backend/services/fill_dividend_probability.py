from __future__ import annotations

from typing import Any


def estimate_fill_dividend_probability(
    fundamentals: dict[str, Any],
    stock: dict[str, Any],
    freight: dict[str, Any],
    institutional: dict[str, Any],
    etf_flow: dict[str, Any],
    market_regime: dict[str, Any],
) -> dict[str, Any]:
    dividend = fundamentals.get("cash_dividend") or fundamentals.get("dividend") or fundamentals.get("dividend_rate")
    if dividend is None:
        return _missing("Data Missing: cash dividend or ex-dividend context unavailable.")

    missing_count = 0
    factors: list[str] = []
    risks: list[str] = []
    freight_intel = freight.get("intelligence") or {}
    historical_fill_score = None
    freight_score = None
    institutional_score = 50
    etf_score = None
    technical_score = 50
    market_regime_score = None

    if freight_intel.get("overall_trend") == "up" and freight_intel.get("confidence", 0) >= 0.55:
        freight_score = 70 if freight_intel.get("strength") != "strong" else 80
        factors.append("運價情報偏多，有利填息敘事。")
    elif freight_intel.get("overall_trend") == "down" and freight_intel.get("confidence", 0) >= 0.55:
        freight_score = 35
        risks.append("運價情報偏空，降低填息信心。")
    else:
        missing_count += 1
        risks.append("Freight Intelligence 信心不足。")

    trend = institutional.get("consecutive_trend", {})
    if trend.get("direction") == "buy":
        institutional_score = 62
        factors.append("法人籌碼偏買。")
    elif trend.get("direction") == "sell":
        institutional_score = 42
        risks.append("法人連賣降低填息信心。")

    if etf_flow.get("etf_flow") == "bullish":
        etf_score = 65
        factors.append("ETF 被動買盤有正式支撐。")
    elif etf_flow.get("etf_flow") == "inferred_bullish":
        etf_score = 52
        risks.append("ETF 只屬搜尋推論，尚未取得實際持股變化與基金規模變化，不能大幅加分。")
    elif etf_flow.get("etf_flow") in {"bearish", "inferred_bearish"}:
        etf_score = 35
        risks.append("ETF flow 偏空或轉弱。")
    else:
        missing_count += 1

    if market_regime.get("market_regime") == "risk_on" and market_regime.get("confidence", 0) >= 0.5:
        market_regime_score = 65
        factors.append("市場環境 risk-on。")
    elif market_regime.get("market_regime") == "risk_off" and market_regime.get("confidence", 0) >= 0.5:
        market_regime_score = 35
        risks.append("市場環境 risk-off。")
    else:
        missing_count += 1
        risks.append("市場環境信心不足。")

    technical = stock.get("technical") or {}
    if technical.get("rsi14") and technical["rsi14"] > 75:
        technical_score = 38
        risks.append("RSI 過熱，短線不利追價填息。")
    elif stock.get("close") is not None and stock.get("ma20") is not None and stock["close"] > stock["ma20"]:
        technical_score = 58
        factors.append("股價站上 20MA。")
    else:
        missing_count += 1

    components = [value for value in [historical_fill_score, freight_score, institutional_score, etf_score, technical_score, market_regime_score] if value is not None]
    if len(components) < 4:
        confidence = max(0.0, 0.35 - missing_count * 0.05)
    else:
        confidence = 0.35 + (0.15 if freight_intel.get("confidence", 0) >= 0.55 else 0) + (0.1 if market_regime.get("confidence", 0) >= 0.5 else 0)
        confidence -= min(0.25, missing_count * 0.06)
    score = sum(components) / len(components) if components else 45
    score = max(0, min(100, score))
    confidence = round(max(0.0, min(0.75, confidence)), 2)
    if confidence < 0.35:
        return {
            "fill_probability_30d": None,
            "fill_probability_90d": None,
            "fill_probability_1y": None,
            "expected_days": None,
            "confidence": confidence,
            "historical_fill_score": historical_fill_score,
            "freight_score": freight_score,
            "institutional_score": institutional_score,
            "etf_score": etf_score,
            "technical_score": technical_score,
            "market_regime_score": market_regime_score,
            "key_factors": factors,
            "risks": risks + ["資料不足，填息機率不硬估。"],
        }
    return {
        "fill_probability_30d": round(max(0, min(0.85, (score - 25) / 100)), 2),
        "fill_probability_90d": round(max(0, min(0.9, score / 100)), 2),
        "fill_probability_1y": round(max(0, min(0.95, (score + 10) / 100)), 2),
        "expected_days": int(max(20, min(240, 160 - score))) if confidence >= 0.45 else None,
        "confidence": confidence,
        "historical_fill_score": historical_fill_score,
        "freight_score": freight_score,
        "institutional_score": institutional_score,
        "etf_score": etf_score,
        "technical_score": technical_score,
        "market_regime_score": market_regime_score,
        "key_factors": factors,
        "risks": risks,
    }


def _missing(reason: str) -> dict[str, Any]:
    return {
        "fill_probability_30d": None,
        "fill_probability_90d": None,
        "fill_probability_1y": None,
        "expected_days": None,
        "confidence": 0.0,
        "historical_fill_score": None,
        "freight_score": None,
        "institutional_score": None,
        "etf_score": None,
        "technical_score": None,
        "market_regime_score": None,
        "key_factors": [],
        "risks": [reason],
    }
