from __future__ import annotations

from typing import Any


RESOLUTION_ORDER = ["官方 API / 結構化資料", "網頁爬取 / OCR", "RSS / 新聞源", "搜尋推論", "AI 摘要抽取"]


def build_gap_report(payload: dict[str, Any], data_quality: dict[str, Any]) -> dict[str, Any]:
    market = payload.get("market_data", {})
    gaps: list[dict[str, Any]] = []
    for field in data_quality.get("missing_data", []):
        gaps.append(_gap(field, "缺漏", _priority(field), market))
    for field in data_quality.get("stale_or_suspicious_data", []):
        gaps.append(_gap(field, "過期或可疑", _priority(field), market))
    for field in data_quality.get("conflict_data", []):
        gaps.append(_gap(field, "資料衝突", "P0", market))
    return {
        "status": "有待補資料" if gaps else "無重大缺口",
        "resolution_order": RESOLUTION_ORDER,
        "gaps": gaps,
    }


def _gap(field: str, status: str, priority: str, market: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_from_existing_intelligence(field, market)
    if resolved:
        return {
            "gap_id": _gap_id(field),
            "field": field,
            "priority": priority,
            "before_status": status,
            "resolution_status": resolved["resolution_status"],
            "evidence": resolved["evidence"],
            "confidence": resolved["confidence"],
            "remaining_risk": resolved["remaining_risk"],
            "recommended_next_source": resolved["recommended_next_source"],
        }
    return {
        "gap_id": _gap_id(field),
        "field": field,
        "priority": priority,
        "before_status": status,
        "resolution_status": "未補足",
        "evidence": "目前沒有足夠證據補齊此欄位。",
        "confidence": 0.0,
        "remaining_risk": "若此欄位屬核心資料，結論必須降級或維持保守。",
        "recommended_next_source": _next_source(field),
    }


def _resolve_from_existing_intelligence(field: str, market: dict[str, Any]) -> dict[str, Any] | None:
    freight = market.get("freight", {})
    intel = freight.get("intelligence") or {}
    if any(key in field for key in ("SCFI", "運價", "航線", "美西", "美東", "歐洲")):
        confidence = float(intel.get("confidence") or 0)
        trend = intel.get("overall_trend")
        if trend and trend != "unknown" and confidence >= 0.45:
            return {
                "resolution_status": "已用多來源趨勢部分補足",
                "evidence": f"運價智慧判讀顯示方向 {_trend_label(trend)}，信心 {confidence}，來源數 {intel.get('source_count')}",
                "confidence": round(confidence, 2),
                "remaining_risk": "方向可用於研判，但若缺精確運價，不能做精準 EPS 或估值推算。",
                "recommended_next_source": "SSE / Freightos / Drewry 或付費航線資料",
            }
    red = market.get("red_sea", {})
    if "紅海" in field and red.get("status") != "unknown" and red.get("confidence", 0) >= 0.4:
        return {
            "resolution_status": "已用新聞與搜尋推論部分補足",
            "evidence": f"紅海狀態 {_signal_label(red.get('status'))}，航運影響 {_signal_label(red.get('shipping_impact'))}，信心 {red.get('confidence')}",
            "confidence": red.get("confidence", 0),
            "remaining_risk": "仍需路透、Lloyd's List 或船公司公告交叉確認。",
            "recommended_next_source": "Reuters、Lloyd's List、Maersk / Hapag-Lloyd / CMA CGM 公告",
        }
    etf = market.get("etf_flow", {})
    if "ETF" in field and etf.get("etf_flow") != "unknown":
        return {
            "resolution_status": "僅低權重補足",
            "evidence": f"ETF 訊號 {_signal_label(etf.get('etf_flow'))}，信心 {etf.get('confidence')}，但缺持股變化與基金規模變化",
            "confidence": min(float(etf.get("confidence") or 0), 0.45),
            "remaining_risk": "不可把 ETF 推論當成實際被動買盤。",
            "recommended_next_source": "ETF 官方持股 CSV / PDF、投信官網、集保或基金規模資料",
        }
    return None


def _priority(field: str) -> str:
    if any(keyword in field for keyword in ("SCFI", "運價", "航線", "美西", "美東", "歐洲", "紅海", "股價", "法人")):
        return "P0"
    if any(keyword in field for keyword in ("ETF", "公告", "法說", "市場環境", "填息", "EPS", "股利")):
        return "P1"
    return "P2"


def _next_source(field: str) -> str:
    if any(keyword in field for keyword in ("SCFI", "運價", "航線", "美西", "美東", "歐洲")):
        return "優先接官方或付費航運資料；無法取得時才用搜尋推論。"
    if "ETF" in field:
        return "ETF 官方持股、基金規模與成分股權重資料。"
    if any(keyword in field for keyword in ("公告", "法說")):
        return "MOPS、TWSE OpenAPI、長榮 IR 頁面。"
    if "市場環境" in field:
        return "台股加權指數、航運類股指數、VIX、DXY、USD/TWD。"
    return "官方 API 優先，其次網頁爬取、RSS、搜尋推論。"


def _gap_id(field: str) -> str:
    return field.lower().replace(" ", "_").replace("/", "_")[:80]


def _trend_label(value: Any) -> str:
    return {"up": "上升", "down": "下降", "flat": "持平", "unknown": "未知"}.get(str(value or ""), str(value or "未知"))


def _signal_label(value: Any) -> str:
    return {
        "inferred_bullish": "推論偏多",
        "inferred_bearish": "推論偏空",
        "bullish": "偏多",
        "bearish": "偏空",
        "neutral": "中性",
        "escalating": "升溫",
        "stable": "穩定",
        "improving": "改善",
        "normalizing": "正常化",
        "high": "高",
        "medium": "中",
        "low": "低",
    }.get(str(value or ""), str(value or "未知"))
