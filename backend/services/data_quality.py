from __future__ import annotations

from typing import Any


def build_data_quality(payload: dict[str, Any], scores: dict[str, Any]) -> dict[str, Any]:
    market = payload.get("market_data", {})
    stock = market.get("stock", {})
    institutional = market.get("institutional", {})
    freight = market.get("freight", {})
    news = market.get("news", {})
    fundamentals = market.get("fundamentals", {})
    announcements = market.get("announcements", {})
    etf = market.get("etf_flow", {})
    red_sea = market.get("red_sea", {})
    announcement_intel = market.get("announcement_intelligence", {})
    regime = market.get("market_regime", {})
    international = market.get("international_events", {})
    fill = market.get("fill_dividend_probability", {})

    exact: list[str] = []
    scraped: list[str] = []
    inferred: list[str] = []
    missing: list[str] = []
    stale: list[str] = []
    conflict: list[str] = []

    _classify_stock(stock, payload, exact, missing, stale)
    _classify_institutional(institutional, exact, missing, stale)
    _classify_freight(freight, exact, scraped, inferred, missing)
    _classify_news(news, market, scraped, inferred, missing)
    _classify_fundamentals(fundamentals, exact, missing)
    _classify_announcements(announcements, announcement_intel, exact, inferred, stale)
    _classify_etf(etf, inferred, stale)
    _classify_red_sea(red_sea, inferred, missing)
    _classify_regime(regime, scraped, inferred, stale, missing)
    _classify_international(international, scraped, inferred, stale)
    _classify_fill(fill, inferred, stale)

    return {
        "exact_data": _dedupe(exact),
        "scraped_data": _dedupe(scraped),
        "search_inferred_data": _dedupe(inferred),
        "missing_data": _dedupe(missing),
        "stale_or_suspicious_data": _dedupe(stale),
        "conflict_data": _dedupe(conflict),
        "data_coverage": scores.get("data_coverage"),
        "coverage_adjusted_score": scores.get("coverage_adjusted_score"),
    }


def _classify_stock(
    stock: dict[str, Any],
    payload: dict[str, Any],
    exact: list[str],
    missing: list[str],
    stale: list[str],
) -> None:
    if stock.get("close") is not None:
        exact.append(
            f"股價與成交量：{stock.get('latest_date') or '日期未知'} "
            f"收盤價 {_fmt_num(stock.get('close'))}，成交量 {_fmt_num(stock.get('volume'), 0)} 股"
        )
    else:
        missing.append("股價 OHLCV：未取得現價或最近收盤價")
    if stock.get("ma20") is not None and stock.get("ma60") is not None:
        exact.append(f"技術指標：20 日均線 {_fmt_num(stock.get('ma20'))}，60 日均線 {_fmt_num(stock.get('ma60'))}")
    else:
        missing.append("技術指標：均線資料不足")
    if stock.get("latest_date") and payload.get("data_freshness", {}).get("warning"):
        stale.append(f"股價資料日期：{stock.get('latest_date')}，非今日即時價，僅能視為最近收盤資料")


def _classify_institutional(
    institutional: dict[str, Any],
    exact: list[str],
    missing: list[str],
    stale: list[str],
) -> None:
    latest = institutional.get("latest") or {}
    if latest:
        exact.append(
            "法人買賣超："
            f"{latest.get('date', '日期未知')} 外資 {_fmt_lots(latest.get('foreign'))}、"
            f"投信 {_fmt_lots(latest.get('trust'))}、自營商 {_fmt_lots(latest.get('dealer'))}、合計 {_fmt_lots(latest.get('total'))}"
        )
    else:
        missing.append("法人買賣超：未取得外資、投信、自營商最新資料")
    if institutional.get("flow_sums"):
        exact.append("法人區間統計：已取得近 1/3/5/10 日買賣超")
    if institutional.get("suspicious_zero_data"):
        stale.append("投信資料可疑：投信多日為 0，可能是資料源分類不完整，需用 TWSE 或券商資料交叉確認")


def _classify_freight(
    freight: dict[str, Any],
    exact: list[str],
    scraped: list[str],
    inferred: list[str],
    missing: list[str],
) -> None:
    intel = freight.get("intelligence") or {}
    if freight.get("scfi_latest") is not None:
        layer = "OCR / 網頁爬取" if freight.get("official_chart_parsed") else "人工補充或結構化資料"
        scraped.append(f"SCFI 綜合指數：{_fmt_num(freight.get('scfi_latest'))}，資料層級：{layer}")
    else:
        missing.append("SCFI 綜合指數：未取得最新數值")

    if freight.get("weekly_change") is not None or freight.get("scfi_streak_weeks") is not None:
        scraped.append(f"SCFI 趨勢：週變化 {_fmt_num(freight.get('weekly_change'))}%，連續週數 {_fmt_num(freight.get('scfi_streak_weeks'), 0)}")

    route_labels = [("us_west", "美西線"), ("us_east", "美東線"), ("europe", "歐洲線")]
    for key, label in route_labels:
        rate = freight.get(key)
        change = freight.get(f"{key}_weekly_change")
        route_intel = intel.get(key) or {}
        if rate is not None or change is not None:
            exact.append(f"{label}運價：{_fmt_num(rate) if rate is not None else '未提供'}，週變化 {_fmt_num(change) if change is not None else '未提供'}%")
        elif route_intel.get("trend") and route_intel.get("trend") != "unknown":
            inferred.append(f"{label}趨勢：{_trend_label(route_intel.get('trend'))}，信心 {route_intel.get('confidence')}，沒有精確運價")
        else:
            missing.append(f"{label}運價與趨勢：未取得")

    if intel.get("overall_trend") and intel.get("overall_trend") != "unknown":
        inferred.append(
            "運價智慧判讀："
            f"方向 {_trend_label(intel.get('overall_trend'))}，強度 {_strength_label(intel.get('strength'))}，"
            f"信心 {intel.get('confidence')}，來源數 {intel.get('source_count')}"
        )
    else:
        missing.append("運價智慧判讀：無法形成可靠方向")


def _classify_news(
    news: dict[str, Any],
    market: dict[str, Any],
    scraped: list[str],
    inferred: list[str],
    missing: list[str],
) -> None:
    articles = news.get("articles") or []
    if articles:
        scraped.append(f"新聞與 RSS：取得 {len(articles)} 則原始新聞或搜尋結果")
    else:
        missing.append("新聞事件：未取得 24~72 小時新聞")
    relevant = market.get("news_relevance", {}).get("articles") or []
    if relevant:
        inferred.append(f"新聞相關度過濾：{len(relevant)} 則納入主分析，其餘降權")
    elif articles:
        stale.append("新聞相關度：有新聞但缺少高相關結果，情緒分數需保守")


def _classify_fundamentals(fundamentals: dict[str, Any], exact: list[str], missing: list[str]) -> None:
    if fundamentals.get("eps") is not None:
        exact.append(f"每股盈餘 EPS：{_fmt_num(fundamentals.get('eps'))}")
    else:
        missing.append("每股盈餘 EPS：未取得")
    if fundamentals.get("dividend_yield") is not None:
        exact.append(f"股利殖利率：{_fmt_num(fundamentals.get('dividend_yield'))}%")
    else:
        missing.append("股利殖利率：未取得")
    if fundamentals.get("monthly_revenue_yoy") is not None:
        exact.append(f"月營收年增率：{_fmt_num(fundamentals.get('monthly_revenue_yoy'))}%")
    else:
        missing.append("月營收年增率：未取得")


def _classify_announcements(
    announcements: dict[str, Any],
    announcement_intel: dict[str, Any],
    exact: list[str],
    inferred: list[str],
    stale: list[str],
) -> None:
    rows = announcements.get("announcements") or []
    status = announcement_intel.get("latest_event", "unknown")
    if rows:
        exact.append(f"公司公告：取得 {len(rows)} 則 MOPS / TWSE 公告資料")
        return
    events = announcement_intel.get("events") or []
    if events:
        inferred.append(f"公告搜尋推論：找到 {len(events)} 則事件線索，狀態 {_event_status_label(status)}")
    if status in {"stale_event_over_14_days", "fetch_failed", "unknown"}:
        stale.append(f"公司公告：狀態 {_event_status_label(status)}，不可解讀為今日無重大公告")


def _classify_etf(etf: dict[str, Any], inferred: list[str], stale: list[str]) -> None:
    flow = etf.get("etf_flow")
    if flow and flow != "unknown":
        inferred.append(
            f"ETF 被動買盤：{_signal_label(flow)}，信心 {etf.get('confidence')}，"
            f"觀察 ETF：{', '.join(etf.get('top_etfs') or []) or '未列出'}"
        )
    else:
        stale.append("ETF 被動買盤：未取得可用訊號")
    if etf.get("holding_change") is None and etf.get("aum_change") is None:
        stale.append("ETF 精確資料：持股變化與基金規模變化缺漏，只能低權重參考搜尋推論")


def _classify_red_sea(red_sea: dict[str, Any], inferred: list[str], missing: list[str]) -> None:
    if red_sea.get("confidence", 0) >= 0.35:
        inferred.append(
            f"紅海與繞航風險：狀態 {_signal_label(red_sea.get('status'))}，"
            f"航運影響 {_signal_label(red_sea.get('shipping_impact'))}，信心 {red_sea.get('confidence')}"
        )
    else:
        missing.append("紅海與繞航風險：未取得可靠狀態")


def _classify_regime(
    regime: dict[str, Any],
    scraped: list[str],
    inferred: list[str],
    stale: list[str],
    missing: list[str],
) -> None:
    snapshot = regime.get("market_snapshot") or {}
    if snapshot:
        scraped.append(f"市場環境快照：取得 {', '.join(snapshot.keys())}")
    if regime.get("market_regime") != "unknown" and regime.get("confidence", 0) >= 0.25:
        inferred.append(
            f"市場環境：{_signal_label(regime.get('market_regime'))}，"
            f"台股 {_signal_label(regime.get('taiwan_market'))}，航運族群 {_signal_label(regime.get('shipping_sector'))}，"
            f"信心 {regime.get('confidence')}"
        )
    else:
        missing.append("市場環境：風險偏好 / 風險趨避判斷不足")
    if regime.get("missing_reason"):
        stale.append(_clean_limitation(regime["missing_reason"]))


def _classify_international(
    international: dict[str, Any],
    scraped: list[str],
    inferred: list[str],
    stale: list[str],
) -> None:
    oil_prices = international.get("oil_prices") or {}
    if oil_prices:
        scraped.append("國際油價：已嘗試抓取 WTI / Brent 或備援報價")
    if international.get("summary"):
        inferred.append(f"國際事件：{international.get('summary')}")
    if international.get("missing_reason"):
        stale.append(_clean_limitation(international["missing_reason"]))


def _classify_fill(fill: dict[str, Any], inferred: list[str], stale: list[str]) -> None:
    if fill.get("fill_probability_90d") is not None:
        inferred.append(f"填息機率：90 日 {round(float(fill.get('fill_probability_90d')) * 100)}%，信心 {fill.get('confidence')}")
    else:
        stale.append("填息機率：資料不足，不能硬估")


def _trend_label(value: Any) -> str:
    return {"up": "上升", "down": "下降", "flat": "持平", "unknown": "未知"}.get(str(value or ""), str(value or "未知"))


def _strength_label(value: Any) -> str:
    return {"strong": "強", "moderate": "中等", "weak": "弱", "unknown": "未知"}.get(str(value or ""), str(value or "未知"))


def _signal_label(value: Any) -> str:
    mapping = {
        "inferred_bullish": "推論偏多",
        "inferred_bearish": "推論偏空",
        "bullish": "偏多",
        "bearish": "偏空",
        "neutral": "中性",
        "risk_on": "風險偏好",
        "risk_off": "風險趨避",
        "high": "高",
        "medium": "中",
        "low": "低",
        "escalating": "升溫",
        "stable": "穩定",
        "improving": "改善",
        "normalizing": "正常化",
        "unknown": "未知",
    }
    return mapping.get(str(value or ""), str(value or "未知"))


def _event_status_label(value: Any) -> str:
    mapping = {
        "today_material_event": "今日有重大事件",
        "recent_event_within_7_days": "近 7 日有事件",
        "stale_event_over_14_days": "事件超過 14 日，僅能當背景",
        "fetch_failed": "公告抓取失敗",
        "unknown": "未知",
        "none": "未發現重大公告",
    }
    return mapping.get(str(value or ""), str(value or "未知"))


def _clean_limitation(value: str) -> str:
    return (
        str(value)
        .replace("Data Limitation: ", "資料限制：")
        .replace("Data Missing: ", "資料不足：")
        .replace("Data Warning: ", "資料提醒：")
    )


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _fmt_num(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "未提供"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if decimals == 0:
        return f"{number:,.0f}"
    return f"{number:,.{decimals}f}"


def _fmt_lots(value: Any) -> str:
    if value is None:
        return "未提供"
    try:
        return f"{float(value) / 1000:,.1f} 張"
    except (TypeError, ValueError):
        return str(value)
