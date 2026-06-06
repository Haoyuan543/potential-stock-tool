from __future__ import annotations

from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from backend.search.web_search import web_search


HIGH_WORDS = ("重大訊息", "配息", "除息", "法說", "獲利", "material", "dividend", "earnings")
MEDIUM_WORDS = ("公告", "法人說明會", "月營收", "conference", "investor", "presentation")
RELEVANT_WORDS = ("長榮", "2603", "evergreen marine", "evergreen", "法說", "公告", "除息", "配息", "dividend", "investor")


def build_announcement_intelligence(symbol: str, announcements: dict[str, Any], manual_context: str = "") -> dict[str, Any]:
    stock_id = symbol.split(".")[0]
    official_events = list(announcements.get("announcements") or [])
    official_missing = list(announcements.get("missing") or [])
    official_fetch_failed = bool(official_missing) and not bool(official_events)
    sources = [
        {"name": "公開資訊觀測站 MOPS", "url": "https://mops.twse.com.tw/"},
        {"name": "TWSE OpenAPI", "url": "https://openapi.twse.com.tw/"},
        {"name": "長榮海運 IR", "url": "https://www.evergreen-marine.com/twn/investors.html"},
    ]

    events = [_normalize_event(row, "官方資料") for row in official_events]
    search_missing: list[str] = []
    if not events or official_fetch_failed:
        search = web_search(
            [
                f"{stock_id} 長榮 重大訊息 公告 除息 配息 法說",
                "長榮海運 法說會 投資人簡報 公告 配息 除息",
                "Evergreen Marine investor relations dividend announcement earnings presentation",
                "Evergreen Marine material information dividend ex-dividend investor conference",
            ],
            max_results_per_query=4,
        )
        sources.extend(search.get("sources", []))
        search_missing = search.get("missing", [])
        events.extend(
            _normalize_event(row, "搜尋推論")
            for row in search.get("results", [])
            if _looks_relevant(row)
        )

    if manual_context.strip():
        events.insert(0, {"date": None, "title": manual_context.strip()[:240], "url": "", "source": "人工補充", "evidence_type": "人工補充"})

    classified = [_classify_event_age(event) for event in events[:20]]
    today_events = [event for event in classified if event.get("age_bucket") == "today_material_event"]
    recent_events = [event for event in classified if event.get("age_bucket") == "recent_event_within_7_days"]
    stale_events = [event for event in classified if event.get("age_bucket") == "stale_event_over_14_days"]

    if today_events:
        latest_event = "today_material_event"
    elif recent_events:
        latest_event = "recent_event_within_7_days"
    elif stale_events:
        latest_event = "stale_event_over_14_days"
    elif official_fetch_failed:
        latest_event = "fetch_failed"
    else:
        latest_event = "unknown"

    materiality = _materiality(today_events or recent_events)
    if latest_event in {"stale_event_over_14_days", "fetch_failed", "unknown"}:
        materiality = "unknown"

    if today_events:
        confidence = min(0.75, 0.35 + 0.1 * len(today_events))
    elif recent_events:
        confidence = min(0.62, 0.28 + 0.08 * len(recent_events))
    elif stale_events:
        confidence = 0.25
    else:
        confidence = 0.0

    if latest_event == "fetch_failed":
        missing_reason = "資料限制：MOPS / TWSE 抓取失敗，而且搜尋沒有可驗證的近期事件；這不等於沒有公告。"
    elif latest_event == "unknown":
        missing_reason = "資料限制：沒有找到清楚且近期的公告事件，仍需以 MOPS 或公司 IR 交叉確認。"
    elif latest_event == "stale_event_over_14_days":
        missing_reason = "資料限制：只找到超過 14 日的事件，可作背景但不可視為今日重大公告。"
    else:
        missing_reason = ""

    return {
        "latest_event": latest_event,
        "materiality": materiality,
        "events": classified,
        "today_material_event": today_events,
        "recent_event_within_7_days": recent_events,
        "stale_event_over_14_days": stale_events,
        "fetch_failed": latest_event == "fetch_failed",
        "confidence": round(confidence, 2),
        "sources": sources,
        "missing_reason": missing_reason,
        "search_missing": search_missing,
    }


def _normalize_event(row: dict[str, Any], evidence_type: str) -> dict[str, Any]:
    return {
        "date": row.get("date") or row.get("published_at"),
        "title": row.get("title") or row.get("subject") or row.get("snippet") or "",
        "url": row.get("url") or row.get("link") or "",
        "source": row.get("source") or row.get("company") or evidence_type,
        "evidence_type": row.get("evidence_type") or evidence_type,
    }


def _looks_relevant(row: dict[str, Any]) -> bool:
    text = f"{row.get('title') or ''} {row.get('snippet') or ''}".lower()
    return any(word.lower() in text for word in RELEVANT_WORDS)


def _materiality(events: list[dict[str, Any]]) -> str:
    if not events:
        return "unknown"
    text = " ".join(str(item.get("title") or "") for item in events).lower()
    if any(word.lower() in text for word in HIGH_WORDS):
        return "high"
    if any(word.lower() in text for word in MEDIUM_WORDS):
        return "medium"
    return "low"


def _classify_event_age(event: dict[str, Any]) -> dict[str, Any]:
    event = dict(event)
    event_date = _parse_event_date(event.get("date") or event.get("published_at"))
    today = date.today()
    if event_date is None:
        event["age_days"] = None
        event["age_bucket"] = "unknown"
        return event
    age = (today - event_date).days
    event["age_days"] = age
    if age <= 1 and _materiality([event]) in {"high", "medium"}:
        bucket = "today_material_event"
    elif age <= 7:
        bucket = "recent_event_within_7_days"
    elif age > 14:
        bucket = "stale_event_over_14_days"
    else:
        bucket = "recent_event_within_7_days"
    event["age_bucket"] = bucket
    return event


def _parse_event_date(value: Any) -> date | None:
    if not value:
        return None
    raw = str(value).strip()
    for parser in (
        lambda x: date.fromisoformat(x[:10]),
        lambda x: datetime.strptime(x, "%Y/%m/%d").date(),
        lambda x: datetime.strptime(x, "%Y%m%d").date(),
        lambda x: parsedate_to_datetime(x).astimezone(timezone.utc).date(),
    ):
        try:
            return parser(raw)
        except Exception:
            pass
    return None
