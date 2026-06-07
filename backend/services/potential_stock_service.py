from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any
from uuid import uuid4

from backend.models import (
    DataPoint,
    MarketDataset,
    PaperPortfolio,
    PaperTradeDecision,
    PotentialBacktestReport,
    PotentialBacktestRequest,
    PotentialStockAnalysis,
    PotentialStockReport,
    PotentialStockRequest,
    PriceBar,
)
from backend.services.fetchers import MarketDataFetcher
from backend.services.openai_service import OpenAIResearchService
from backend.services.research_collector import ResearchCollectRequest, ResearchCollectorService
from backend.services.storage import (
    potential_stock_case_store,
    potential_stock_ledger_store,
    potential_stock_settings_store,
    potential_stock_store,
)


TW_TZ = timezone(timedelta(hours=8))


class PotentialStockService:
    STOCK_NAMES = {
        "2330.TW": "台積電",
        "2454.TW": "聯發科",
        "2303.TW": "聯電",
        "2379.TW": "瑞昱",
        "3034.TW": "聯詠",
        "3711.TW": "日月光投控",
        "3443.TW": "創意",
        "3661.TW": "世芯-KY",
        "2317.TW": "鴻海",
        "2382.TW": "廣達",
        "3231.TW": "緯創",
        "2356.TW": "英業達",
        "6669.TW": "緯穎",
        "3017.TW": "奇鋐",
        "2308.TW": "台達電",
        "4938.TW": "和碩",
        "2603.TW": "長榮",
        "2609.TW": "陽明",
        "2615.TW": "萬海",
        "2002.TW": "中鋼",
        "1301.TW": "台塑",
        "1303.TW": "南亞",
        "1513.TW": "中興電",
        "2049.TW": "上銀",
        "2881.TW": "富邦金",
        "2882.TW": "國泰金",
        "2884.TW": "玉山金",
        "2885.TW": "元大金",
        "2886.TW": "兆豐金",
        "2891.TW": "中信金",
        "2892.TW": "第一金",
        "5876.TW": "上海商銀",
    }
    UNIVERSES = {
        "semiconductor": ["2330.TW", "2454.TW", "2303.TW", "2379.TW", "3034.TW", "3711.TW", "3443.TW", "3661.TW"],
        "electronics": ["2317.TW", "2382.TW", "3231.TW", "2356.TW", "6669.TW", "3017.TW", "2308.TW", "4938.TW"],
        "industrial": ["2603.TW", "2609.TW", "2615.TW", "2002.TW", "1301.TW", "1303.TW", "1513.TW", "2049.TW"],
        "financial": ["2881.TW", "2882.TW", "2884.TW", "2885.TW", "2886.TW", "2891.TW", "2892.TW", "5876.TW"],
    }
    US_TECH_LEADERS = ["NVDA", "AMD", "AVGO", "TSM", "ASML", "AMAT", "LRCX", "KLAC", "MU", "QQQ", "SMH", "SOXX"]
    HIGH_US_TECH_EXPOSURE = {"2330.TW", "2454.TW", "2303.TW", "2379.TW", "3034.TW", "3711.TW", "3443.TW", "3661.TW"}
    MEDIUM_US_TECH_EXPOSURE = {"2317.TW", "2382.TW", "3231.TW", "2356.TW", "6669.TW", "3017.TW", "2308.TW", "4938.TW"}
    DEFAULT_SYMBOLS = ["2330.TW", "2454.TW", "2303.TW", "2379.TW", "3034.TW", "3711.TW", "3443.TW", "3661.TW"]

    def __init__(self) -> None:
        self.fetcher = MarketDataFetcher()
        self.ai = OpenAIResearchService()
        self.research_collector = ResearchCollectorService()
        self.research_collector.fetcher = self.fetcher

    def active_case_id(self) -> str:
        rows = potential_stock_case_store.all()
        rows.sort(key=lambda item: str(item.get("created_at") or ""))
        for row in reversed(rows):
            if row.get("event") in {"case_started", "case_selected"} and row.get("case_id"):
                return str(row["case_id"])
        return "default"

    def cases(self) -> dict[str, Any]:
        active_case_id = self.active_case_id()
        rows = potential_stock_case_store.all()
        started = [row for row in rows if row.get("event") == "case_started"]
        if not started:
            started = [
                {
                    "case_id": "default",
                    "case_name": "預設案件",
                    "created_at": "",
                    "event": "case_started",
                    "archived_previous_case_id": "",
                    "note": "系統預設案件，舊資料沒有 case_id 時會歸入此案件。",
                }
            ]
        report_rows = potential_stock_store.all()
        ledger_rows = potential_stock_ledger_store.all()
        has_default_records = any(self._record_case_id(item) == "default" for item in report_rows + ledger_rows)
        has_default_case = any(str(row.get("case_id") or "") == "default" for row in started)
        if has_default_records and not has_default_case:
            started.append(
                {
                    "case_id": "default",
                    "case_name": "預設案件",
                    "created_at": "",
                    "event": "case_started",
                    "archived_previous_case_id": "",
                    "note": "既有未分案資料會顯示在預設案件。",
                }
            )
        cases = []
        for row in started:
            case_id = str(row.get("case_id") or "default")
            reports = [item for item in report_rows if self._record_case_id(item) == case_id]
            ledgers = [item for item in ledger_rows if self._record_case_id(item) == case_id]
            ledgers.sort(key=lambda item: str(item.get("generated_at") or ""))
            dates = sorted({str(item.get("trading_date") or "") for item in reports if item.get("trading_date")})
            latest_value = self._float_or_none(ledgers[-1].get("total_value")) if ledgers else None
            initial_capital = self._case_initial_capital(reports, ledgers)
            cases.append(
                {
                    "case_id": case_id,
                    "case_name": row.get("case_name") or self._case_name(case_id),
                    "created_at": row.get("created_at") or "",
                    "archived_previous_case_id": row.get("archived_previous_case_id") or "",
                    "active": case_id == active_case_id,
                    "report_count": len(reports),
                    "ledger_count": len(ledgers),
                    "initial_capital": initial_capital,
                    "capital_locked": bool(reports or ledgers),
                    "first_trading_date": dates[0] if dates else "",
                    "last_trading_date": dates[-1] if dates else "",
                    "latest_account_value": latest_value,
                    "note": row.get("note") or "",
                }
            )
        cases.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {"active_case_id": active_case_id, "cases": cases}

    def _case_initial_capital(self, reports: list[dict[str, Any]], ledgers: list[dict[str, Any]]) -> float | None:
        combined = sorted(reports + ledgers, key=lambda item: str(item.get("generated_at") or ""))
        for row in combined:
            for value in (
                row.get("initial_capital"),
                (row.get("portfolio") or {}).get("initial_capital"),
                (row.get("settings") or {}).get("initial_capital"),
            ):
                parsed = self._float_or_none(value)
                if parsed and parsed > 0:
                    return parsed
        return None

    def reset_case(self, note: str = "") -> dict[str, Any]:
        now = datetime.now(TW_TZ)
        previous = self.active_case_id()
        case_id = f"case-{now.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        record = {
            "event": "case_started",
            "case_id": case_id,
            "case_name": self._case_name(case_id),
            "created_at": now.isoformat(),
            "archived_previous_case_id": previous,
            "note": note or "重新開始追蹤；舊資料保留但不作為目前案件。",
        }
        potential_stock_case_store.append(record)
        return {"active_case_id": case_id, "archived_case_id": previous, "case": record, "cases": self.cases()["cases"]}

    def switch_case(self, case_id: str) -> dict[str, Any]:
        target = str(case_id or "").strip() or "default"
        known_case_ids = {str(row.get("case_id") or "default") for row in potential_stock_case_store.all()}
        known_case_ids.update(self._record_case_id(row) for row in potential_stock_store.all())
        known_case_ids.update(self._record_case_id(row) for row in potential_stock_ledger_store.all())
        if target not in known_case_ids:
            return {"active_case_id": self.active_case_id(), "selected": False, "error": f"Unknown case_id: {target}", "cases": self.cases()["cases"]}
        potential_stock_case_store.append(
            {
                "event": "case_selected",
                "case_id": target,
                "case_name": self._case_name(target),
                "created_at": datetime.now(TW_TZ).isoformat(),
                "note": "切換目前追蹤支線。",
            }
        )
        return {"active_case_id": target, "selected": True, "cases": self.cases()["cases"]}

    def delete_case(self, case_id: str) -> dict[str, Any]:
        target = str(case_id or "").strip() or "default"
        reports_before = potential_stock_store.all()
        ledgers_before = potential_stock_ledger_store.all()
        cases_before = potential_stock_case_store.all()

        reports_after = [row for row in reports_before if self._record_case_id(row) != target]
        ledgers_after = [row for row in ledgers_before if self._record_case_id(row) != target]
        cases_after = [row for row in cases_before if str(row.get("case_id") or "default") != target]

        potential_stock_store.replace_all(reports_after)
        potential_stock_ledger_store.replace_all(ledgers_after)
        potential_stock_case_store.replace_all(cases_after)

        return {
            "deleted_case_id": target,
            "deleted_reports": len(reports_before) - len(reports_after),
            "deleted_ledgers": len(ledgers_before) - len(ledgers_after),
            "deleted_case_records": len(cases_before) - len(cases_after),
            "active_case_id": self.active_case_id(),
            "cases": self.cases()["cases"],
        }

    def delete_all_cases(self) -> dict[str, Any]:
        deleted_reports = len(potential_stock_store.all())
        deleted_ledgers = len(potential_stock_ledger_store.all())
        deleted_case_records = len(potential_stock_case_store.all())
        potential_stock_store.clear()
        potential_stock_ledger_store.clear()
        potential_stock_case_store.clear()
        return {
            "deleted_reports": deleted_reports,
            "deleted_ledgers": deleted_ledgers,
            "deleted_case_records": deleted_case_records,
            "active_case_id": "default",
            "cases": self.cases()["cases"],
        }

    async def run(self, request: PotentialStockRequest) -> PotentialStockReport:
        request = request.model_copy(update={"report_session": self._resolve_report_session(request.report_session)})
        case_id = self.active_case_id()
        existing = self._today_report_record(request.report_session, case_id=case_id) if request.persist else None
        if existing:
            return self._report_from_record(existing)

        symbols = self._symbols_for_request(request)
        if request.use_live_data:
            datasets = await self._datasets_for_symbols(symbols, include_us_tech=request.use_us_tech_leading)
        else:
            datasets = [MarketDataset(ticker=symbol, limitations=["Data Missing: live data disabled for this run."]) for symbol in symbols]

        us_tech_context = self.research_collector.latest_us_tech_context(max_age_minutes=720) if request.use_live_data and request.use_us_tech_leading else None
        if us_tech_context is None:
            us_tech_context = await self._build_us_tech_context(request)
        analyses = [self._analyze_dataset(dataset, request, us_tech_context=us_tech_context) for dataset in datasets]
        analyses.sort(key=lambda item: item.score, reverse=True)
        if request.report_session == "market_hours" and not request.persist:
            portfolio = self._analysis_only_portfolio(analyses, request)
        elif request.report_session == "pre_market":
            portfolio = self._premarket_plan_portfolio(analyses, request)
        elif request.report_session == "post_market":
            portfolio = self._postmarket_settlement_portfolio(analyses, request, case_id=case_id)
        else:
            portfolio = self._paper_trade_with_ledger(analyses, request, case_id=case_id)
        market_stance = self._market_stance(analyses)
        limitations = self._friendly_data_messages(sorted({item for analysis in analyses for item in analysis.data_limitations}))
        markdown = self._markdown(request, market_stance, analyses, portfolio, limitations)
        ai_summary = ""
        ai_mode = "disabled"
        ai_error = ""
        if request.use_ai_analysis:
            ai_result = await self._ai_research_summary(request, market_stance, analyses, portfolio, limitations)
            ai_summary = str(ai_result.get("summary_markdown") or "")
            ai_mode = "openai" if ai_result.get("analysis_mode") == "openai" else "fallback"
            ai_error = str(ai_result.get("openai_error") or "")
            if ai_summary:
                markdown = f"{markdown}\n\n## AI 深度解讀\n\n{ai_summary}\n"
            elif ai_error:
                limitations.append(f"OpenAI 深度解讀未完成：{ai_error}")
        report = PotentialStockReport(
            report_session=request.report_session,
            market_stance=market_stance,
            analyses=analyses,
            portfolio=portfolio,
            markdown=markdown,
            data_limitations=limitations,
            ai_summary=ai_summary,
            ai_mode=ai_mode,
            ai_error=ai_error,
        )
        if request.persist:
            self.save_report(report, request, case_id=case_id)
            if request.report_session in {"market_hours", "post_market"}:
                self.save_ledger(report, request, case_id=case_id)
        return report

    async def _datasets_for_symbols(self, symbols: list[str], include_us_tech: bool = False) -> list[MarketDataset]:
        normalized = self._normalize_symbols(symbols)
        missing: list[str] = []
        for symbol in normalized:
            cached = self.research_collector.latest_dataset(symbol, max_age_minutes=240)
            if not cached or self._data_score(cached) < 70:
                missing.append(symbol)
        needs_us_tech = include_us_tech and self.research_collector.latest_us_tech_context(max_age_minutes=720) is None
        if missing or needs_us_tech:
            try:
                await self.research_collector.collect(
                    ResearchCollectRequest(
                        symbols=missing,
                        include_us_tech=needs_us_tech,
                        max_symbols=max(1, len(missing)),
                    )
                )
            except Exception:
                pass
        datasets: list[MarketDataset] = []
        for symbol in normalized:
            cached = self.research_collector.latest_dataset(symbol, max_age_minutes=240)
            if cached and self._data_score(cached) >= 70:
                datasets.append(cached)
                continue
            dataset = await self.fetcher.collect(self._finmind_symbol(symbol))
            dataset.ticker = symbol
            datasets.append(dataset)
        return datasets

    def save_report(self, report: PotentialStockReport, request: PotentialStockRequest, case_id: str | None = None) -> None:
        generated_at = datetime.now(TW_TZ)
        case_id = case_id or self.active_case_id()
        potential_stock_store.append(
            {
                "case_id": case_id,
                "generated_at": generated_at.isoformat(),
                "trading_date": generated_at.date().isoformat(),
                "report_session": report.report_session,
                "market_universe": request.market_universe,
                "initial_capital": request.initial_capital,
                "max_positions": request.max_positions,
                "max_position_pct": request.max_position_pct,
                "buy_score": request.buy_score,
                "watch_score": request.watch_score,
                "sell_score": request.sell_score,
                "stop_loss_pct": request.stop_loss_pct,
                "take_profit_pct": request.take_profit_pct,
                "swap_score_gap": request.swap_score_gap,
                "min_hold_days": request.min_hold_days,
                "benchmark_symbol": request.benchmark_symbol,
                "strategy_version": request.strategy_version,
                "risk_reward_profile": request.risk_reward_profile,
                "investment_horizon": request.investment_horizon,
                "market_stance": report.market_stance,
                "portfolio": report.portfolio.model_dump(mode="json"),
                "analyses": [item.model_dump(mode="json") for item in report.analyses],
                "markdown": report.markdown,
                "data_limitations": report.data_limitations,
                "ai_mode": report.ai_mode,
                "ai_error": report.ai_error,
                "ai_summary": report.ai_summary,
                "immutable": report.report_session in {"pre_market", "market_hours", "post_market"},
            }
        )

    def save_ledger(self, report: PotentialStockReport, request: PotentialStockRequest, case_id: str | None = None) -> None:
        generated_at = datetime.now(TW_TZ)
        case_id = case_id or self.active_case_id()
        candidates = [
            {
                "symbol": item.symbol,
                "company_name": item.company_name,
                "score": item.score,
                "action": item.action,
                "price": item.latest_price,
                "strategy_version": request.strategy_version,
            }
            for item in report.analyses
        ]
        potential_stock_ledger_store.append(
            {
                "case_id": case_id,
                "generated_at": generated_at.isoformat(),
                "trading_date": generated_at.date().isoformat(),
                "report_session": report.report_session,
                "strategy_version": request.strategy_version,
                "initial_capital": report.portfolio.initial_capital,
                "cash": report.portfolio.cash,
                "invested_value": report.portfolio.invested_value,
                "total_value": report.portfolio.total_value,
                "return_pct": report.portfolio.return_pct,
                "realized_pl": report.portfolio.realized_pl,
                "unrealized_pl": report.portfolio.unrealized_pl,
                "costs": report.portfolio.costs,
                "holdings": report.portfolio.holdings,
                "trades": [item.model_dump(mode="json") for item in report.portfolio.trades],
                "candidates": candidates,
                "benchmark": report.portfolio.benchmark,
                "settings": self._strategy_settings(request),
            }
        )

    def latest_ledger(self, case_id: str | None = None) -> dict[str, Any] | None:
        selected_case_id = case_id or self.active_case_id()
        rows = [row for row in potential_stock_ledger_store.all() if self._record_case_id(row) == selected_case_id]
        rows.sort(key=lambda item: str(item.get("generated_at") or ""))
        return rows[-1] if rows else None

    def default_settings(self) -> dict[str, Any]:
        request = PotentialStockRequest(symbols=self.DEFAULT_SYMBOLS, market_universes=["semiconductor", "electronics"])
        return self._settings_from_request(request)

    def settings(self) -> dict[str, Any]:
        rows = [row for row in potential_stock_settings_store.all() if row.get("event") == "settings_saved"]
        rows.sort(key=lambda item: str(item.get("saved_at") or ""))
        default_settings = self.default_settings()
        if not rows:
            return {"settings": default_settings, "saved_at": "", "source": "default"}
        latest = rows[-1]
        raw_settings = latest.get("settings") or {}
        try:
            parsed = self._request_from_settings(raw_settings).model_dump(mode="json")
        except Exception:
            parsed = default_settings
        return {
            "settings": {**default_settings, **parsed},
            "saved_at": latest.get("saved_at") or "",
            "source": "saved",
        }

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        request = self._request_from_settings(settings)
        normalized = self._settings_from_request(request)
        record = {
            "event": "settings_saved",
            "saved_at": datetime.now(TW_TZ).isoformat(),
            "settings": normalized,
        }
        potential_stock_settings_store.append(record)
        return {"settings": normalized, "saved_at": record["saved_at"], "source": "saved"}

    def request_from_saved_settings(self, report_session: str, persist: bool = True) -> PotentialStockRequest:
        settings = self.settings()["settings"]
        settings = {**settings, "report_session": report_session, "persist": persist}
        return self._request_from_settings(settings)

    def sequence_check(self, report_session: str, persist: bool = True, case_id: str | None = None) -> dict[str, Any]:
        session = self._resolve_report_session(report_session)
        if not persist or session == "pre_market":
            return {"allowed": True, "report_session": session, "required_session": ""}
        required = "pre_market" if session == "market_hours" else "market_hours"
        selected_case_id = case_id or self.active_case_id()
        if self._today_report_record(required, case_id=selected_case_id):
            return {"allowed": True, "report_session": session, "required_session": required}
        labels = {"pre_market": "盤前分析選股", "market_hours": "盤中模擬交易", "post_market": "盤後結算"}
        return {
            "allowed": False,
            "report_session": session,
            "required_session": required,
            "case_id": selected_case_id,
            "reason": f"今日尚未完成{labels[required]}，所以先略過{labels[session]}，避免流程順序錯亂。",
        }

    def history(self, limit: int = 30, case_id: str | None = None) -> list[dict[str, Any]]:
        selected_case_id = case_id or self.active_case_id()
        rows = [row for row in potential_stock_store.all() if self._record_case_id(row) == selected_case_id]
        rows.sort(key=lambda item: str(item.get("generated_at") or ""))
        return rows[-limit:]

    def _today_report_record(self, report_session: str, case_id: str | None = None) -> dict[str, Any] | None:
        if report_session not in {"pre_market", "market_hours", "post_market"}:
            return None
        today = datetime.now(TW_TZ).date().isoformat()
        selected_case_id = case_id or self.active_case_id()
        rows = [
            row
            for row in self.history(limit=2000, case_id=selected_case_id)
            if row.get("trading_date") == today and row.get("report_session") == report_session
        ]
        rows.sort(key=lambda item: str(item.get("generated_at") or ""))
        return rows[0] if rows else None

    def _report_from_record(self, row: dict[str, Any]) -> PotentialStockReport:
        generated_at = row.get("generated_at")
        try:
            parsed_generated_at = datetime.fromisoformat(str(generated_at)) if generated_at else datetime.now(TW_TZ)
        except ValueError:
            parsed_generated_at = datetime.now(TW_TZ)
        analyses = [PotentialStockAnalysis.model_validate(item) for item in row.get("analyses") or []]
        portfolio = PaperPortfolio.model_validate(row.get("portfolio") or {})
        markdown = str(row.get("markdown") or "").strip()
        if not markdown:
            markdown = self._immutable_record_markdown(row, analyses, portfolio)
        limitations = self._friendly_data_messages(list(row.get("data_limitations") or []))
        immutable_note = "已有不可變紀錄：existing daily plan/trade data was replayed without changing trade decisions."
        if immutable_note not in limitations:
            limitations.append(immutable_note)
        return PotentialStockReport(
            generated_at=parsed_generated_at,
            report_session=row.get("report_session"),
            market_stance=str(row.get("market_stance") or ""),
            analyses=analyses,
            portfolio=portfolio,
            markdown=markdown,
            data_limitations=limitations,
            ai_summary=str(row.get("ai_summary") or ""),
            ai_mode=row.get("ai_mode") or "disabled",
            ai_error=str(row.get("ai_error") or ""),
        )

    def _immutable_record_markdown(self, row: dict[str, Any], analyses: list[PotentialStockAnalysis], portfolio: PaperPortfolio) -> str:
        session_title = {"pre_market": "盤前計畫", "market_hours": "盤中模擬", "post_market": "盤後結算"}.get(str(row.get("report_session") or ""), "歷史紀錄")
        generated_at = row.get("generated_at") or ""
        trades = "\n".join(
            f"- {trade.symbol} {trade.company_name} {self._action_label(trade.action)} {trade.shares} shares @ {trade.price or 'N/A'}: {trade.reason}"
            for trade in portfolio.trades
        ) or "- 尚無操作紀錄"
        ranking = "\n".join(
            f"- {index + 1}. {item.symbol} {item.company_name}: {item.score}/100, {self._action_label(item.action)}"
            for index, item in enumerate(analyses)
        ) or "- 尚無排行紀錄"
        return f"""# 潛力股模擬操作歷史紀錄
產生時間：{generated_at}

## {session_title}

此為已保存的每日紀錄；系統只重播既有交易決策，不改動原本的預估買賣資料。

## 潛力股排行
{ranking}

## 模擬操作
{trades}
"""
    def daily_status(self, limit: int = 10, case_id: str | None = None) -> dict[str, Any]:
        selected_case_id = case_id or self.active_case_id()
        rows = self.history(limit=500, case_id=selected_case_id)
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            trading_date = str(row.get("trading_date") or str(row.get("generated_at") or "")[:10])
            session = row.get("report_session")
            if trading_date not in grouped:
                grouped[trading_date] = {"date": trading_date, "pre_market": None, "market_hours": None, "post_market": None, "summary": ""}
            if session in {"pre_market", "market_hours", "post_market"}:
                grouped[trading_date][session] = row

        days = [self._summarize_day(day) for day in grouped.values()]
        days.sort(key=lambda item: item["date"], reverse=True)
        days = days[:limit]
        return {"active_case_id": selected_case_id, "days": days, "markdown": self._daily_status_markdown(days)}

    def performance(self, case_id: str | None = None) -> dict[str, Any]:
        selected_case_id = case_id or self.active_case_id()
        rows = self.history(limit=2000, case_id=selected_case_id)
        ledger_rows = self.ledger(limit=2000, case_id=selected_case_id)
        signals: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        candidate_signals: list[dict[str, Any]] = []
        candidate_pending: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            if row.get("report_session") == "market_hours":
                continue
            generated_at = str(row.get("generated_at") or "")
            analyses_by_symbol = {item.get("symbol"): item for item in row.get("analyses") or []}
            for analysis in row.get("analyses") or []:
                if analysis.get("action") != "BUY":
                    continue
                symbol = analysis.get("symbol")
                entry_price = self._float_or_none(analysis.get("latest_price"))
                if not symbol or not entry_price:
                    continue
                future = self._latest_future_price(rows[index + 1 :], symbol)
                base = {"symbol": symbol, "company_name": analysis.get("company_name") or self._company_name(symbol), "entry_at": generated_at, "entry_price": entry_price, "entry_score": analysis.get("score")}
                if future is None:
                    candidate_pending.append(base)
                else:
                    return_pct = (future["price"] - entry_price) / entry_price
                    candidate_signals.append({**base, "latest_at": future["generated_at"], "latest_price": future["price"], "return_pct": return_pct, "correct": return_pct > 0})
            for trade in (row.get("portfolio") or {}).get("trades") or []:
                if trade.get("action") != "BUY":
                    continue
                symbol = trade.get("symbol")
                analysis = analyses_by_symbol.get(symbol) or {}
                entry_price = self._float_or_none(trade.get("price") or analysis.get("latest_price"))
                if not symbol or not entry_price:
                    continue
                future = self._latest_future_price(rows[index + 1 :], symbol)
                base = {
                    "symbol": symbol,
                    "company_name": trade.get("company_name") or analysis.get("company_name") or self._company_name(symbol),
                    "entry_at": generated_at,
                    "entry_price": entry_price,
                    "entry_score": analysis.get("score"),
                    "entry_thesis": trade.get("reason") or analysis.get("thesis"),
                }
                if future is None:
                    pending.append(base)
                    continue
                return_pct = (future["price"] - entry_price) / entry_price
                signals.append({**base, "latest_at": future["generated_at"], "latest_price": future["price"], "return_pct": return_pct, "correct": return_pct > 0})

        returns = [item["return_pct"] for item in signals]
        wins = [item for item in signals if item["correct"]]
        summary = {
            "runs": len(rows),
            "signals": len(signals) + len(pending),
            "validated_signals": len(signals),
            "pending_signals": len(pending),
            "win_rate": len(wins) / len(signals) if signals else None,
            "average_return_pct": sum(returns) / len(returns) if returns else None,
            "best_signal": max(signals, key=lambda item: item["return_pct"], default=None),
            "worst_signal": min(signals, key=lambda item: item["return_pct"], default=None),
            "candidate_signals": len(candidate_signals) + len(candidate_pending),
            "validated_candidate_signals": len(candidate_signals),
            "candidate_hit_rate": len([item for item in candidate_signals if item["correct"]]) / len(candidate_signals) if candidate_signals else None,
            "candidate_average_return_pct": sum(item["return_pct"] for item in candidate_signals) / len(candidate_signals) if candidate_signals else None,
            "account_return_pct": self._account_return(ledger_rows),
            "benchmark_return_pct": self._ledger_benchmark_return(ledger_rows),
            "account_excess_return_pct": self._excess_return(self._account_return(ledger_rows), self._ledger_benchmark_return(ledger_rows)),
            "latest_account_value": ledger_rows[-1].get("total_value") if ledger_rows else None,
            "ledger_days": len({row.get("trading_date") for row in ledger_rows}),
        }
        return {"active_case_id": selected_case_id, "summary": summary, "signals": signals[-100:], "pending": pending[-100:], "candidate_signals": candidate_signals[-100:], "candidate_pending": candidate_pending[-100:], "ledger": ledger_rows[-100:], "markdown": self._performance_markdown(summary, signals, pending)}

    def branch_summary(self, case_id: str | None = None) -> dict[str, Any]:
        selected_case_id = case_id or self.active_case_id()
        rows = self.history(limit=2000, case_id=selected_case_id)
        ledger_rows = self.ledger(limit=2000, case_id=selected_case_id)
        performance = self.performance(case_id=selected_case_id)
        summary = performance["summary"]
        session_counts = {
            "pre_market": len([row for row in rows if row.get("report_session") == "pre_market"]),
            "market_hours": len([row for row in rows if row.get("report_session") == "market_hours"]),
            "post_market": len([row for row in rows if row.get("report_session") == "post_market"]),
        }
        trade_rows = [trade for row in ledger_rows for trade in row.get("trades") or []]
        buys = [trade for trade in trade_rows if trade.get("action") == "BUY"]
        sells = [trade for trade in trade_rows if trade.get("action") == "SELL"]
        holds = [row for row in ledger_rows[-1].get("holdings", [])] if ledger_rows else []
        latest = ledger_rows[-1] if ledger_rows else {}
        first_date = min((str(row.get("trading_date") or str(row.get("generated_at") or "")[:10]) for row in rows + ledger_rows if row.get("trading_date") or row.get("generated_at")), default="")
        last_date = max((str(row.get("trading_date") or str(row.get("generated_at") or "")[:10]) for row in rows + ledger_rows if row.get("trading_date") or row.get("generated_at")), default="")
        metrics = {
            "case_id": selected_case_id,
            "first_date": first_date,
            "last_date": last_date,
            "report_count": len(rows),
            "ledger_count": len(ledger_rows),
            "pre_market_count": session_counts["pre_market"],
            "market_hours_count": session_counts["market_hours"],
            "post_market_count": session_counts["post_market"],
            "buy_count": len(buys),
            "sell_count": len(sells),
            "holding_count": len(holds),
            "latest_account_value": latest.get("total_value"),
            "cash": latest.get("cash"),
            "invested_value": latest.get("invested_value"),
            "account_return_pct": summary.get("account_return_pct"),
            "benchmark_return_pct": summary.get("benchmark_return_pct"),
            "account_excess_return_pct": summary.get("account_excess_return_pct"),
            "candidate_hit_rate": summary.get("candidate_hit_rate"),
            "candidate_average_return_pct": summary.get("candidate_average_return_pct"),
            "trade_win_rate": summary.get("win_rate"),
            "validated_trades": summary.get("validated_signals"),
            "pending_trades": summary.get("pending_signals"),
            "ledger_days": summary.get("ledger_days"),
        }
        review = self._branch_strategy_review(metrics, performance, ledger_rows)
        tables = {
            "metrics": self._branch_metric_rows(metrics),
            "sessions": [
                {"name": "盤前計畫", "count": session_counts["pre_market"]},
                {"name": "盤中模擬交易", "count": session_counts["market_hours"]},
                {"name": "盤後結算", "count": session_counts["post_market"]},
            ],
            "trades": [
                {"name": "買進", "count": len(buys)},
                {"name": "賣出", "count": len(sells)},
                {"name": "目前持倉", "count": len(holds)},
            ],
        }
        markdown = self._branch_summary_markdown(selected_case_id, metrics, review, tables)
        return {"active_case_id": selected_case_id, "metrics": metrics, "review": review, "tables": tables, "performance": performance, "markdown": markdown}

    def ledger(self, limit: int = 100, case_id: str | None = None) -> list[dict[str, Any]]:
        selected_case_id = case_id or self.active_case_id()
        rows = [row for row in potential_stock_ledger_store.all() if self._record_case_id(row) == selected_case_id]
        rows.sort(key=lambda item: str(item.get("generated_at") or ""))
        return rows[-limit:]

    def _account_return(self, ledger_rows: list[dict[str, Any]]) -> float | None:
        if not ledger_rows:
            return None
        first = self._float_or_none(ledger_rows[0].get("total_value"))
        last = self._float_or_none(ledger_rows[-1].get("total_value"))
        if not first:
            return None
        return ((last or first) - first) / first

    def _ledger_benchmark_return(self, ledger_rows: list[dict[str, Any]]) -> float | None:
        prices = [self._float_or_none((row.get("benchmark") or {}).get("price")) for row in ledger_rows]
        prices = [price for price in prices if price]
        if len(prices) < 2 or not prices[0]:
            return None
        return (prices[-1] - prices[0]) / prices[0]

    def _excess_return(self, account_return: float | None, benchmark_return: float | None) -> float | None:
        if account_return is None or benchmark_return is None:
            return None
        return account_return - benchmark_return

    async def backtest(self, request: PotentialBacktestRequest) -> PotentialBacktestReport:
        price_history, benchmark_history = await self._backtest_price_history(request)
        limitations: list[str] = []
        price_history = {symbol: sorted(bars, key=lambda item: item.date) for symbol, bars in price_history.items() if bars}
        benchmark_history = sorted(benchmark_history, key=lambda item: item.date)
        if not price_history:
            limitations.append("Data Missing: no historical price data available for backtest.")
            return self._empty_backtest(request, limitations)

        dates = sorted({bar.date for bars in price_history.values() for bar in bars})
        cash = request.initial_capital
        holdings: dict[str, dict[str, Any]] = {}
        trade_log: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []
        total_costs = 0.0
        max_positions = max(1, min(30, int(request.max_positions or 5)))
        max_position_value = request.initial_capital * max(0.01, min(0.5, request.max_position_pct))
        slippage = max(0.0, request.slippage_bps) / 10000

        for date_index, current_date in enumerate(dates):
            if date_index == 0:
                continue
            signal_date = dates[date_index - 1]
            bars_by_symbol = {symbol: self._bar_on_or_before(bars, current_date) for symbol, bars in price_history.items()}
            bars_by_symbol = {symbol: bar for symbol, bar in bars_by_symbol.items() if bar is not None}
            if not bars_by_symbol:
                continue

            scores = [
                {
                    "symbol": symbol,
                    "company_name": self._company_name(symbol),
                    "score": self._historical_score(price_history[symbol], signal_date),
                    "price": bar.open,
                }
                for symbol, bar in bars_by_symbol.items()
            ]
            candidates = [item for item in scores if item["score"] >= request.buy_score]
            candidates.sort(key=lambda item: item["score"], reverse=True)
            target_symbols = {item["symbol"] for item in candidates[:max_positions]}

            for symbol in list(holdings):
                if symbol in target_symbols:
                    continue
                bar = bars_by_symbol.get(symbol)
                if not bar:
                    continue
                sell_price = bar.open * (1 - slippage)
                shares = holdings[symbol]["shares"]
                gross = shares * sell_price
                fee_tax = gross * (request.fee_rate + request.tax_rate)
                slip_cost = shares * bar.open * slippage
                cash += gross - fee_tax
                total_costs += fee_tax + slip_cost
                trade_log.append({"date": current_date.isoformat(), "signal_date": signal_date.isoformat(), "symbol": symbol, "company_name": self._company_name(symbol), "action": "SELL", "shares": shares, "price": sell_price, "amount": gross, "cost": fee_tax + slip_cost, "reason": "Backtest rebalance sell: symbol left target list."})
                del holdings[symbol]

            for item in candidates[:max_positions]:
                symbol = item["symbol"]
                if symbol in holdings:
                    continue
                if len(holdings) >= max_positions:
                    break
                buy_price = item["price"] * (1 + slippage)
                target_value = min(max_position_value, cash)
                lot_size = 1000 if symbol.endswith((".TW", ".TWO")) else 1
                shares = int(target_value // (buy_price * lot_size)) * lot_size
                if shares <= 0:
                    continue
                gross = shares * buy_price
                fee = gross * request.fee_rate
                slip_cost = shares * item["price"] * slippage
                if gross + fee > cash:
                    continue
                cash -= gross + fee
                total_costs += fee + slip_cost
                holdings[symbol] = {"symbol": symbol, "company_name": item["company_name"], "shares": shares, "entry_price": buy_price, "score": item["score"]}
                trade_log.append({"date": current_date.isoformat(), "signal_date": signal_date.isoformat(), "symbol": symbol, "company_name": item["company_name"], "action": "BUY", "shares": shares, "price": buy_price, "amount": gross, "cost": fee + slip_cost, "reason": f"Backtest buy: score {item['score']}/100 reached threshold."})

            market_value = 0.0
            latest_holdings: list[dict[str, Any]] = []
            for symbol, holding in holdings.items():
                bar = bars_by_symbol.get(symbol)
                if not bar:
                    continue
                value = holding["shares"] * bar.close
                market_value += value
                latest_holdings.append({**holding, "market_price": bar.close, "market_value": value, "unrealized_pl": value - holding["shares"] * holding["entry_price"]})
            total_value = cash + market_value
            equity_curve.append({"date": current_date.isoformat(), "cash": cash, "market_value": market_value, "total_value": total_value, "holdings": len(holdings)})

        if not equity_curve:
            limitations.append("Data Missing: no valid trading dates available for backtest equity curve.")
            return self._empty_backtest(request, limitations)

        final_value = equity_curve[-1]["total_value"]
        total_return = (final_value - request.initial_capital) / request.initial_capital
        max_drawdown = self._max_drawdown([item["total_value"] for item in equity_curve])
        benchmark = self._benchmark_result(request, dates, benchmark_history)
        benchmark_return = benchmark.get("return")
        excess_return = total_return - benchmark_return if benchmark_return is not None else None
        report = PotentialBacktestReport(
            initial_capital=request.initial_capital,
            final_value=final_value,
            total_return=total_return,
            benchmark_return=benchmark_return,
            excess_return=excess_return,
            max_drawdown=max_drawdown,
            trade_count=len(trade_log),
            fees_taxes_slippage=total_costs,
            latest_holdings=latest_holdings,
            equity_curve=equity_curve,
            trade_log=trade_log,
            benchmark=benchmark,
            data_limitations=limitations,
            markdown="",
        )
        report.markdown = self._backtest_markdown(report, request)
        return report

    async def _backtest_price_history(self, request: PotentialBacktestRequest) -> tuple[dict[str, list[PriceBar]], list[PriceBar]]:
        benchmark_symbol = self._normalize_symbols([request.benchmark_symbol])[0] if request.benchmark_symbol else ""
        if request.price_history:
            normalized = {self._normalize_symbols([symbol])[0]: bars for symbol, bars in request.price_history.items()}
            benchmark_history = normalized.pop(benchmark_symbol, []) if benchmark_symbol else []
            requested_symbols = self._normalize_symbols(request.symbols) if request.symbols else list(normalized)
            strategy_history = {symbol: normalized[symbol] for symbol in requested_symbols if symbol in normalized}
            return strategy_history, benchmark_history
        if not request.use_live_data:
            return {}, []
        symbols = self._normalize_symbols(request.symbols) if request.symbols else self._symbols_for_request(PotentialStockRequest(market_universe=request.market_universe))
        history: dict[str, list[PriceBar]] = {}
        benchmark_history: list[PriceBar] = []
        async with self.fetcher_client() as client:
            for symbol in symbols:
                history[symbol] = await self.fetcher.fetch_finmind_prices(client, self._finmind_symbol(symbol))
            if benchmark_symbol:
                benchmark_history = await self.fetcher.fetch_finmind_prices(client, self._finmind_symbol(benchmark_symbol))
        return history, benchmark_history

    def fetcher_client(self):
        import httpx

        return httpx.AsyncClient(timeout=self.fetcher.settings.request_timeout)

    def _bar_on_or_before(self, bars: list[PriceBar], current_date: Any) -> PriceBar | None:
        previous = None
        for bar in bars:
            if bar.date > current_date:
                break
            previous = bar
        return previous

    def _historical_score(self, bars: list[PriceBar], current_date: Any) -> int:
        window = [bar for bar in bars if bar.date <= current_date]
        if len(window) < 20:
            return 0
        latest = window[-1]
        closes = [bar.close for bar in window]
        volumes = [bar.volume for bar in window if bar.volume]
        ma20 = mean(closes[-20:])
        ma60 = mean(closes[-60:]) if len(closes) >= 60 else ma20
        momentum = (latest.close - closes[-20]) / closes[-20] if closes[-20] else 0
        volume_boost = mean(volumes[-5:]) / mean(volumes[-20:]) if len(volumes) >= 20 and mean(volumes[-20:]) else 1
        score = 45
        if latest.close > ma20:
            score += 15
        if ma20 > ma60:
            score += 15
        if momentum > 0.08:
            score += 15
        elif momentum > 0.02:
            score += 8
        if volume_boost > 1.25:
            score += 7
        if latest.close < ma20:
            score -= 12
        if momentum < -0.08:
            score -= 12
        return int(max(0, min(100, score)))

    def _benchmark_result(self, request: PotentialBacktestRequest, dates: list[Any], benchmark_history: list[PriceBar]) -> dict[str, Any]:
        if not request.benchmark_symbol:
            return {"symbol": request.benchmark_symbol, "return": None, "note": "Benchmark symbol is not configured."}
        symbol = self._normalize_symbols([request.benchmark_symbol])[0]
        bars = sorted(benchmark_history, key=lambda item: item.date)
        if not bars:
            return {"symbol": symbol, "return": None, "note": "Benchmark price data is missing."}
        start = self._bar_on_or_before(bars, dates[0])
        end = self._bar_on_or_before(bars, dates[-1])
        if not start or not end or start.close <= 0:
            return {"symbol": symbol, "return": None, "note": "Benchmark price range is incomplete."}
        return {"symbol": symbol, "start_price": start.close, "end_price": end.close, "return": (end.close - start.close) / start.close}

    def _max_drawdown(self, values: list[float]) -> float:
        if not values:
            return 0
        peak = values[0]
        max_dd = 0.0
        for value in values:
            peak = max(peak, value)
            if peak:
                max_dd = min(max_dd, (value - peak) / peak)
        return max_dd

    def _empty_backtest(self, request: PotentialBacktestRequest, limitations: list[str]) -> PotentialBacktestReport:
        report = PotentialBacktestReport(
            initial_capital=request.initial_capital,
            final_value=request.initial_capital,
            total_return=0,
            benchmark_return=None,
            excess_return=None,
            max_drawdown=0,
            trade_count=0,
            fees_taxes_slippage=0,
            data_limitations=limitations,
            markdown="",
        )
        report.markdown = self._backtest_markdown(report, request)
        return report

    def _backtest_markdown(self, report: PotentialBacktestReport, request: PotentialBacktestRequest) -> str:
        holdings = "\n".join(
            f"- {item['symbol']} {item.get('company_name', '')}: {item['shares']} shares, market value {item.get('market_value', 0):,.0f}"
            for item in report.latest_holdings
        ) or "- 尚無持倉"
        trades = "\n".join(
            f"- {item['date']} {item['symbol']} {item.get('company_name', '')} {self._action_label(item['action'])} {item['shares']} shares @ {item['price']:.2f}, cost {item['cost']:.0f}"
            for item in report.trade_log[-30:]
        ) or "- 尚無交易"
        limitations = "\n".join(f"- {item}" for item in report.data_limitations) or "- 尚無資料限制"
        return f"""# 潛力股歷史回放回測
## 回測設定

- 初始資金：{request.initial_capital:,.0f}
- 最多持股：{request.max_positions}
- 單股上限：{request.max_position_pct * 100:.1f}%
- 買進門檻：{request.buy_score}/100
- 手續費率：{request.fee_rate * 100:.4f}%
- 交易稅率：{request.tax_rate * 100:.4f}%
- 滑價：{request.slippage_bps:.1f} bps
- Benchmark：{request.benchmark_symbol}

## 回測結果

- 最終資產：{report.final_value:,.0f}
- 策略報酬：{self._pct(report.total_return)}
- Benchmark 報酬：{self._pct(report.benchmark_return)}
- 超額報酬：{self._pct(report.excess_return)}
- 最大回撤：{self._pct(report.max_drawdown)}
- 交易筆數：{report.trade_count}
- 費用/稅/滑價成本：{report.fees_taxes_slippage:,.0f}

## 最新持倉

{holdings}

## 最近交易
{trades}

## 資料限制

{limitations}
"""
    def _buy_analyses(self, row: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not row:
            return []
        planned = {
            trade.get("symbol")
            for trade in (row.get("portfolio") or {}).get("trades") or []
            if trade.get("action") in {"PLAN_BUY", "BUY"}
        }
        analyses = [item for item in row.get("analyses") or [] if item.get("action") == "BUY" or item.get("symbol") in planned]
        return analyses

    def _summarize_day(self, day: dict[str, Any]) -> dict[str, Any]:
        pre = day.get("pre_market")
        intraday = day.get("market_hours")
        post = day.get("post_market")
        portfolio_snapshot = (
            (post or {}).get("portfolio")
            or (intraday or {}).get("portfolio")
            or (pre or {}).get("portfolio")
            or {}
        )
        pre_buys = self._buy_analyses(pre)
        intraday_lookup = {item.get("symbol"): item for item in (intraday or {}).get("analyses", [])}
        post_lookup = {item.get("symbol"): item for item in (post or {}).get("analyses", [])}
        followups: list[dict[str, Any]] = []
        for item in pre_buys:
            symbol = item.get("symbol")
            intraday_item = intraday_lookup.get(symbol)
            post_item = post_lookup.get(symbol)
            entry_price = self._float_or_none(item.get("latest_price"))
            intraday_price = self._float_or_none((intraday_item or {}).get("latest_price"))
            post_price = self._float_or_none((post_item or {}).get("latest_price"))
            latest_price = post_price or intraday_price
            followup_return = (latest_price - entry_price) / entry_price if entry_price and latest_price else None
            followups.append(
                {
                    "symbol": symbol,
                    "company_name": item.get("company_name") or self._company_name(symbol),
                    "pre_action": self._action_label(item.get("action")),
                    "pre_score": item.get("score"),
                    "intraday_action": self._action_label((intraday_item or {}).get("action")) if intraday_item else "尚無盤中資料",
                    "intraday_score": (intraday_item or {}).get("score"),
                    "post_action": self._action_label((post_item or {}).get("action")) if post_item else "尚無盤後資料",
                    "post_score": (post_item or {}).get("score"),
                    "entry_price": entry_price,
                    "intraday_price": intraday_price,
                    "post_price": post_price,
                    "latest_price": latest_price,
                    "intraday_return": followup_return,
                    "status": self._followup_status(item, intraday_item, post_item, followup_return),
                }
            )
        return {
            "date": day["date"],
            "has_pre_market": pre is not None,
            "has_market_hours": intraday is not None,
            "has_post_market": post is not None,
            "pre_market": pre,
            "market_hours": intraday,
            "post_market": post,
            "portfolio_snapshot": portfolio_snapshot,
            "followups": followups,
            "summary": self._day_summary(pre, intraday, post, followups),
        }

    def _day_summary(self, pre: dict[str, Any] | None, intraday: dict[str, Any] | None, post: dict[str, Any] | None, followups: list[dict[str, Any]]) -> str:
        if not pre:
            return "尚未產生盤前計畫。"
        if not intraday:
            return f"已完成盤前計畫，待觀察候選 {len(followups)} 檔；尚未執行盤中模擬交易。"
        if not post:
            executed = len([trade for trade in (intraday.get("portfolio") or {}).get("trades") or [] if trade.get("action") in {"BUY", "SELL"}])
            return f"已完成盤中模擬，今日執行 {executed} 筆；尚未盤後結算。"
        positive = sum(1 for item in followups if (item.get("intraday_return") or 0) > 0)
        return f"已完成盤後結算；盤前候選 {len(followups)} 檔，其中 {positive} 檔盤中表現為正。"

    def _followup_status(self, pre_item: dict[str, Any], intraday_item: dict[str, Any] | None, post_item: dict[str, Any] | None, intraday_return: float | None) -> str:
        if intraday_item is None:
            return "尚未盤中觀察"
        if post_item is None:
            return "尚未盤後結算"
        if intraday_return is None:
            return "缺少盤中價格"
        if intraday_return > 0.02:
            return "盤中表現偏強"
        if intraday_return < -0.02:
            return "盤中表現偏弱"
        return "盤中表現持平"
    def _daily_status_markdown(self, days: list[dict[str, Any]]) -> str:
        if not days:
            return "# 每日盤前盤中盤後追蹤\n\n尚未有盤前、盤中或盤後紀錄。"
        blocks = ["# 每日盤前盤中盤後追蹤", ""]
        for day in days:
            blocks.extend([f"## {day['date']}", "", f"- 狀態：{day['summary']}"])
            if day["followups"]:
                blocks.append("- 盤前候選追蹤：")
                for item in day["followups"]:
                    blocks.append(
                        f"  - {item['symbol']} {item['company_name']}：盤前 {item['pre_score']} 分，盤中 {item.get('intraday_score') or '--'} 分，盤後 {item.get('post_score') or '--'} 分，狀態 {item['status']}，盤中報酬 {self._pct(item.get('intraday_return'))}"
                    )
            blocks.append("")
        return "\n".join(blocks)

    def _latest_future_price(self, rows: list[dict[str, Any]], symbol: str) -> dict[str, Any] | None:
        latest = None
        for row in rows:
            for analysis in row.get("analyses") or []:
                if analysis.get("symbol") != symbol:
                    continue
                price = self._float_or_none(analysis.get("latest_price"))
                if price is not None:
                    latest = {"generated_at": row.get("generated_at"), "price": price}
        return latest

    def _performance_markdown(self, summary: dict[str, Any], signals: list[dict[str, Any]], pending: list[dict[str, Any]]) -> str:
        best = summary.get("best_signal") or {}
        worst = summary.get("worst_signal") or {}
        recent = "\n".join(
            f"- {item['symbol']} {item['company_name']}：進場 {item['entry_price']:.2f}，最新 {item['latest_price']:.2f}，報酬 {self._pct(item['return_pct'])}"
            for item in signals[-20:]
        ) or "- 尚無已驗證候選"
        pending_lines = "\n".join(
            f"- {item['symbol']} {item['company_name']}：進場 {item['entry_price']:.2f}，尚未取得後續價格"
            for item in pending[-20:]
        ) or "- 尚無等待驗證候選"
        return f"""# 潛力股工具績效回朔

- 候選股數：{summary.get('signals', 0)}
- 已驗證候選：{summary.get('validated_signals', 0)}
- 候選命中率：{self._pct(summary.get('candidate_hit_rate'))}
- 模擬帳戶報酬：{self._pct(summary.get('account_return_pct'))}
- Benchmark 報酬：{self._pct(summary.get('benchmark_return_pct'))}
- 相對 Benchmark：{self._pct(summary.get('excess_return_pct'))}
- 最佳候選：{best.get('symbol', '--')} {self._pct(best.get('return_pct'))}
- 最弱候選：{worst.get('symbol', '--')} {self._pct(worst.get('return_pct'))}

## 最近已驗證候選
{recent}

## 等待驗證候選
{pending_lines}
"""

    def _branch_strategy_review(self, metrics: dict[str, Any], performance: dict[str, Any], ledger_rows: list[dict[str, Any]]) -> dict[str, Any]:
        account_return = metrics.get("account_return_pct")
        excess = metrics.get("account_excess_return_pct")
        hit_rate = metrics.get("candidate_hit_rate")
        buy_count = int(metrics.get("buy_count") or 0)
        ledger_days = int(metrics.get("ledger_days") or 0)
        issues: list[str] = []
        fixes: list[str] = []
        strengths: list[str] = []
        if ledger_days < 5:
            issues.append("樣本天數偏少，支線可能只做到一半，結論只能視為初步觀察。")
            fixes.append("至少累積 10 個交易日或 5 筆以上實際買進後，再調整策略參數。")
        if buy_count == 0:
            issues.append("尚無實際買進，無法評估交易績效，只能評估候選股品質。")
            fixes.append("先確認盤前計畫與盤中執行是否都有按流程產生，避免只有分析沒有交易。")
        if account_return is not None and account_return > 0:
            strengths.append("模擬帳戶目前為正報酬。")
        if excess is not None and excess > 0:
            strengths.append("目前跑贏 benchmark，代表支線有初步相對優勢。")
        elif excess is not None and excess < 0:
            issues.append("目前落後 benchmark，選股或持倉效率需要檢討。")
            fixes.append("降低低分持倉續抱時間，並提高買進門檻或籌碼品質門檻。")
        if hit_rate is not None and hit_rate < 0.45:
            issues.append("候選股命中率偏低，盤前篩選可能過度寬鬆。")
            fixes.append("提高買進門檻 3-5 分，或要求籌碼品質與基本面至少一項達 60 分以上。")
        elif hit_rate is not None and hit_rate >= 0.55:
            strengths.append("候選股命中率尚可，盤前篩選有保留價值。")
        if metrics.get("pending_trades", 0):
            issues.append("仍有未驗證交易，短期結論可能受後續價格影響。")
        if not issues:
            issues.append("目前沒有明顯重大缺陷，但仍需持續累積樣本避免過早最佳化。")
        if not fixes:
            fixes.append("維持目前規則，優先觀察更多交易日；暫不大幅改參數。")
        conclusion = "可繼續觀察" if (excess is None or excess >= 0) and buy_count > 0 else "需要保守調整"
        return {"conclusion": conclusion, "strengths": strengths or ["尚未形成明確優勢。"], "issues": issues, "fixes": fixes}

    def _branch_metric_rows(self, metrics: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"name": "追蹤期間", "value": f"{metrics.get('first_date') or '--'} ~ {metrics.get('last_date') or '--'}"},
            {"name": "報告數", "value": metrics.get("report_count", 0)},
            {"name": "帳本數", "value": metrics.get("ledger_count", 0)},
            {"name": "買進次數", "value": metrics.get("buy_count", 0)},
            {"name": "賣出次數", "value": metrics.get("sell_count", 0)},
            {"name": "目前持倉", "value": metrics.get("holding_count", 0)},
            {"name": "帳戶報酬", "value": self._pct(metrics.get("account_return_pct"))},
            {"name": "Benchmark 報酬", "value": self._pct(metrics.get("benchmark_return_pct"))},
            {"name": "相對 Benchmark", "value": self._pct(metrics.get("account_excess_return_pct"))},
            {"name": "候選命中率", "value": self._pct(metrics.get("candidate_hit_rate"))},
            {"name": "候選平均報酬", "value": self._pct(metrics.get("candidate_average_return_pct"))},
            {"name": "實際交易勝率", "value": self._pct(metrics.get("trade_win_rate"))},
        ]

    def _branch_summary_markdown(self, case_id: str, metrics: dict[str, Any], review: dict[str, Any], tables: dict[str, Any]) -> str:
        metric_lines = "\n".join(f"| {row['name']} | {row['value']} |" for row in tables["metrics"])
        strengths = "\n".join(f"- {item}" for item in review["strengths"])
        issues = "\n".join(f"- {item}" for item in review["issues"])
        fixes = "\n".join(f"- {item}" for item in review["fixes"])
        return f"""# 支線總結與策略檢討

- 支線：{case_id}
- 結論：{review['conclusion']}

## 量化統計

| 指標 | 數值 |
|---|---:|
{metric_lines}

## 目前看到的優勢
{strengths}

## 策略問題
{issues}

## 修正建議
{fixes}
"""
    def _symbols_for_request(self, request: PotentialStockRequest) -> list[str]:
        if request.symbols:
            symbols = request.symbols
        else:
            universes = request.market_universes or [request.market_universe]
            symbols = []
            for universe in universes:
                if universe == "custom":
                    continue
                symbols.extend(self.UNIVERSES.get(universe, []))
            if not symbols:
                symbols = self.UNIVERSES["semiconductor"]
        return self._normalize_symbols(symbols)

    def _record_case_id(self, row: dict[str, Any]) -> str:
        return str(row.get("case_id") or "default")

    def _case_name(self, case_id: str) -> str:
        if case_id == "default":
            return "?身獢辣"
        return f"模擬案件 {case_id.replace('case-', '')}"

    def _resolve_report_session(self, report_session: str, now: datetime | None = None) -> str:
        if report_session in {"pre_market", "market_hours", "post_market"}:
            return report_session
        current = now or datetime.now(TW_TZ)
        if current.weekday() >= 5:
            return "post_market"
        minutes = current.hour * 60 + current.minute
        if minutes < 9 * 60:
            return "pre_market"
        if minutes <= 13 * 60 + 30:
            return "market_hours"
        return "post_market"

    async def _ai_research_summary(
        self,
        request: PotentialStockRequest,
        market_stance: str,
        analyses: list[PotentialStockAnalysis],
        portfolio: PaperPortfolio,
        limitations: list[str],
    ) -> dict[str, Any]:
        compact_analyses = [
            {
                "symbol": item.symbol,
                "company_name": item.company_name,
                "score": item.score,
                "action": item.action,
                "risk_level": item.risk_level,
                "component_scores": item.component_scores,
                "latest_price": item.latest_price,
                "advantages": item.advantages[:4],
                "risks": item.risks[:4],
                "related_news": item.related_news[:4],
                "evidence_links": item.evidence_links[:5],
                "score_explanation": item.score_explanation[:6],
                "news_impact_summary": item.news_impact_summary[:5],
                "thesis": item.thesis,
            }
            for item in analyses[:10]
        ]
        payload = {
            "language": "zh-Hant",
            "report_session": request.report_session,
            "market_universe": request.market_universe,
            "market_stance": market_stance,
            "settings": {
                "initial_capital": request.initial_capital,
                "max_positions": request.max_positions,
                "max_position_pct": request.max_position_pct,
                "buy_score": request.buy_score,
                "watch_score": request.watch_score,
                "risk_reward_profile": request.risk_reward_profile,
                "investment_horizon": request.investment_horizon,
            },
            "analyses": compact_analyses,
            "portfolio": portfolio.model_dump(mode="json"),
            "data_limitations": limitations,
        }
        return await self.ai.analyze_potential_stocks(payload)

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        cleaned: list[str] = []
        for symbol in symbols:
            value = str(symbol).strip().upper()
            if not value:
                continue
            if value.isdigit():
                value = f"{value}.TW"
            if value not in cleaned:
                cleaned.append(value)
        return cleaned[:30] or self.UNIVERSES["semiconductor"]

    def _finmind_symbol(self, symbol: str) -> str:
        return symbol.split(".")[0] if symbol.endswith((".TW", ".TWO")) else symbol

    async def _build_us_tech_context(self, request: PotentialStockRequest) -> dict[str, Any]:
        if not request.use_us_tech_leading:
            return {"available": False, "rows": [], "limitation": ""}
        if not request.use_live_data:
            return {
                "available": False,
                "rows": [],
                "limitation": "US Leading Data Missing: live data disabled; using exposure-based fallback score.",
            }
        rows = await self.fetcher.fetch_us_daily_returns(self.US_TECH_LEADERS)
        if not rows:
            return {
                "available": False,
                "rows": [],
                "limitation": "US Leading Data Missing: US market leader prices unavailable; using exposure-based fallback score.",
            }
        returns = [float(row["return_pct"]) for row in rows if self._float_or_none(row.get("return_pct")) is not None]
        if not returns:
            return {
                "available": False,
                "rows": rows,
                "limitation": "US Leading Data Missing: US market leader returns unavailable; using exposure-based fallback score.",
            }
        semi_symbols = {"NVDA", "AMD", "AVGO", "TSM", "ASML", "AMAT", "LRCX", "KLAC", "MU", "SMH", "SOXX"}
        semi_returns = [float(row["return_pct"]) for row in rows if row.get("symbol") in semi_symbols and self._float_or_none(row.get("return_pct")) is not None]
        return {
            "available": True,
            "rows": rows,
            "average_return_pct": mean(returns),
            "positive_ratio": sum(1 for item in returns if item > 0) / len(returns),
            "semiconductor_return_pct": mean(semi_returns) if semi_returns else mean(returns),
            "leader_count": len(returns),
            "source": "Yahoo Finance chart",
        }

    def _analyze_dataset(self, dataset: MarketDataset, request: PotentialStockRequest, us_tech_context: dict[str, Any] | None = None) -> PotentialStockAnalysis:
        symbol = dataset.ticker if "." in dataset.ticker else f"{dataset.ticker}.TW"
        company_name = self._company_name(symbol)
        technical_score, technical_summary, latest_price, latest_open = self._technical(dataset)
        fundamental_score, fundamental_summary, operating_summary = self._fundamentals(dataset)
        institutional_score, institutional_summary = self._institutional(dataset)
        news_score, related_news, news_risks = self._news(dataset)
        event_score, event_summary, event_risks, evidence_links = self._event_intelligence(dataset)
        data_score = self._data_score(dataset)
        data_quality_summary = self._data_quality_summary(dataset, data_score)
        component_scores = {
            "technical": technical_score,
            "fundamental": fundamental_score,
            "institutional": institutional_score,
            "news": news_score,
            "event_intel": event_score,
            "data_quality": data_score,
        }
        smart_money_score, smart_money_summary = self._smart_money_quality_signal(component_scores)
        component_scores["smart_money_quality"] = smart_money_score
        us_score, us_summary, us_limitations = self._us_tech_leading_signal(symbol, request, us_tech_context)
        if request.use_us_tech_leading:
            component_scores["us_tech_leading"] = us_score
            dataset.limitations = list(dict.fromkeys([*dataset.limitations, *us_limitations]))
        score = self._weighted_score(component_scores, request)
        action = "BUY" if score >= request.buy_score else "WATCH" if score >= request.watch_score else "AVOID"
        risk_level = "High" if data_score < 45 or score < 50 else "Medium" if score < 75 else "Low"
        advantages = self._advantages(component_scores)
        risks = self._friendly_data_messages(news_risks + event_risks + self._risks(component_scores, dataset))
        related_news = self._friendly_data_messages([*event_summary, *related_news])[:5]
        news_impact_summary = self._news_impact_summary(dataset, related_news, news_risks, event_risks)
        technical_summary = self._friendly_data_messages(technical_summary)
        fundamental_summary = self._friendly_data_messages(fundamental_summary)
        institutional_summary = self._friendly_data_messages(institutional_summary)
        operating_summary = self._friendly_data_messages(operating_summary)
        data_limitations = self._friendly_data_messages(dataset.limitations)
        score_explanation = self._score_explanation(
            component_scores,
            request,
            technical_summary,
            fundamental_summary,
            institutional_summary,
            [*related_news, *news_impact_summary],
            us_summary if request.use_us_tech_leading else [],
            risks,
        )
        thesis = self._thesis(symbol, company_name, score, action, advantages, risks, score_explanation)
        return PotentialStockAnalysis(
            symbol=symbol,
            company_name=company_name,
            score=score,
            action=action,
            risk_level=risk_level,
            component_scores=component_scores,
            fundamental_summary=fundamental_summary,
            institutional_summary=institutional_summary,
            technical_summary=technical_summary,
            operating_summary=[*operating_summary, *smart_money_summary, *data_quality_summary],
            us_market_summary=us_summary if request.use_us_tech_leading else [],
            score_explanation=score_explanation,
            news_impact_summary=news_impact_summary,
            advantages=advantages,
            risks=risks,
            related_news=related_news,
            evidence_links=evidence_links[:5],
            data_limitations=data_limitations,
            latest_price=latest_price,
            latest_open=latest_open,
            thesis=thesis,
        )

    def _weighted_score(self, scores: dict[str, int], request: PotentialStockRequest) -> int:
        weights_by_horizon = {
            "short_weeks": {"technical": 0.28, "fundamental": 0.12, "institutional": 0.13, "smart_money_quality": 0.10, "news": 0.10, "event_intel": 0.09, "us_tech_leading": 0.10, "data_quality": 0.08},
            "mid_term_3m": {"technical": 0.21, "fundamental": 0.20, "institutional": 0.14, "smart_money_quality": 0.12, "news": 0.09, "event_intel": 0.08, "us_tech_leading": 0.07, "data_quality": 0.09},
            "long_6m": {"technical": 0.17, "fundamental": 0.28, "institutional": 0.13, "smart_money_quality": 0.11, "news": 0.06, "event_intel": 0.08, "us_tech_leading": 0.04, "data_quality": 0.13},
            "multi_year": {"technical": 0.12, "fundamental": 0.36, "institutional": 0.09, "smart_money_quality": 0.10, "news": 0.05, "event_intel": 0.08, "us_tech_leading": 0.02, "data_quality": 0.18},
        }
        weights = weights_by_horizon.get(request.investment_horizon, weights_by_horizon["mid_term_3m"])
        score = sum(scores.get(key, 50) * weight for key, weight in weights.items())
        if request.risk_reward_profile == "aggressive":
            score += max(0, scores.get("technical", 50) - 65) * 0.08 + max(0, scores.get("news", 50) - 60) * 0.05
            score += max(0, scores.get("us_tech_leading", 50) - 60) * 0.04
            score += max(0, scores.get("event_intel", 50) - 65) * 0.05
            score -= max(0, 55 - scores.get("data_quality", 50)) * 0.08
        elif request.risk_reward_profile == "conservative":
            score += max(0, scores.get("data_quality", 50) - 70) * 0.05
            score -= max(0, 60 - scores.get("data_quality", 50)) * 0.25
            score -= max(0, 55 - scores.get("fundamental", 50)) * 0.12
            score += max(0, scores.get("event_intel", 50) - 70) * 0.03
        return int(max(0, min(100, round(score))))

    def _smart_money_quality_signal(self, scores: dict[str, int]) -> tuple[int, list[str]]:
        technical = scores.get("technical", 50)
        fundamental = scores.get("fundamental", 50)
        institutional = scores.get("institutional", 50)
        news = scores.get("news", 50)
        aligned_count = sum(1 for value in (technical, fundamental, institutional) if value >= 60)
        weak_count = sum(1 for value in (technical, fundamental, institutional) if value < 50)
        score = 50
        score += aligned_count * 10
        score -= weak_count * 9
        if institutional >= 65 and fundamental < 55:
            score -= 12
        if institutional >= 65 and technical >= 70 and fundamental >= 60:
            score += 8
        if technical >= 78 and fundamental < 55:
            score -= 10
        if news >= 65 and fundamental >= 60:
            score += 4
        score = int(max(0, min(100, score)))
        if score >= 70:
            summary = "籌碼、基本面與價格位置同向，較接近大資金布局而非單純追價。"
        elif institutional >= 65 and fundamental < 55:
            summary = "籌碼偏多但基本面尚未跟上，先視為資金腳印，不直接當買進理由。"
        elif technical >= 78 and fundamental < 55:
            summary = "價格已轉強但基本面支撐不足，追高的風險報酬需要打折。"
        else:
            summary = "籌碼、基本面與價格位置尚未完全同向，需等待更多確認。"
        return score, [
            "策略原則：籌碼是腳印，基本面是原因，價格位置決定風險報酬。",
            summary,
        ]

    def _us_tech_leading_signal(self, symbol: str, request: PotentialStockRequest, context: dict[str, Any] | None = None) -> tuple[int, list[str], list[str]]:
        if not request.use_us_tech_leading:
            return 50, [], []
        leaders = ", ".join(self.US_TECH_LEADERS)
        context = context or {}
        if symbol in self.HIGH_US_TECH_EXPOSURE:
            fallback_score = 58
            exposure = "高"
            exposure_factor = 1.0
            summary = "此股屬半導體供應鏈，盤前優先參考前一晚美股半導體與 AI 指標。"
        elif symbol in self.MEDIUM_US_TECH_EXPOSURE:
            fallback_score = 55
            exposure = "中"
            exposure_factor = 0.7
            summary = "此股屬 AI/電子供應鏈，盤前參考 Nasdaq、QQQ 與大型科技股風險偏好。"
        else:
            fallback_score = 50
            exposure = "低"
            exposure_factor = 0.35
            summary = "此股受美股科技影響較間接，美股僅作為整體風險偏好參考。"
        if context.get("available"):
            avg_return = float(context.get("average_return_pct") or 0)
            semi_return = float(context.get("semiconductor_return_pct") or 0)
            positive_ratio = float(context.get("positive_ratio") or 0)
            raw_score = 50 + avg_return * 260 + semi_return * 190 + (positive_ratio - 0.5) * 22
            score = int(max(15, min(90, round(50 + (raw_score - 50) * exposure_factor))))
            leader_count = int(context.get("leader_count") or 0)
            top_rows = sorted(context.get("rows") or [], key=lambda row: abs(float(row.get("return_pct") or 0)), reverse=True)[:4]
            top_summary = ", ".join(f"{row.get('symbol')} {float(row.get('return_pct') or 0) * 100:+.2f}%" for row in top_rows)
            return score, [
                summary,
                f"美股科技曝險：{exposure}；已納入前一晚 {leader_count} 個美股/ETF 指標，平均漲跌 {avg_return * 100:+.2f}%、半導體鏈 {semi_return * 100:+.2f}%、上漲比例 {positive_ratio * 100:.0f}%。",
                f"主要領先指標：{top_summary or leaders}；資料源：{context.get('source') or 'US market data'}。",
            ], []
        limitation = str(context.get("limitation") or "US Leading Data Missing: no US market data source is connected; using exposure-based fallback score.")
        return fallback_score, [
            summary,
            f"美股科技曝險：{exposure}；追蹤指標：{leaders}。",
            "尚未取得美股領先資料，本次先以曝險等級的保守 fallback 分數納入；取得資料後會改用前一晚實際漲跌。",
        ], [limitation]
    def _technical(self, dataset: MarketDataset) -> tuple[int, list[str], float | None, float | None]:
        bars = sorted(dataset.price, key=lambda item: item.date)
        if len(bars) < 20:
            latest = bars[-1] if bars else None
            return 40, ["Data Missing: price history is shorter than 20 bars."], latest.close if latest else None, latest.open if latest else None
        latest = bars[-1]
        closes = [bar.close for bar in bars]
        volumes = [bar.volume for bar in bars if bar.volume]
        ma20 = mean(closes[-20:])
        ma60 = mean(closes[-60:]) if len(closes) >= 60 else ma20
        return_20 = (latest.close - closes[-20]) / closes[-20] if closes[-20] else 0
        volume_boost = mean(volumes[-5:]) / mean(volumes[-20:]) if len(volumes) >= 20 and mean(volumes[-20:]) else 1
        score = 50
        if latest.close > ma20:
            score += 12
        if ma20 > ma60:
            score += 12
        if return_20 > 0.08:
            score += 14
        elif return_20 > 0.02:
            score += 7
        if volume_boost > 1.25:
            score += 8
        if latest.close < ma20:
            score -= 12
        if return_20 < -0.08:
            score -= 12
        return int(max(0, min(100, score))), [
            f"最新收盤 {latest.close:.2f}，20 日報酬 {return_20 * 100:.2f}%",
            f"20 日均線 {ma20:.2f}，60 日均線 {ma60:.2f}",
            f"近 5 日均量 / 20 日均量：{volume_boost:.2f} 倍",
        ], latest.close, latest.open

    def _fundamentals(self, dataset: MarketDataset) -> tuple[int, list[str], list[str]]:
        rows = [point for point in dataset.fundamentals if not point.missing]
        if not rows:
            return 40, ["Data Missing: no fundamental data available."], ["營運資料不足，暫以保守分數處理。"]
        latest = rows[-1]
        revenue_growth = self._latest_revenue_growth(rows)
        score = 55
        if revenue_growth is not None:
            if revenue_growth > 20:
                score += 20
            elif revenue_growth > 5:
                score += 10
            elif revenue_growth < -10:
                score -= 15
        summary = [self._format_datapoint(latest)]
        summary.append(f"最近營收年增率：{revenue_growth:.2f}%" if revenue_growth is not None else "Data Missing: revenue growth is unavailable.")
        return int(max(0, min(100, score))), summary, [
            "營運面以營收成長與最新基本面資料評估。",
            "若缺少 EPS、毛利率或法說資料，需搭配新聞與籌碼面確認。",
        ]

    def _latest_revenue_growth(self, points: list[DataPoint]) -> float | None:
        for point in reversed(points):
            if isinstance(point.value, dict):
                for key in ("revenue_year_growth", "YoY", "yoy", "growth_rate"):
                    if key in point.value:
                        return self._float_or_none(point.value[key])
        return None

    def _institutional(self, dataset: MarketDataset) -> tuple[int, list[str]]:
        points = [point for point in dataset.institutional if not point.missing]
        if not points:
            return 40, ["Data Missing: no institutional trading data available."]
        recent = points[-10:]
        positive = 0
        negative = 0
        for point in recent:
            value = self._numeric_value(point.value)
            if value is None:
                continue
            if value > 0:
                positive += 1
            elif value < 0:
                negative += 1
        return int(max(0, min(100, 50 + positive * 5 - negative * 4))), [
            f"最近 {len(recent)} 筆法人資料中，買超天數 {positive}，賣超天數 {negative}。",
            "籌碼分數用近期法人買賣超方向估算。",
        ]

    def _news(self, dataset: MarketDataset) -> tuple[int, list[str], list[str]]:
        rows = [point for point in dataset.news if not point.missing]
        if not rows:
            return 45, ["Data Missing: no recent news available."], ["新聞資料不足，事件風險覆蓋不完整。"]
        titles = [str(point.name) for point in rows[:5]]
        text = " ".join(titles + [str(point.value or "") for point in rows[:5]]).lower()
        positive_words = ("growth", "beat", "record", "ai", "order", "benefit", "upgrade", "outperform", "訂單", "產能", "擴產", "受惠", "創高", "法說", "調高")
        negative_words = ("loss", "cut", "weak", "risk", "lawsuit", "decline", "downgrade", "miss", "大跌", "崩", "血洗", "恐慌", "下跌", "摜壓", "倒地", "缺口", "砍單", "下修", "賣壓")
        risks = [f"新聞出現負面關鍵字：{word}" for word in negative_words if word in text]
        score = 55 + sum(6 for word in positive_words if word in text) - sum(8 for word in negative_words if word in text)
        return int(max(0, min(100, score))), titles, risks

    def _event_intelligence(self, dataset: MarketDataset) -> tuple[int, list[str], list[str], list[dict[str, Any]]]:
        rows = [point for point in dataset.events if not point.missing]
        if not rows:
            return 45, ["官方公告、公司 IR 與供應鏈情報尚未取得。"], ["缺少官方/IR/供應鏈情報，事件面信心需下修。"], []
        tier_weight = {
            "official_mops": 6,
            "exchange_alert": 4,
            "company_ir": 3,
            "conference_material": 3,
            "supply_chain_search": 2,
        }
        positive_keywords = ("AI", "CoWoS", "HBM", "ASIC", "訂單", "產能", "擴產", "NVIDIA", "輝達", "先進封裝", "GB200", "GB300", "CPO", "液冷", "運價", "SCFI", "市占", "法說", "upgrade", "guidance")
        negative_keywords = ("處置", "注意", "裁罰", "訴訟", "下修", "減產", "缺料", "風險", "downgrade", "weak", "miss")
        score = 50
        summary: list[str] = []
        risks: list[str] = []
        evidence = self._evidence_links(dataset)
        for point in rows[:12]:
            value = point.value if isinstance(point.value, dict) else {}
            tier = str(value.get("tier") or "news")
            credibility = self._float_or_none(value.get("credibility")) or 55
            relevance = self._float_or_none(value.get("relevance_score")) or 0
            text = " ".join([str(point.name or ""), str(value.get("summary") or point.value or "")])
            score += tier_weight.get(tier, 1) * max(0.6, credibility / 100)
            score += min(8, relevance / 12)
            score += sum(2 for keyword in positive_keywords if keyword.lower() in text.lower())
            if any(keyword.lower() in text.lower() for keyword in negative_keywords):
                score -= 4
                risks.append(f"{point.source} 出現需留意事件：{point.name}")
        for point in rows[:5]:
            value = point.value if isinstance(point.value, dict) else {}
            tier = str(value.get("tier") or "news")
            tier_label = self._tier_label(tier)
            summary_text = str(value.get("summary") or point.name or "")
            drivers = value.get("drivers_hit") if isinstance(value.get("drivers_hit"), list) else []
            risks_hit = value.get("risk_terms_hit") if isinstance(value.get("risk_terms_hit"), list) else []
            leaders = value.get("us_leaders_hit") if isinstance(value.get("us_leaders_hit"), list) else []
            hits = [*drivers[:4], *leaders[:2], *risks_hit[:2]]
            keyword_text = f"；股性命中：{', '.join(str(item) for item in hits[:5])}" if hits else ""
            summary.append(f"{tier_label}｜{point.source}：{point.name}。{summary_text[:120]}{keyword_text}")
        return int(max(0, min(100, round(score)))), summary, risks[:4], evidence[:5]

    def _evidence_links(self, dataset: MarketDataset) -> list[dict[str, Any]]:
        tier_rank = {
            "official_mops": 0,
            "exchange_alert": 1,
            "supply_chain_search": 2,
            "news": 3,
            "company_ir": 4,
            "conference_material": 5,
        }
        candidates: list[DataPoint] = [point for point in [*dataset.events, *dataset.news] if not point.missing and point.url]
        def rank(point: DataPoint) -> tuple[int, int, int]:
            value = point.value if isinstance(point.value, dict) else {}
            tier = str(value.get("tier") or ("news" if point in dataset.news else "supply_chain_search"))
            credibility = int(self._float_or_none(value.get("credibility")) or 50)
            relevance = int(self._float_or_none(value.get("relevance_score")) or 0)
            text = f"{point.name} {value.get('summary') if isinstance(value, dict) else point.value}"
            has_market_shock = any(word in str(text) for word in ("大跌", "崩", "血洗", "恐慌", "下跌", "砍單", "下修", "賣壓"))
            shock_priority = 0 if has_market_shock else 1
            tier_priority = 0 if has_market_shock else tier_rank.get(tier, 9)
            return tier_priority, shock_priority, -(credibility + relevance)
        candidates.sort(key=rank)
        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        for point in candidates:
            url = str(point.url or "")
            if not url or url in seen:
                continue
            seen.add(url)
            value = point.value if isinstance(point.value, dict) else {}
            tier = str(value.get("tier") or ("news" if point in dataset.news else "supply_chain_search"))
            links.append(
                {
                    "title": point.name,
                    "source": point.source,
                    "url": url,
                    "tier": tier,
                    "tier_label": self._tier_label(tier),
                    "credibility": int(self._float_or_none(value.get("credibility")) or (60 if tier == "news" else 70)),
                    "relevance": int(self._float_or_none(value.get("relevance_score")) or 0),
                }
            )
            if len(links) >= 5:
                break
        return links

    def _tier_label(self, tier: str) -> str:
        labels = {
            "official_mops": "官方重大訊息",
            "exchange_alert": "交易所公告",
            "company_ir": "公司 IR",
            "conference_material": "法說/簡報",
            "supply_chain_search": "供應鏈搜尋",
            "news": "新聞",
        }
        return labels.get(tier, tier or "資料來源")

    def _score_explanation(
        self,
        scores: dict[str, int],
        request: PotentialStockRequest,
        technical_summary: list[str],
        fundamental_summary: list[str],
        institutional_summary: list[str],
        news_summary: list[str],
        us_summary: list[str],
        risks: list[str],
    ) -> list[str]:
        weights = self._score_weights(request)
        rows = [
            ("technical", "技術面", technical_summary),
            ("fundamental", "基本面", fundamental_summary),
            ("institutional", "籌碼面", institutional_summary),
            ("smart_money_quality", "籌碼品質", []),
            ("news", "新聞面", news_summary),
            ("event_intel", "事件/股性情報", news_summary),
            ("us_tech_leading", "美股科技領先", us_summary),
            ("data_quality", "資料品質", []),
        ]
        explanations: list[str] = []
        for key, label, evidence in rows:
            if key not in scores:
                continue
            score = int(scores.get(key) or 0)
            weight = weights.get(key, 0)
            contribution = score * weight
            tone = "加分" if score >= 65 else "中性" if score >= 50 else "扣分"
            evidence_text = "；".join(str(item) for item in evidence[:2] if item) or self._score_default_reason(key, score)
            explanations.append(f"{label} {score}/100，權重 {weight:.0%}，約貢獻 {contribution:.1f} 分，屬於{tone}因子。依據：{evidence_text}")
        if risks:
            explanations.append(f"風險折抵：{risks[0]}")
        return explanations[:8]

    def _score_default_reason(self, key: str, score: int) -> str:
        if key == "smart_money_quality":
            return "用技術、基本面與籌碼是否同向判斷是否只是短線資金腳印。"
        if key == "data_quality":
            return "用股價、法人、基本面、新聞與官方/供應鏈事件的覆蓋度判斷信心。"
        if score >= 65:
            return "該構面目前偏正向。"
        if score < 50:
            return "該構面目前資料不足或偏弱。"
        return "該構面目前中性，尚需更多確認。"

    def _score_weights(self, request: PotentialStockRequest) -> dict[str, float]:
        weights_by_horizon = {
            "short_weeks": {"technical": 0.28, "fundamental": 0.12, "institutional": 0.13, "smart_money_quality": 0.10, "news": 0.10, "event_intel": 0.09, "us_tech_leading": 0.10, "data_quality": 0.08},
            "mid_term_3m": {"technical": 0.21, "fundamental": 0.20, "institutional": 0.14, "smart_money_quality": 0.12, "news": 0.09, "event_intel": 0.08, "us_tech_leading": 0.07, "data_quality": 0.09},
            "long_6m": {"technical": 0.17, "fundamental": 0.28, "institutional": 0.13, "smart_money_quality": 0.11, "news": 0.06, "event_intel": 0.08, "us_tech_leading": 0.04, "data_quality": 0.13},
            "multi_year": {"technical": 0.12, "fundamental": 0.36, "institutional": 0.09, "smart_money_quality": 0.10, "news": 0.05, "event_intel": 0.08, "us_tech_leading": 0.02, "data_quality": 0.18},
        }
        return weights_by_horizon.get(request.investment_horizon, weights_by_horizon["mid_term_3m"])

    def _news_impact_summary(self, dataset: MarketDataset, related_news: list[str], news_risks: list[str], event_risks: list[str]) -> list[str]:
        rows = [point for point in [*dataset.events, *dataset.news] if not point.missing]
        shock_words = ("大跌", "崩", "血洗", "恐慌", "下跌", "砍單", "下修", "賣壓")
        positive_words = ("CoWoS", "HBM", "NVIDIA", "輝達", "訂單", "產能", "擴產", "受惠", "創高", "調高")
        shocks: list[str] = []
        positives: list[str] = []
        for point in rows:
            value = point.value if isinstance(point.value, dict) else {"summary": point.value}
            text = f"{point.name} {value.get('summary') or value}"
            if any(word in text for word in shock_words):
                shocks.append(f"負面/風險事件：{point.name}。這類訊息會壓低新聞與風險偏好分數，盤前若遇開低或流動性轉弱，不應只因技術趨勢偏多就追價。")
            elif any(word.lower() in text.lower() for word in positive_words):
                positives.append(f"正面/主題事件：{point.name}。此訊息與股性驅動因子有連動，支持事件面或供應鏈分數。")
        summary = [*shocks[:2], *positives[:2]]
        if news_risks or event_risks:
            summary.append(f"新聞風險折抵：{'；'.join([*news_risks, *event_risks][:2])}")
        if not summary and related_news:
            summary.append(f"目前新聞多屬參考訊息，尚未形成明確加減分主軸；最相關標題：{related_news[0]}")
        return summary[:5]

    def _data_score(self, dataset: MarketDataset) -> int:
        score = 100
        score -= 18 if not dataset.price else 0
        score -= 14 if not dataset.fundamentals else 0
        score -= 14 if not dataset.institutional else 0
        score -= 10 if not dataset.news or all(point.missing for point in dataset.news) else 0
        score -= 8 if not dataset.events or all(point.missing for point in dataset.events) else 0
        score -= min(25, len(dataset.limitations) * 6)
        return int(max(0, min(100, score)))

    def _data_quality_summary(self, dataset: MarketDataset, data_score: int) -> list[str]:
        news_rows = len([point for point in dataset.news if not point.missing])
        event_rows = len([point for point in dataset.events if not point.missing])
        coverage = (
            f"資料覆蓋：股價 {len(dataset.price)} 筆、法人 {len(dataset.institutional)} 筆、"
            f"基本面 {len(dataset.fundamentals)} 筆、新聞 {news_rows} 則、官方/IR/供應鏈事件 {event_rows} 筆，資料品質 {data_score}/100。"
        )
        if data_score >= 75:
            judgement = "資料品質足夠支撐本次排序；仍需用盤中成交價驗證預估買賣是否合理。"
        elif data_score >= 55:
            judgement = "資料品質中等，分數可作候選排序，但部位應依資料缺口與價格確認降低。"
        else:
            judgement = "資料品質偏弱，本次以觀察為主；若要交易，需要先補足價格、籌碼、基本面或事件資料。"
        return [coverage, judgement]

    def _friendly_data_message(self, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        lower = text.lower()
        has_data_gap_marker = any(
            marker in lower
            for marker in (
                "data missing",
                "data limitation",
                "unavailable",
                "not configured",
                "fetch failed",
                "no recent news",
                "news/event feed",
                "us leading",
                "ohlcv",
                "price history",
                "institutional trading data",
            )
        )
        if not has_data_gap_marker:
            return text
        if "us leading data missing" in lower:
            return "前一晚美股科技/半導體領先資料暫未取得；本次以產業曝險等級保守估算，盤中需再用實際價格確認。"
        if "no recent news" in lower:
            return "近期新聞來源暫未取得；本次新聞分數採保守估計，需搭配公告、營收與籌碼確認。"
        if "news/event feed" in lower or "newsapi" in lower or "news articles" in lower:
            return "新聞與事件資料源暫時無法取得，事件風險覆蓋不完整。"
        if "live data disabled" in lower:
            return "本次未啟用即時資料，僅能用既有或測試資料做保守模擬。"
        if "price history" in lower or "ohlcv" in lower or "stock ohlcv" in lower:
            return "股價歷史資料不足，技術面與成交回填需降低信心。"
        if "fundamental" in lower or "monthly revenue" in lower or "revenue growth" in lower or "eps" in lower:
            return "基本面或營收資料不足，暫以保守分數處理，需補營收、EPS 或法說資訊。"
        if "institutional" in lower:
            return "法人籌碼資料不足，暫時不能確認買賣超是否連續。"
        if "benchmark" in lower:
            return "Benchmark 資料不足，績效比較信心較低。"
        if lower.startswith("data missing:"):
            text = text.split(":", 1)[1].strip()
        if lower.startswith("data limitation:"):
            text = text.split(":", 1)[1].strip()
        replacements = {
            "unavailable": "尚未取得",
            "not configured": "尚未設定",
            "fetch failed": "抓取失敗",
            "fallback": "備援估算",
            "no ": "未取得 ",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return f"資料不足：{text}" if not text.startswith(("資料", "新聞", "法人", "基本面", "股價", "前一晚", "本次", "Benchmark")) else text

    def _friendly_data_messages(self, values: list[object]) -> list[str]:
        cleaned: list[str] = []
        for value in values or []:
            message = self._friendly_data_message(value)
            if message and message not in cleaned:
                cleaned.append(message)
        return cleaned

    def _paper_trade(self, analyses: list[PotentialStockAnalysis], request: PotentialStockRequest) -> PaperPortfolio:
        cash = request.initial_capital
        invested = 0.0
        trades: list[PaperTradeDecision] = []
        holdings: list[dict[str, Any]] = []
        replacement_suggestions: list[dict[str, Any]] = []
        max_position = request.initial_capital * max(0.01, min(0.5, request.max_position_pct))
        buy_candidates = [item for item in analyses if item.action == "BUY" and item.latest_price and item.latest_price > 0]
        max_positions = max(1, min(30, int(request.max_positions or 5)))
        selected_candidates = buy_candidates[:max_positions]
        overflow_candidates = buy_candidates[max_positions:]

        for analysis in selected_candidates:
            amount = min(max_position, cash)
            lot_size = 1000 if analysis.symbol.endswith((".TW", ".TWO")) else 1
            shares = int(amount // (analysis.latest_price * lot_size)) * lot_size
            if shares <= 0:
                trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="WATCH", price=analysis.latest_price, reason="資金不足或價格過高，暫不買進。"))
                continue
            cost = shares * analysis.latest_price
            cash -= cost
            invested += cost
            analysis.suggested_capital = cost
            analysis.suggested_shares = shares
            trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="BUY", shares=shares, price=analysis.latest_price, amount=cost, reason=analysis.thesis))
            holdings.append({"symbol": analysis.symbol, "company_name": analysis.company_name, "shares": shares, "entry_price": analysis.latest_price, "market_price": analysis.latest_price, "market_value": cost, "unrealized_pl": 0, "score": analysis.score})
        for analysis in overflow_candidates:
            reason = f"已達最多持股 {max_positions} 檔，列為換股候選；若分數持續高於持倉，可盤後評估替換。"
            replacement_suggestions.append({"symbol": analysis.symbol, "company_name": analysis.company_name, "score": analysis.score, "price": analysis.latest_price, "reason": reason})
            trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="WATCH", price=analysis.latest_price, reason=reason))
        for analysis in analyses:
            if analysis.action != "BUY":
                trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action=analysis.action, price=analysis.latest_price, reason=analysis.thesis))
        total = cash + invested
        return PaperPortfolio(initial_capital=request.initial_capital, cash=cash, invested_value=invested, total_value=total, unrealized_pl=0, return_pct=(total - request.initial_capital) / request.initial_capital if request.initial_capital else 0, holdings=holdings, trades=trades, replacement_suggestions=replacement_suggestions)

    def _premarket_plan_portfolio(self, analyses: list[PotentialStockAnalysis], request: PotentialStockRequest) -> PaperPortfolio:
        trades: list[PaperTradeDecision] = []
        replacement_suggestions: list[dict[str, Any]] = []
        max_positions = max(1, min(30, int(request.max_positions or 5)))
        buy_candidates = [item for item in analyses if item.action == "BUY" and item.latest_price and item.latest_price > 0]
        actionable_candidates: list[PotentialStockAnalysis] = []
        deferred_candidates: list[tuple[PotentialStockAnalysis, str]] = []
        for analysis in buy_candidates:
            should_trade, gate_reason = self._should_plan_trade_today(analysis, request)
            if should_trade:
                actionable_candidates.append(analysis)
            else:
                deferred_candidates.append((analysis, gate_reason))

        for analysis in actionable_candidates[:max_positions]:
            max_position = request.initial_capital * max(0.01, min(0.5, request.max_position_pct))
            lot_size = 1000 if analysis.symbol.endswith((".TW", ".TWO")) else 1
            shares = int(max_position // (analysis.latest_price * lot_size)) * lot_size
            analysis.suggested_capital = shares * analysis.latest_price if shares > 0 else 0
            analysis.suggested_shares = shares
            reason = f"盤前預計買進 {shares} 股，預估投入 {analysis.suggested_capital:,.0f}；盤中需用實際開盤/當下價格加滑價確認成交。{analysis.thesis}"
            trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="PLAN_BUY", shares=shares, price=analysis.latest_price, amount=analysis.suggested_capital, reason=reason))
        for analysis in actionable_candidates[max_positions:]:
            reason = f"盤前分數達標，但已超過最多持股 {max_positions} 檔，列為換股候選。"
            replacement_suggestions.append({"symbol": analysis.symbol, "company_name": analysis.company_name, "score": analysis.score, "price": analysis.latest_price, "reason": reason})
            trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="WATCH", price=analysis.latest_price, reason=reason))
        for analysis, reason in deferred_candidates:
            trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="WATCH", price=analysis.latest_price, reason=reason))
        for analysis in analyses:
            if analysis.action != "BUY":
                trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action=analysis.action, price=analysis.latest_price, reason=analysis.thesis))
        return PaperPortfolio(initial_capital=request.initial_capital, cash=request.initial_capital, invested_value=0, total_value=request.initial_capital, unrealized_pl=0, return_pct=0, holdings=[], trades=trades, replacement_suggestions=replacement_suggestions, benchmark=self._paper_benchmark(request), strategy_version=request.strategy_version)

    def _should_plan_trade_today(self, analysis: PotentialStockAnalysis, request: PotentialStockRequest) -> tuple[bool, str]:
        scores = analysis.component_scores or {}
        data_quality = float(scores.get("data_quality") or 0)
        smart_money_quality = float(scores.get("smart_money_quality") or 0)
        fundamental = float(scores.get("fundamental") or 0)
        technical = float(scores.get("technical") or 0)
        institutional = float(scores.get("institutional") or 0)
        score_floor = max(float(request.buy_score or 0), 0)

        if request.risk_reward_profile == "aggressive":
            data_floor, smart_floor, base_floor = 45, 50, 45
        elif request.risk_reward_profile == "conservative":
            data_floor, smart_floor, base_floor = 60, 62, 55
        else:
            data_floor, smart_floor, base_floor = 50, 55, 50

        blockers: list[str] = []
        if analysis.score < score_floor:
            blockers.append(f"總分 {analysis.score}/100 未達買進門檻 {score_floor:g}")
        if data_quality < data_floor:
            blockers.append(f"資料品質 {data_quality:.0f}/100 未達 {data_floor}")
        if smart_money_quality < smart_floor:
            blockers.append(f"籌碼品質 {smart_money_quality:.0f}/100 未達 {smart_floor}")
        if fundamental < base_floor and institutional < smart_floor:
            blockers.append("基本面與籌碼未同時確認")
        if technical < 50:
            blockers.append("價格位置或技術趨勢尚未站穩")
        if not analysis.latest_price or analysis.latest_price <= 0:
            blockers.append("缺少可用價格")

        if blockers:
            return False, f"今日不交易，先列觀察：{'；'.join(blockers)}。{analysis.thesis}"
        return True, "通過今日交易門檻。"
    def _paper_trade_with_ledger(self, analyses: list[PotentialStockAnalysis], request: PotentialStockRequest, case_id: str | None = None) -> PaperPortfolio:
        previous = self.latest_ledger(case_id=case_id) if request.persist else None
        analyses_by_symbol = {item.symbol: item for item in analyses}
        base_capital = self._ledger_initial_capital(previous, request)
        cash = self._float_or_none((previous or {}).get("cash")) if previous else None
        cash = base_capital if cash is None else cash
        holdings = [dict(item) for item in (previous or {}).get("holdings", [])]
        trades: list[PaperTradeDecision] = []
        replacement_suggestions: list[dict[str, Any]] = []
        realized_pl = 0.0
        total_costs = 0.0
        sold_symbols: set[str] = set()

        updated_holdings: list[dict[str, Any]] = []
        for holding in holdings:
            symbol = str(holding.get("symbol") or "")
            analysis = analyses_by_symbol.get(symbol)
            sell_reason = self._sell_reason(holding, analysis, request)
            market_price = self._reference_price(analysis, request) if analysis else self._float_or_none(holding.get("market_price"))
            shares = int(self._float_or_none(holding.get("shares")) or 0)
            entry_price = self._float_or_none(holding.get("entry_price")) or 0
            if sell_reason and market_price and shares > 0:
                sell_price = self._sell_execution_price_from_reference(market_price, request)
                gross = shares * sell_price
                fee_tax = gross * (max(0, request.fee_rate) + max(0, request.tax_rate))
                slippage_cost = shares * max(0, market_price - sell_price)
                cash += gross - fee_tax
                realized_pl += gross - fee_tax - shares * entry_price
                total_costs += fee_tax + slippage_cost
                sold_symbols.add(symbol)
                trades.append(PaperTradeDecision(symbol=symbol, company_name=holding.get("company_name") or self._company_name(symbol), action="SELL", shares=shares, price=sell_price, amount=gross, reason=sell_reason))
                continue
            if market_price and shares > 0:
                holding["market_price"] = market_price
                holding["market_value"] = shares * market_price
                holding["unrealized_pl"] = shares * (market_price - entry_price)
            if analysis:
                holding["score"] = analysis.score
            updated_holdings.append(holding)
        holdings = updated_holdings

        max_positions = max(1, min(30, int(request.max_positions or 5)))
        max_position = base_capital * max(0.01, min(0.5, request.max_position_pct))
        planned_symbols = self._planned_symbols_for_today(request, case_id=case_id) if request.persist else set()
        buy_candidates = [item for item in analyses if item.action == "BUY" and item.latest_price and item.latest_price > 0]
        existing_symbols = {str(item.get("symbol")) for item in holdings}
        for analysis in buy_candidates:
            if analysis.symbol in existing_symbols or analysis.symbol in sold_symbols:
                continue
            if request.persist and not planned_symbols:
                trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="WATCH", price=analysis.latest_price, reason="今日尚無盤前買進計畫，盤中不建立新倉位。"))
                continue
            if planned_symbols and analysis.symbol not in planned_symbols:
                trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="WATCH", price=analysis.latest_price, reason="未列入今日盤前買進計畫，盤中不新增追價。"))
                continue
            if len(holdings) >= max_positions:
                reason = f"已達最多持股 {max_positions} 檔，列為換股候選。"
                replacement_suggestions.append({"symbol": analysis.symbol, "company_name": analysis.company_name, "score": analysis.score, "price": analysis.latest_price, "reason": reason})
                trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="WATCH", price=analysis.latest_price, reason=reason))
                continue
            reference_price = self._reference_price(analysis, request)
            buy_price = self._buy_execution_price(analysis, request)
            if not buy_price or buy_price <= 0:
                trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="WATCH", price=analysis.latest_price, reason="缺少可用盤中成交價，暫不買進。"))
                continue
            lot_size = 1000 if analysis.symbol.endswith((".TW", ".TWO")) else 1
            budget = min(max_position, cash)
            shares = int(budget // (buy_price * lot_size)) * lot_size
            if shares <= 0:
                trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="WATCH", price=buy_price, reason="資金不足，暫不買進。"))
                continue
            gross = shares * buy_price
            fee = gross * max(0, request.fee_rate)
            if gross + fee > cash:
                continue
            cash -= gross + fee
            slippage_cost = shares * max(0, buy_price - (reference_price or buy_price))
            total_costs += fee + slippage_cost
            mark_price = reference_price or buy_price
            market_value = shares * mark_price
            holding = {"symbol": analysis.symbol, "company_name": analysis.company_name, "shares": shares, "entry_price": buy_price, "market_price": mark_price, "market_value": market_value, "unrealized_pl": shares * (mark_price - buy_price), "score": analysis.score, "entry_date": datetime.now(TW_TZ).date().isoformat()}
            holdings.append(holding)
            existing_symbols.add(analysis.symbol)
            analysis.suggested_capital = gross
            analysis.suggested_shares = shares
            trades.append(PaperTradeDecision(symbol=analysis.symbol, company_name=analysis.company_name, action="BUY", shares=shares, price=buy_price, amount=gross, reason=f"盤中用當下股價加滑價，依盤前計畫成交。{analysis.thesis}"))

        invested_value = sum(self._float_or_none(item.get("market_value")) or 0 for item in holdings)
        unrealized_pl = sum(self._float_or_none(item.get("unrealized_pl")) or 0 for item in holdings)
        total_value = cash + invested_value
        return PaperPortfolio(initial_capital=base_capital, cash=cash, invested_value=invested_value, total_value=total_value, unrealized_pl=unrealized_pl, realized_pl=realized_pl, return_pct=(total_value - base_capital) / base_capital if base_capital else 0, holdings=holdings, trades=trades, replacement_suggestions=replacement_suggestions, costs=total_costs, benchmark=self._paper_benchmark(request), strategy_version=request.strategy_version)
    def _postmarket_settlement_portfolio(self, analyses: list[PotentialStockAnalysis], request: PotentialStockRequest, case_id: str | None = None) -> PaperPortfolio:
        previous = self.latest_ledger(case_id=case_id) if request.persist else None
        base_capital = self._ledger_initial_capital(previous, request)
        cash = self._float_or_none((previous or {}).get("cash")) if previous else None
        cash = base_capital if cash is None else cash
        analyses_by_symbol = {item.symbol: item for item in analyses}
        holdings: list[dict[str, Any]] = []
        for holding in [dict(item) for item in (previous or {}).get("holdings", [])]:
            symbol = str(holding.get("symbol") or "")
            analysis = analyses_by_symbol.get(symbol)
            shares = int(self._float_or_none(holding.get("shares")) or 0)
            entry_price = self._float_or_none(holding.get("entry_price")) or 0
            market_price = analysis.latest_price if analysis and analysis.latest_price else self._float_or_none(holding.get("market_price")) or entry_price
            holding["market_price"] = market_price
            holding["market_value"] = shares * market_price
            holding["unrealized_pl"] = shares * (market_price - entry_price)
            if analysis:
                holding["score"] = analysis.score
            holdings.append(holding)
        invested_value = sum(self._float_or_none(item.get("market_value")) or 0 for item in holdings)
        unrealized_pl = sum(self._float_or_none(item.get("unrealized_pl")) or 0 for item in holdings)
        total_value = cash + invested_value
        held_symbols = {str(item.get("symbol") or "") for item in holdings}
        trades = [
            PaperTradeDecision(
                symbol=item.symbol,
                company_name=item.company_name,
                action="HOLD" if item.symbol in held_symbols else "WATCH",
                price=item.latest_price,
                reason="盤後只做結算與追蹤，不新增買進；實際買賣由盤中模擬交易處理。",
            )
            for item in analyses
        ]
        return PaperPortfolio(initial_capital=base_capital, cash=cash, invested_value=invested_value, total_value=total_value, unrealized_pl=unrealized_pl, realized_pl=0, return_pct=(total_value - base_capital) / base_capital if base_capital else 0, holdings=holdings, trades=trades, replacement_suggestions=[], costs=0, benchmark=self._paper_benchmark(request), strategy_version=request.strategy_version)
    def _execution_price(self, analysis: PotentialStockAnalysis, request: PotentialStockRequest) -> float | None:
        return self._buy_execution_price(analysis, request)

    def _reference_price(self, analysis: PotentialStockAnalysis | None, request: PotentialStockRequest) -> float | None:
        if not analysis:
            return None
        if request.report_session == "market_hours":
            return analysis.latest_price
        return analysis.latest_open or analysis.latest_price

    def _buy_execution_price(self, analysis: PotentialStockAnalysis, request: PotentialStockRequest) -> float | None:
        reference = self._reference_price(analysis, request)
        if not reference:
            return None
        slippage = 1 + max(0, request.slippage_bps) / 10000
        return reference * slippage

    def _sell_execution_price_from_reference(self, reference_price: float, request: PotentialStockRequest) -> float:
        slippage = 1 - max(0, request.slippage_bps) / 10000
        return reference_price * slippage

    def _execution_reason_prefix(self, request: PotentialStockRequest) -> str:
        if request.report_session == "market_hours":
            return "盤中依當下價格加滑價執行模擬成交。"
        return "盤前僅產生計畫，不直接成交。"

    def _ledger_initial_capital(self, previous: dict[str, Any] | None, request: PotentialStockRequest) -> float:
        if previous:
            for value in (
                previous.get("initial_capital"),
                (previous.get("settings") or {}).get("initial_capital"),
                (previous.get("portfolio") or {}).get("initial_capital"),
            ):
                parsed = self._float_or_none(value)
                if parsed and parsed > 0:
                    return parsed
        return request.initial_capital

    def _planned_symbols_for_today(self, request: PotentialStockRequest, case_id: str | None = None) -> set[str]:
        today = datetime.now(TW_TZ).date().isoformat()
        rows = [row for row in self.history(limit=500, case_id=case_id) if row.get("trading_date") == today and row.get("report_session") == "pre_market"]
        rows.sort(key=lambda item: str(item.get("generated_at") or ""))
        if not rows:
            return set()
        planned_record = rows[0]
        symbols = {
            trade.get("symbol")
            for trade in (planned_record.get("portfolio") or {}).get("trades") or []
            if trade.get("action") == "PLAN_BUY"
        }
        return {str(symbol) for symbol in symbols if symbol}

    def _sell_reason(self, holding: dict[str, Any], analysis: PotentialStockAnalysis | None, request: PotentialStockRequest) -> str:
        entry_price = self._float_or_none(holding.get("entry_price"))
        market_price = analysis.latest_price if analysis and analysis.latest_price else self._float_or_none(holding.get("market_price"))
        if not entry_price or not market_price:
            return ""
        return_pct = (market_price - entry_price) / entry_price
        if return_pct <= -abs(request.stop_loss_pct):
            return f"觸發停損：目前報酬 {self._pct(return_pct)}，低於 {self._pct(-abs(request.stop_loss_pct))}。"
        if return_pct >= abs(request.take_profit_pct):
            return f"觸發停利：目前報酬 {self._pct(return_pct)}，高於 {self._pct(abs(request.take_profit_pct))}。"
        if analysis and analysis.score < request.sell_score:
            return f"分數跌破賣出門檻：{analysis.score}/100，低於 {request.sell_score}/100。"
        return ""

    def _holding_days(self, holding: dict[str, Any], today: Any) -> int:
        try:
            entry = datetime.fromisoformat(str(holding.get("entry_date"))).date()
            return max(0, (today - entry).days)
        except (TypeError, ValueError):
            return 0

    def _paper_benchmark(self, request: PotentialStockRequest) -> dict[str, Any]:
        return {"symbol": request.benchmark_symbol, "note": "Benchmark comparison is tracked when enough price data is available."}
    def _strategy_settings(self, request: PotentialStockRequest) -> dict[str, Any]:
        return {
            "strategy_version": request.strategy_version,
            "initial_capital": request.initial_capital,
            "risk_reward_profile": request.risk_reward_profile,
            "investment_horizon": request.investment_horizon,
            "buy_score": request.buy_score,
            "watch_score": request.watch_score,
            "sell_score": request.sell_score,
            "stop_loss_pct": request.stop_loss_pct,
            "take_profit_pct": request.take_profit_pct,
            "swap_score_gap": request.swap_score_gap,
            "min_hold_days": request.min_hold_days,
            "max_positions": request.max_positions,
            "max_position_pct": request.max_position_pct,
            "fee_rate": request.fee_rate,
            "tax_rate": request.tax_rate,
            "slippage_bps": request.slippage_bps,
            "benchmark_symbol": request.benchmark_symbol,
        }

    def _settings_from_request(self, request: PotentialStockRequest) -> dict[str, Any]:
        return {
            "symbols": self._normalize_symbols(request.symbols or self.DEFAULT_SYMBOLS),
            "market_universe": request.market_universe,
            "market_universes": request.market_universes or [request.market_universe],
            "initial_capital": request.initial_capital,
            "max_positions": request.max_positions,
            "max_position_pct": request.max_position_pct,
            "buy_score": request.buy_score,
            "watch_score": request.watch_score,
            "sell_score": request.sell_score,
            "stop_loss_pct": request.stop_loss_pct,
            "take_profit_pct": request.take_profit_pct,
            "swap_score_gap": request.swap_score_gap,
            "min_hold_days": request.min_hold_days,
            "fee_rate": request.fee_rate,
            "tax_rate": request.tax_rate,
            "slippage_bps": request.slippage_bps,
            "benchmark_symbol": request.benchmark_symbol,
            "strategy_version": request.strategy_version,
            "risk_reward_profile": request.risk_reward_profile,
            "investment_horizon": request.investment_horizon,
            "use_live_data": request.use_live_data,
            "use_us_tech_leading": request.use_us_tech_leading,
            "use_ai_analysis": request.use_ai_analysis,
        }

    def _request_from_settings(self, settings: dict[str, Any]) -> PotentialStockRequest:
        data = {**self.default_settings(), **(settings or {})}
        symbols = data.get("symbols") or []
        if isinstance(symbols, str):
            data["symbols"] = [item.strip() for item in symbols.replace(";", ",").split(",") if item.strip()]
        return PotentialStockRequest.model_validate(data)

    def _analysis_only_portfolio(self, analyses: list[PotentialStockAnalysis], request: PotentialStockRequest) -> PaperPortfolio:
        trades = [
            PaperTradeDecision(
                symbol=analysis.symbol,
                company_name=analysis.company_name,
                action="WATCH",
                price=analysis.latest_price,
                reason=f"盤中模式只做觀察與參考，不建立正式買賣紀錄。{analysis.thesis}",
            )
            for analysis in analyses
        ]
        return PaperPortfolio(
            initial_capital=request.initial_capital,
            cash=request.initial_capital,
            invested_value=0,
            total_value=request.initial_capital,
            unrealized_pl=0,
            return_pct=0,
            holdings=[],
            trades=trades,
            replacement_suggestions=[],
        )

    def _risk_reward_label(self, value: str | None) -> str:
        return {"conservative": "低風險/穩健報酬", "balanced": "中風險/中報酬", "aggressive": "高風險/高報酬"}.get(str(value or ""), str(value or "--"))

    def _horizon_label(self, value: str | None) -> str:
        return {"short_weeks": "短線（數週）", "mid_term_3m": "中長線（約 3 個月）", "long_6m": "長線（約半年）", "multi_year": "長期（數年）"}.get(str(value or ""), str(value or "--"))

    def _advantages(self, scores: dict[str, int]) -> list[str]:
        return _potential_advantages_v2(self, scores)

    def _risks(self, scores: dict[str, int], dataset: MarketDataset) -> list[str]:
        return _potential_risks_v2(self, scores, dataset)

    def _thesis(self, symbol: str, company_name: str, score: int, action: str, advantages: list[str], risks: list[str], score_explanation: list[str] | None = None) -> str:
        risk = risks[0] if risks else "暫無重大風險訊號。"
        advantage = advantages[0] if advantages else "暫無明確單一優勢。"
        score_detail = ""
        if score_explanation:
            score_detail = f" 分數拆解：{score_explanation[0]}"
        return f"{symbol} {company_name} 分數 {score}/100，建議 {self._action_label(action)}。主要理由：{advantage} 主要風險：{risk}{score_detail}"

    def _market_stance(self, analyses: list[PotentialStockAnalysis]) -> str:
        if not analyses:
            return "尚無候選資料"
        average_score = mean(item.score for item in analyses)
        buy_count = sum(1 for item in analyses if item.action == "BUY")
        if buy_count >= 3 and average_score >= 68:
            return "偏多"
        if average_score >= 58:
            return "中性偏多"
        return "保守觀望"

    def _markdown(self, request: PotentialStockRequest, market_stance: str, analyses: list[PotentialStockAnalysis], portfolio: PaperPortfolio, limitations: list[str]) -> str:
        session_title = {"pre_market": "盤前選股計畫", "market_hours": "盤中模擬交易", "post_market": "盤後結算"}[request.report_session]
        ranking = "\n".join(f"- {i + 1}. {a.symbol} {a.company_name}: {a.score}/100, {self._action_label(a.action)}, {self._risk_label(a.risk_level)}" for i, a in enumerate(analyses)) or "- 尚無候選"
        trades = "\n".join(f"- {t.symbol} {t.company_name} {self._action_label(t.action)} {t.shares} 股 @ {t.price or 'N/A'}：{t.reason}" for t in portfolio.trades) or "- 尚無操作"
        holdings = "\n".join(f"- {row['symbol']} {row.get('company_name', '')}: {row.get('shares', 0)} 股，市值 {row.get('market_value', 0):.0f}，分數 {row.get('score', '--')}" for row in portfolio.holdings) or "- 尚無持倉"
        replacements = "\n".join(f"- {item['symbol']} {item.get('company_name', '')}: {item['score']}/100，{item['reason']}" for item in portfolio.replacement_suggestions) or "- 尚無換股候選"
        per_stock = "\n\n".join(self._stock_markdown(item) for item in analyses)
        limits = "\n".join(f"- {item}" for item in limitations) or "- 尚無重大資料限制"
        us_enabled = "啟用" if request.use_us_tech_leading else "停用"
        return f"""# 潛力股模擬操作報告
產生時間：{datetime.now(TW_TZ).isoformat(timespec="seconds")}

## {session_title}

- 市場狀態：{market_stance}
- 初始模擬資金：{request.initial_capital:,.0f}
- 現金：{portfolio.cash:,.0f}
- 持股市值：{portfolio.invested_value:,.0f}
- 帳戶淨值：{portfolio.total_value:,.0f}
- 模擬報酬：{portfolio.return_pct * 100:.2f}%
- 美股科技領先因子：{us_enabled}

## 潛力股排行
{ranking}

## 模擬操作
{trades}

## 目前持倉
{holdings}

## 換股候選
{replacements}

## 個股分析
{per_stock}

## 策略設定
- 單股上限：{request.max_position_pct * 100:.1f}%
- 最多持股：{request.max_positions}
- 買進門檻：{request.buy_score}/100
- 觀察門檻：{request.watch_score}/100
- 賣出門檻：{request.sell_score}/100
- 風險/報酬：{self._risk_reward_label(request.risk_reward_profile)}
- 投資週期：{self._horizon_label(request.investment_horizon)}
- 停損：{self._pct(-abs(request.stop_loss_pct))}
- 停利：{self._pct(abs(request.take_profit_pct))}
- 策略版本：{request.strategy_version}

## 資料限制
{limits}
"""

    def _stock_markdown(self, item: PotentialStockAnalysis) -> str:
        def bullets(values: list[str]) -> str:
            return "\n".join(f"- {value}" for value in values) if values else "- 尚無資料"
        links = "\n".join(
            f"- [{link.get('tier_label') or link.get('source')}: {link.get('title')}]({link.get('url')})"
            for link in item.evidence_links[:5]
            if link.get("url")
        ) or "- 尚無可追溯連結"
        return f"""### {item.symbol} {item.company_name} - {self._action_label(item.action)}（{item.score}/100）
投資論點：{item.thesis}

分數拆解：
{bullets(item.score_explanation)}

基本面：
{bullets(item.fundamental_summary)}

籌碼面：
{bullets(item.institutional_summary)}

技術面：
{bullets(item.technical_summary)}

美股科技領先：
{bullets(item.us_market_summary)}

營運狀況：
{bullets(item.operating_summary)}

近期優勢：
{bullets(item.advantages)}

相關新聞：
{bullets(item.related_news)}

新聞/事件衝擊：
{bullets(item.news_impact_summary)}

資料來源連結：
{links}

主要風險：
{bullets(item.risks)}
"""
    def _company_name(self, symbol: str | None) -> str:
        return self.STOCK_NAMES.get(str(symbol or "").upper(), "")

    def _action_label(self, action: str | None) -> str:
        return {"PLAN_BUY": "預計買進", "BUY": "買進", "HOLD": "持有", "WATCH": "觀察", "AVOID": "避開", "SELL": "賣出", "SNAPSHOT": "快照"}.get(str(action or ""), str(action or "--"))

    def _risk_label(self, risk: str | None) -> str:
        return {"Low": "低", "Medium": "中", "High": "高"}.get(str(risk or ""), str(risk or "--"))

    def _pct(self, value: float | None) -> str:
        return "資料不足" if value is None else f"{value * 100:.2f}%"

    def _numeric_value(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            for key in ("buy", "sell", "buy_sell", "value"):
                if key in value:
                    return self._float_or_none(value[key])
        return self._float_or_none(value)

    def _float_or_none(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _format_datapoint(self, point: DataPoint) -> str:
        if isinstance(point.value, dict):
            compact = ", ".join(f"{self._field_label(key)}: {value}" for key, value in list(point.value.items())[:4])
            return f"{point.name}: {compact}"
        return f"{point.name}: {point.value}"

    def _field_label(self, key: str) -> str:
        return {"date": "日期", "stock_id": "股票代號", "country": "市場", "revenue": "營收", "revenue_year_growth": "年增率", "YoY": "年增率", "yoy": "年增率", "growth_rate": "成長率"}.get(str(key), str(key))

def _potential_advantages_v2(self: PotentialStockService, scores: dict[str, int]) -> list[str]:
    advantages: list[str] = []
    if scores.get("technical", 50) >= 70:
        advantages.append("\u6280\u8853\u9762\u8da8\u52e2\u504f\u591a\u3002")
    if scores.get("fundamental", 50) >= 65:
        advantages.append("\u57fa\u672c\u9762\u6216\u71df\u6536\u52d5\u80fd\u76f8\u5c0d\u6b63\u5411\u3002")
    if scores.get("institutional", 50) >= 65:
        advantages.append("\u7c4c\u78bc\u9762\u6709\u6cd5\u4eba\u504f\u591a\u8de1\u8c61\u3002")
    if scores.get("smart_money_quality", 50) >= 70:
        advantages.append("籌碼、基本面與價格位置同向，符合「籌碼是腳印、基本面是原因」的確認邏輯。")
    if scores.get("news", 50) >= 65:
        advantages.append("\u8fd1\u671f\u65b0\u805e\u4e8b\u4ef6\u504f\u6b63\u5411\u3002")
    if scores.get("event_intel", 50) >= 65:
        advantages.append("官方公告、公司 IR、法說或供應鏈情報對本次判斷提供較高可信度支撐。")
    if scores.get("us_tech_leading", 50) >= 55:
        advantages.append("\u5df2\u7d0d\u5165\u524d\u4e00\u665a\u7f8e\u80a1\u79d1\u6280/\u534a\u5c0e\u9ad4\u4f5c\u70ba\u53f0\u80a1\u76e4\u524d\u9818\u5148\u56e0\u5b50\u3002")
    return advantages or ["\u66ab\u7121\u660e\u78ba\u55ae\u4e00\u512a\u52e2\uff0c\u9700\u6301\u7e8c\u89c0\u5bdf\u5f8c\u7e8c\u8cc7\u6599\u3002"]


def _potential_risks_v2(self: PotentialStockService, scores: dict[str, int], dataset: MarketDataset) -> list[str]:
    risks: list[str] = []
    if scores.get("technical", 50) < 50:
        risks.append("\u6280\u8853\u9762\u5c1a\u672a\u8f49\u5f37\uff0c\u8ffd\u50f9\u98a8\u96aa\u8f03\u9ad8\u3002")
    if scores.get("fundamental", 50) < 50:
        risks.append("\u57fa\u672c\u9762\u8cc7\u6599\u4e0d\u8db3\u6216\u52d5\u80fd\u504f\u5f31\u3002")
    if scores.get("institutional", 50) < 50:
        risks.append("\u7c4c\u78bc\u9762\u5c1a\u672a\u770b\u5230\u660e\u78ba\u6cd5\u4eba\u652f\u6301\u3002")
    if scores.get("institutional", 50) >= 65 and scores.get("fundamental", 50) < 55:
        risks.append("籌碼偏多但基本面尚未同步，不能把法人或分點買超直接視為買進理由。")
    if scores.get("smart_money_quality", 50) < 45:
        risks.append("籌碼、基本面與價格位置未同向，需降低追價權重。")
    if scores.get("us_tech_leading", 50) < 45:
        risks.append("\u524d\u4e00\u665a\u7f8e\u80a1\u79d1\u6280/\u534a\u5c0e\u9ad4\u9818\u5148\u8a0a\u865f\u504f\u5f31\uff0c\u53f0\u80a1\u958b\u76e4\u524d\u9700\u964d\u4f4e\u8ffd\u50f9\u885d\u52d5\u3002")
    if scores.get("data_quality", 50) < 60:
        risks.append("\u8cc7\u6599\u54c1\u8cea\u4e0d\u8db3\uff0c\u6a21\u64ec\u64cd\u4f5c\u61c9\u964d\u4f4e\u90e8\u4f4d\u6216\u7b49\u5f85\u88dc\u9f4a\u8cc7\u6599\u3002")
    risks.extend(self._friendly_data_messages(dataset.limitations[:3]))
    return risks[:7] or ["\u66ab\u7121\u91cd\u5927\u98a8\u96aa\u8a0a\u865f\uff0c\u4f46\u4ecd\u9700\u7528\u76e4\u4e2d\u50f9\u78ba\u8a8d\u662f\u5426\u6210\u4ea4\u3002"]


PotentialStockService._advantages = _potential_advantages_v2
PotentialStockService._risks = _potential_risks_v2













