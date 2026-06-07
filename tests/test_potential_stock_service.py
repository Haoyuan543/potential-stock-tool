from __future__ import annotations

import asyncio
import importlib
import os
import unittest
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

import backend.services.potential_stock_service as potential_stock_module
import backend.services.research_collector as research_collector_module
from backend.config import get_settings
from backend.main import app
from backend.models import DataPoint, MarketDataset, PotentialBacktestRequest, PotentialStockRequest, PriceBar
from backend.services.official_research import OfficialResearchFetcher
from backend.services.potential_stock_cron import PotentialStockCronRunner
from backend.services.potential_stock_service import PotentialStockService
from backend.services.research_collector import ResearchCollectRequest, ResearchCollectorService


TW_TEST_TZ = timezone(timedelta(hours=8))


class PotentialStockServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PotentialStockService()

    def test_default_universe_is_semiconductor(self) -> None:
        request = PotentialStockRequest(use_live_data=False)
        symbols = self.service._symbols_for_request(request)

        self.assertEqual(request.market_universe, "semiconductor")
        self.assertIn("2330.TW", symbols)
        self.assertIn("2454.TW", symbols)
        self.assertNotIn("2603.TW", symbols)

    def test_backend_universe_selection_without_symbols(self) -> None:
        request = PotentialStockRequest(market_universe="financial", use_live_data=False)
        symbols = self.service._symbols_for_request(request)

        self.assertIn("2881.TW", symbols)
        self.assertIn("2891.TW", symbols)
        self.assertNotIn("2330.TW", symbols)

    def test_backend_multi_universe_selection_merges_and_dedupes(self) -> None:
        request = PotentialStockRequest(market_universes=["semiconductor", "financial"], use_live_data=False)
        symbols = self.service._symbols_for_request(request)

        self.assertIn("2330.TW", symbols)
        self.assertIn("2881.TW", symbols)
        self.assertEqual(len(symbols), len(set(symbols)))

    def test_default_risk_profile_and_horizon(self) -> None:
        request = PotentialStockRequest(use_live_data=False)

        self.assertEqual(request.risk_reward_profile, "balanced")
        self.assertEqual(request.investment_horizon, "mid_term_3m")

    def test_official_research_profiles_are_stock_specific(self) -> None:
        fetcher = OfficialResearchFetcher()
        tsmc = fetcher.profile_for("2330")
        evergreen = fetcher.profile_for("2603")

        self.assertIn("CoWoS", tsmc["drivers"])
        self.assertIn("NVIDIA", tsmc["drivers"])
        self.assertIn("SCFI", evergreen["drivers"])
        self.assertIn("紅海", evergreen["drivers"])
        self.assertNotEqual(tsmc["role"], evergreen["role"])

    def test_official_research_scores_stock_driver_relevance(self) -> None:
        fetcher = OfficialResearchFetcher()
        profile = fetcher.profile_for("2330")
        point = fetcher._point(
            "股性網路搜尋",
            "台積電 CoWoS 產能受惠 NVIDIA AI 訂單",
            "CoWoS、HBM 與先進封裝需求升溫。",
            "supply_chain_search",
            "https://example.com/tsmc-cowos",
            62,
            profile,
        )

        self.assertIsInstance(point.value, dict)
        self.assertGreaterEqual(point.value["relevance_score"], 20)
        self.assertIn("CoWoS", point.value["drivers_hit"])
        self.assertIn("NVIDIA", point.value["drivers_hit"])

    def test_scoring_and_paper_trade_buy_candidate_has_chinese_name(self) -> None:
        dataset = self._strong_dataset("2330")
        request = PotentialStockRequest(
            symbols=["2330.TW"],
            initial_capital=1_000_000,
            max_position_pct=0.2,
            buy_score=60,
            use_live_data=False,
            persist=False,
        )

        analysis = self.service._analyze_dataset(dataset, request)
        portfolio = self.service._paper_trade([analysis], request)

        self.assertEqual(analysis.symbol, "2330.TW")
        self.assertEqual(analysis.company_name, "台積電")
        self.assertEqual(analysis.action, "BUY")
        self.assertGreaterEqual(analysis.score, 60)
        self.assertEqual(len(portfolio.holdings), 1)
        self.assertEqual(portfolio.holdings[0]["company_name"], "台積電")
        self.assertLessEqual(portfolio.invested_value, 200_000)
        self.assertGreater(portfolio.trades[0].shares, 0)

    def test_investment_horizon_changes_component_weighting(self) -> None:
        scores = {"technical": 90, "fundamental": 45, "institutional": 55, "news": 80, "data_quality": 70}
        short_request = PotentialStockRequest(investment_horizon="short_weeks", risk_reward_profile="aggressive", use_live_data=False)
        long_request = PotentialStockRequest(investment_horizon="multi_year", risk_reward_profile="conservative", use_live_data=False)

        short_score = self.service._weighted_score(scores, short_request)
        long_score = self.service._weighted_score(scores, long_request)

        self.assertGreater(short_score, long_score)

    def test_us_tech_leading_factor_is_default_for_premarket_prediction(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], use_live_data=False, persist=False)
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request)

        self.assertIn("us_tech_leading", analysis.component_scores)
        self.assertGreaterEqual(analysis.component_scores["us_tech_leading"], 55)
        self.assertTrue(any("美股科技" in item and "保守估算" in item for item in analysis.data_limitations))
        self.assertFalse(any("US Leading Data Missing" in item for item in analysis.data_limitations))
        self.assertTrue(any("NVDA" in item or "QQQ" in item for item in analysis.us_market_summary))

    def test_us_tech_leading_factor_uses_actual_leader_context_when_available(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], use_live_data=True, persist=False)
        context = {
            "available": True,
            "rows": [
                {"symbol": "NVDA", "return_pct": 0.035},
                {"symbol": "AMD", "return_pct": 0.021},
                {"symbol": "SMH", "return_pct": 0.018},
                {"symbol": "QQQ", "return_pct": 0.009},
            ],
            "average_return_pct": 0.02075,
            "semiconductor_return_pct": 0.02467,
            "positive_ratio": 1.0,
            "leader_count": 4,
            "source": "test feed",
        }
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request, us_tech_context=context)

        self.assertIn("us_tech_leading", analysis.component_scores)
        self.assertGreater(analysis.component_scores["us_tech_leading"], 60)
        self.assertFalse(any("US Leading Data Missing" in item for item in analysis.data_limitations))
        self.assertTrue(any("平均漲跌" in item and "NVDA" in " ".join(analysis.us_market_summary) for item in analysis.us_market_summary))

    def test_us_tech_leading_factor_can_be_disabled(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], use_live_data=False, persist=False, use_us_tech_leading=False)
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request)

        self.assertNotIn("us_tech_leading", analysis.component_scores)
        self.assertEqual(analysis.us_market_summary, [])

    def test_smart_money_quality_rewards_aligned_chip_fundamental_and_price(self) -> None:
        score, summary = self.service._smart_money_quality_signal({"technical": 76, "fundamental": 68, "institutional": 70, "news": 55})

        self.assertGreaterEqual(score, 70)
        self.assertTrue(any("籌碼是腳印" in item for item in summary))

    def test_smart_money_quality_discounts_chip_only_signal(self) -> None:
        score, summary = self.service._smart_money_quality_signal({"technical": 52, "fundamental": 45, "institutional": 72, "news": 55})
        request = PotentialStockRequest(symbols=["2330.TW"], use_live_data=False, persist=False)
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request)
        analysis.component_scores.update({"technical": 52, "fundamental": 45, "institutional": 72, "smart_money_quality": score})
        risks = self.service._risks(analysis.component_scores, self._strong_dataset("2330"))

        self.assertLess(score, 60)
        self.assertTrue(any("基本面尚未跟上" in item for item in summary))
        self.assertTrue(any("不能把法人" in item for item in risks))

    def test_premarket_can_choose_not_to_trade_when_quality_gate_fails(self) -> None:
        request = PotentialStockRequest(
            symbols=["2330.TW"],
            initial_capital=1_000_000,
            report_session="pre_market",
            buy_score=60,
            risk_reward_profile="balanced",
            use_live_data=False,
            persist=False,
        )
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request)
        analysis.action = "BUY"
        analysis.score = 76
        analysis.component_scores.update(
            {
                "technical": 68,
                "fundamental": 45,
                "institutional": 72,
                "smart_money_quality": 48,
                "data_quality": 84,
            }
        )

        portfolio = self.service._premarket_plan_portfolio([analysis], request)

        self.assertEqual(portfolio.cash, 1_000_000)
        self.assertEqual(portfolio.invested_value, 0)
        self.assertFalse(any(trade.action == "PLAN_BUY" for trade in portfolio.trades))
        self.assertTrue(any(trade.action == "WATCH" and "今日不交易" in trade.reason for trade in portfolio.trades))

    def test_max_positions_limits_holdings_and_creates_replacement_candidates(self) -> None:
        request = PotentialStockRequest(initial_capital=10_000_000, max_positions=2, max_position_pct=0.1, buy_score=60, use_live_data=False, persist=False)
        analyses = []
        for ticker in ["2330", "2454", "2303", "2379"]:
            analyses.append(self.service._analyze_dataset(self._strong_dataset(ticker), request))
        analyses.sort(key=lambda item: item.score, reverse=True)

        portfolio = self.service._paper_trade(analyses, request)

        self.assertLessEqual(len(portfolio.holdings), 2)
        self.assertGreaterEqual(len(portfolio.replacement_suggestions), 2)
        self.assertIn("已達最多持股", portfolio.replacement_suggestions[0]["reason"])

    def test_empty_live_disabled_report_keeps_cash(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], initial_capital=1_000_000, use_live_data=False, persist=False)
        dataset = MarketDataset(ticker="2330.TW", limitations=["Data Missing: test dataset is empty."])

        analysis = self.service._analyze_dataset(dataset, request)
        portfolio = self.service._paper_trade([analysis], request)

        self.assertEqual(analysis.action, "AVOID")
        self.assertEqual(portfolio.cash, 1_000_000)
        self.assertEqual(portfolio.invested_value, 0)

    def test_potential_stock_analysis_hides_engineering_missing_language(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], use_live_data=True, persist=False)
        dataset = MarketDataset(
            ticker="2330.TW",
            limitations=[
                "Data Missing: news/event feed unavailable.",
                "US Leading Data Missing: US market leader prices unavailable; using exposure-based fallback score.",
            ],
        )

        analysis = self.service._analyze_dataset(dataset, request)
        combined = "\n".join(analysis.related_news + analysis.risks + analysis.data_limitations)

        self.assertNotIn("Data Missing", combined)
        self.assertNotIn("unavailable", combined)
        self.assertNotIn("US Leading Data Missing", combined)
        self.assertIn("新聞與事件資料源暫時無法取得", combined)
        self.assertIn("美股科技/半導體領先資料暫未取得", combined)

    def test_research_collector_persists_reusable_dataset_bundle(self) -> None:
        original_store = research_collector_module.potential_stock_research_store
        research_collector_module.potential_stock_research_store = self._memory_store([])
        try:
            collector = ResearchCollectorService()
            dataset = self._strong_dataset("2330")
            dataset.ticker = "2330.TW"
            research_collector_module.potential_stock_research_store.append(collector._dataset_record(dataset, datetime.now(TW_TEST_TZ)))

            cached = collector.latest_dataset("2330.TW", max_age_minutes=60)

            self.assertIsNotNone(cached)
            self.assertEqual(cached.ticker, "2330.TW")
            self.assertGreaterEqual(len(cached.price), 20)
        finally:
            research_collector_module.potential_stock_research_store = original_store

    def test_research_collector_quality_counts_research_v2_sources(self) -> None:
        collector = ResearchCollectorService()
        dataset = self._strong_dataset("2330")
        dataset.ticker = "2330.TW"
        dataset.events = [
            DataPoint(source="MOPS 重大訊息", name="official", value={"tier": "official_mops", "credibility": 98}, url="https://mops.twse.com.tw/mops/web/t05st01"),
            DataPoint(source="公司 IR", name="ir", value={"tier": "company_ir", "credibility": 86}, url="https://investor.tsmc.com/chinese"),
            DataPoint(source="供應鏈關鍵字搜尋", name="supply", value={"tier": "supply_chain_search", "credibility": 68}, url="https://example.com"),
        ]

        quality = collector._dataset_quality(dataset)

        self.assertEqual(quality["event_rows"], 3)
        self.assertEqual(quality["official_rows"], 1)
        self.assertEqual(quality["ir_rows"], 1)
        self.assertEqual(quality["supply_chain_rows"], 1)

    def test_potential_stock_service_prefers_research_cache_before_live_fetch(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], use_live_data=True, persist=False)
        dataset = self._strong_dataset("2330")
        dataset.ticker = "2330.TW"

        class CacheOnlyCollector:
            def latest_dataset(self, symbol, max_age_minutes=240):
                return dataset if symbol == "2330.TW" else None

            def latest_datasets(self, symbols, max_age_minutes=240):
                return [dataset], []

            def latest_us_tech_context(self, max_age_minutes=720):
                return None

            async def collect(self, request):
                raise AssertionError("collector should not refresh when research cache is available")

        async def fail_collect(_symbol):
            raise AssertionError("live fetch should not run when research cache is available")

        self.service.research_collector = CacheOnlyCollector()
        self.service.fetcher.collect = fail_collect

        report = asyncio.run(self.service.run(request))

        self.assertEqual(report.analyses[0].symbol, "2330.TW")
        self.assertGreaterEqual(report.analyses[0].score, 60)

    def test_potential_stock_service_auto_refreshes_research_cache_before_live_fetch(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], use_live_data=True, persist=False, use_us_tech_leading=False)
        dataset = self._strong_dataset("2330")
        dataset.ticker = "2330.TW"

        class CollectingCollector:
            def __init__(self):
                self.datasets = {}
                self.collect_count = 0

            def latest_dataset(self, symbol, max_age_minutes=240):
                return self.datasets.get(symbol)

            def latest_datasets(self, symbols, max_age_minutes=240):
                present = [self.datasets[symbol] for symbol in symbols if symbol in self.datasets]
                missing = [symbol for symbol in symbols if symbol not in self.datasets]
                return present, missing

            def latest_us_tech_context(self, max_age_minutes=720):
                return None

            async def collect(self, collect_request: ResearchCollectRequest):
                self.collect_count += 1
                for symbol in collect_request.symbols:
                    self.datasets[symbol] = dataset
                return {"ok": True, "collected_count": len(collect_request.symbols)}

        async def fail_collect(_symbol):
            raise AssertionError("direct live fetch should not run after collector refresh")

        collector = CollectingCollector()
        self.service.research_collector = collector
        self.service.fetcher.collect = fail_collect

        report = asyncio.run(self.service.run(request))

        self.assertEqual(collector.collect_count, 1)
        self.assertEqual(report.analyses[0].symbol, "2330.TW")

    def test_potential_stock_analysis_reports_data_coverage_summary(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], use_live_data=False, persist=False)
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request)

        self.assertTrue(any("資料覆蓋" in item and "資料品質" in item for item in analysis.operating_summary))

    def test_potential_stock_analysis_uses_official_event_evidence_links(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], use_live_data=False, persist=False)
        dataset = self._strong_dataset("2330")
        dataset.events = [
            DataPoint(
                source="MOPS 重大訊息",
                name="台積電產能與先進封裝說明",
                value={"summary": "CoWoS 產能與 AI 訂單需求持續增加", "tier": "official_mops", "credibility": 98},
                url="https://mops.twse.com.tw/mops/web/t05st01",
            ),
            DataPoint(
                source="公司 IR",
                name="台積電投資人關係",
                value={"summary": "公司 IR 法說與財報簡報", "tier": "company_ir", "credibility": 86},
                url="https://investor.tsmc.com/chinese",
            ),
            DataPoint(
                source="供應鏈關鍵字搜尋",
                name="輝達 AI server supply chain",
                value={"summary": "AI server、HBM、CoWoS 需求", "tier": "supply_chain_search", "credibility": 68, "matched_keywords": ["HBM", "CoWoS"]},
                url="https://example.com/supply-chain",
            ),
        ]

        analysis = self.service._analyze_dataset(dataset, request)

        self.assertIn("event_intel", analysis.component_scores)
        self.assertGreaterEqual(analysis.component_scores["event_intel"], 65)
        self.assertTrue(any("官方重大訊息" in item or "公司 IR" in item for item in analysis.related_news))
        self.assertGreaterEqual(len(analysis.evidence_links), 3)
        self.assertEqual(analysis.evidence_links[0]["tier"], "official_mops")

    def test_evidence_links_are_limited_to_five_and_prioritize_official_sources(self) -> None:
        dataset = self._strong_dataset("2330")
        dataset.events = [
            DataPoint(source="供應鏈關鍵字搜尋", name=f"search {index}", value={"tier": "supply_chain_search", "credibility": 65}, url=f"https://example.com/search-{index}")
            for index in range(8)
        ]
        dataset.events.append(
            DataPoint(source="MOPS 重大訊息", name="official", value={"tier": "official_mops", "credibility": 98}, url="https://mops.twse.com.tw/mops/web/t05st01")
        )

        links = self.service._evidence_links(dataset)

        self.assertEqual(len(links), 5)
        self.assertEqual(links[0]["tier"], "official_mops")

    def test_auto_report_session_resolves_by_taiwan_market_time(self) -> None:
        self.assertEqual(self.service._resolve_report_session("auto", datetime(2026, 6, 5, 8, 30, tzinfo=TW_TEST_TZ)), "pre_market")
        self.assertEqual(self.service._resolve_report_session("auto", datetime(2026, 6, 5, 10, 0, tzinfo=TW_TEST_TZ)), "market_hours")
        self.assertEqual(self.service._resolve_report_session("auto", datetime(2026, 6, 5, 20, 0, tzinfo=TW_TEST_TZ)), "post_market")
        self.assertEqual(self.service._resolve_report_session("auto", datetime(2026, 6, 6, 10, 0, tzinfo=TW_TEST_TZ)), "post_market")

    def test_reference_market_hours_report_does_not_create_new_simulated_buys(self) -> None:
        request = PotentialStockRequest(
            symbols=["2330.TW"],
            report_session="market_hours",
            initial_capital=1_000_000,
            buy_score=60,
            use_live_data=False,
            persist=False,
        )
        dataset = self._strong_dataset("2330")
        analysis = self.service._analyze_dataset(dataset, request)

        portfolio = self.service._analysis_only_portfolio([analysis], request)

        self.assertEqual(len(portfolio.holdings), 0)
        self.assertEqual(portfolio.cash, 1_000_000)
        self.assertEqual(portfolio.trades[0].action, "WATCH")
        self.assertIn("盤中模式只做觀察", portfolio.trades[0].reason)

    def test_intraday_executes_premarket_plan_at_current_price_plus_slippage(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], report_session="market_hours", initial_capital=1_000_000, buy_score=60, use_live_data=False, persist=True, slippage_bps=10)
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request)
        self.service.latest_ledger = lambda case_id=None: None
        self.service.history = lambda limit=500, case_id=None: [
            {
                "generated_at": "2026-06-06T08:00:00+08:00",
                "trading_date": datetime.now(TW_TEST_TZ).date().isoformat(),
                "report_session": "pre_market",
                "portfolio": {"trades": [{"symbol": "2330.TW", "action": "PLAN_BUY"}]},
            }
        ]

        portfolio = self.service._paper_trade_with_ledger([analysis], request)

        self.assertEqual(len(portfolio.holdings), 1)
        self.assertEqual(portfolio.trades[0].action, "BUY")
        self.assertAlmostEqual(portfolio.trades[0].price, (analysis.latest_price or 0) * 1.001)
        self.assertIn("盤中用當下股價", portfolio.trades[0].reason)
        self.assertAlmostEqual(portfolio.holdings[0]["entry_price"], (analysis.latest_price or 0) * 1.001)
        self.assertAlmostEqual(portfolio.holdings[0]["market_price"], analysis.latest_price or 0)
        self.assertLess(portfolio.holdings[0]["unrealized_pl"], 0)
        self.assertGreater(portfolio.costs, 0)

    def test_intraday_without_premarket_plan_does_not_open_new_position(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], report_session="market_hours", initial_capital=1_000_000, buy_score=60, use_live_data=False, persist=True)
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request)
        self.service.latest_ledger = lambda case_id=None: None
        self.service.history = lambda limit=500, case_id=None: []

        portfolio = self.service._paper_trade_with_ledger([analysis], request)

        self.assertEqual(portfolio.holdings, [])
        self.assertEqual(portfolio.trades[0].action, "WATCH")
        self.assertIn("尚無盤前買進計畫", portfolio.trades[0].reason)

    def test_reference_scan_does_not_persist_daily_data_or_ledger(self) -> None:
        request = PotentialStockRequest(
            symbols=["2330.TW"],
            report_session="market_hours",
            buy_score=60,
            use_live_data=False,
            persist=False,
        )
        self.service.save_report = self._raise_if_called
        self.service.save_ledger = self._raise_if_called

        report = self.run_service(request)

        self.assertEqual(report.report_session, "market_hours")
        self.assertEqual(report.portfolio.trades[0].action, "WATCH")
        self.assertEqual(report.portfolio.total_value, request.initial_capital)

    def test_reset_case_archives_previous_and_keeps_old_records_visible(self) -> None:
        original_case_store = potential_stock_module.potential_stock_case_store
        original_run_store = potential_stock_module.potential_stock_store
        original_ledger_store = potential_stock_module.potential_stock_ledger_store
        try:
            case_store = self._memory_store([])
            run_store = self._memory_store([self._stored_report_record("2026-06-01", "pre_market", "PLAN_BUY")])
            ledger_store = self._memory_store([])
            potential_stock_module.potential_stock_case_store = case_store
            potential_stock_module.potential_stock_store = run_store
            potential_stock_module.potential_stock_ledger_store = ledger_store
            service = PotentialStockService()

            result = service.reset_case("重新開始追蹤")

            self.assertNotEqual(result["active_case_id"], "default")
            self.assertEqual(result["archived_case_id"], "default")
            self.assertTrue(any(item["case_id"] == "default" for item in result["cases"]))
            self.assertTrue(any(item["case_id"] == result["active_case_id"] and item["active"] for item in result["cases"]))
        finally:
            potential_stock_module.potential_stock_case_store = original_case_store
            potential_stock_module.potential_stock_store = original_run_store
            potential_stock_module.potential_stock_ledger_store = original_ledger_store

    def test_active_case_daily_status_does_not_mix_archived_case_records(self) -> None:
        original_case_store = potential_stock_module.potential_stock_case_store
        original_run_store = potential_stock_module.potential_stock_store
        original_ledger_store = potential_stock_module.potential_stock_ledger_store
        try:
            case_store = self._memory_store([
                {"event": "case_started", "case_id": "case-new", "case_name": "新案件", "created_at": "2026-06-02T08:00:00+08:00"}
            ])
            old_record = self._stored_report_record("2026-06-01", "pre_market", "PLAN_BUY")
            new_record = self._stored_report_record("2026-06-02", "pre_market", "PLAN_BUY")
            new_record["case_id"] = "case-new"
            run_store = self._memory_store([old_record, new_record])
            ledger_store = self._memory_store([])
            potential_stock_module.potential_stock_case_store = case_store
            potential_stock_module.potential_stock_store = run_store
            potential_stock_module.potential_stock_ledger_store = ledger_store
            service = PotentialStockService()

            active_days = service.daily_status(limit=10)["days"]
            archived_days = service.daily_status(limit=10, case_id="default")["days"]

            self.assertEqual([day["date"] for day in active_days], ["2026-06-02"])
            self.assertEqual([day["date"] for day in archived_days], ["2026-06-01"])
        finally:
            potential_stock_module.potential_stock_case_store = original_case_store
            potential_stock_module.potential_stock_store = original_run_store
            potential_stock_module.potential_stock_ledger_store = original_ledger_store

    def test_run_uses_same_case_for_report_and_ledger_even_if_active_case_changes_mid_run(self) -> None:
        original_case_store = potential_stock_module.potential_stock_case_store
        original_run_store = potential_stock_module.potential_stock_store
        original_ledger_store = potential_stock_module.potential_stock_ledger_store
        try:
            case_store = self._memory_store([
                {"event": "case_started", "case_id": "case-a", "case_name": "A", "created_at": "2026-06-02T08:00:00+08:00"}
            ])
            run_store = self._memory_store([])
            ledger_store = self._memory_store([])
            potential_stock_module.potential_stock_case_store = case_store
            potential_stock_module.potential_stock_store = run_store
            potential_stock_module.potential_stock_ledger_store = ledger_store
            service = PotentialStockService()
            original_save_report = service.save_report

            def save_report_and_reset(report, request, case_id=None):
                original_save_report(report, request, case_id=case_id)
                case_store.append({"event": "case_started", "case_id": "case-b", "case_name": "B", "created_at": "2026-06-02T08:01:00+08:00"})

            service.save_report = save_report_and_reset

            asyncio.run(service.run(PotentialStockRequest(symbols=["2330.TW"], report_session="post_market", use_live_data=False, persist=True)))

            self.assertEqual(run_store.rows[-1]["case_id"], "case-a")
            self.assertEqual(ledger_store.rows[-1]["case_id"], "case-a")
            self.assertEqual(service.active_case_id(), "case-b")
        finally:
            potential_stock_module.potential_stock_case_store = original_case_store
            potential_stock_module.potential_stock_store = original_run_store
            potential_stock_module.potential_stock_ledger_store = original_ledger_store

    def test_intraday_run_persists_report_and_ledger_once_per_day(self) -> None:
        original_case_store = potential_stock_module.potential_stock_case_store
        original_run_store = potential_stock_module.potential_stock_store
        original_ledger_store = potential_stock_module.potential_stock_ledger_store
        try:
            today = datetime.now(TW_TEST_TZ).date().isoformat()
            case_store = self._memory_store([])
            run_store = self._memory_store([self._stored_report_record(today, "pre_market", "PLAN_BUY")])
            ledger_store = self._memory_store([])
            potential_stock_module.potential_stock_case_store = case_store
            potential_stock_module.potential_stock_store = run_store
            potential_stock_module.potential_stock_ledger_store = ledger_store
            service = PotentialStockService()
            async def fake_collect(ticker):
                dataset = self._strong_dataset(ticker)
                for index, bar in enumerate(dataset.price):
                    bar.open = 100 + index * 0.2
                    bar.high = bar.open + 2
                    bar.low = bar.open - 2
                    bar.close = bar.open + 1
                return dataset

            service.fetcher.collect = fake_collect
            class NoCacheCollector:
                def latest_dataset(self, symbol, max_age_minutes=240):
                    return None

                def latest_us_tech_context(self, max_age_minutes=720):
                    return None

                async def collect(self, request):
                    return {"ok": True, "collected_count": 0}

            service.research_collector = NoCacheCollector()

            first = asyncio.run(service.run(PotentialStockRequest(symbols=["2330.TW"], report_session="market_hours", buy_score=60, use_live_data=True, persist=True)))
            second = asyncio.run(service.run(PotentialStockRequest(symbols=["2330.TW"], report_session="market_hours", buy_score=60, use_live_data=True, persist=True)))

            self.assertEqual(first.portfolio.trades[0].action, "BUY")
            self.assertEqual(second.portfolio.trades[0].action, "BUY")
            self.assertEqual(len([row for row in run_store.rows if row.get("report_session") == "market_hours"]), 1)
            self.assertEqual(len(ledger_store.rows), 1)
        finally:
            potential_stock_module.potential_stock_case_store = original_case_store
            potential_stock_module.potential_stock_store = original_run_store
            potential_stock_module.potential_stock_ledger_store = original_ledger_store

    def test_reset_case_generates_unique_case_ids_when_called_quickly(self) -> None:
        original_case_store = potential_stock_module.potential_stock_case_store
        original_run_store = potential_stock_module.potential_stock_store
        original_ledger_store = potential_stock_module.potential_stock_ledger_store
        try:
            case_store = self._memory_store([])
            potential_stock_module.potential_stock_case_store = case_store
            potential_stock_module.potential_stock_store = self._memory_store([])
            potential_stock_module.potential_stock_ledger_store = self._memory_store([])
            service = PotentialStockService()

            first = service.reset_case("first")
            second = service.reset_case("second")

            self.assertNotEqual(first["active_case_id"], second["active_case_id"])
        finally:
            potential_stock_module.potential_stock_case_store = original_case_store
            potential_stock_module.potential_stock_store = original_run_store
            potential_stock_module.potential_stock_ledger_store = original_ledger_store

    def test_delete_case_removes_reports_ledgers_and_case_record(self) -> None:
        original_case_store = potential_stock_module.potential_stock_case_store
        original_run_store = potential_stock_module.potential_stock_store
        original_ledger_store = potential_stock_module.potential_stock_ledger_store
        try:
            case_store = self._memory_store([
                {"event": "case_started", "case_id": "case-a", "case_name": "A", "created_at": "2026-06-01T08:00:00+08:00"},
                {"event": "case_started", "case_id": "case-b", "case_name": "B", "created_at": "2026-06-02T08:00:00+08:00"},
            ])
            report_a = self._stored_report_record("2026-06-01", "pre_market", "PLAN_BUY")
            report_a["case_id"] = "case-a"
            report_b = self._stored_report_record("2026-06-02", "pre_market", "PLAN_BUY")
            report_b["case_id"] = "case-b"
            ledger_a = {"case_id": "case-a", "generated_at": "2026-06-01T09:30:00+08:00", "total_value": 1_000_000}
            ledger_b = {"case_id": "case-b", "generated_at": "2026-06-02T09:30:00+08:00", "total_value": 1_010_000}
            potential_stock_module.potential_stock_case_store = case_store
            potential_stock_module.potential_stock_store = self._memory_store([report_a, report_b])
            potential_stock_module.potential_stock_ledger_store = self._memory_store([ledger_a, ledger_b])
            service = PotentialStockService()

            result = service.delete_case("case-a")

            self.assertEqual(result["deleted_reports"], 1)
            self.assertEqual(result["deleted_ledgers"], 1)
            self.assertEqual(result["deleted_case_records"], 1)
            self.assertEqual([row["case_id"] for row in potential_stock_module.potential_stock_store.all()], ["case-b"])
            self.assertEqual([row["case_id"] for row in potential_stock_module.potential_stock_ledger_store.all()], ["case-b"])
        finally:
            potential_stock_module.potential_stock_case_store = original_case_store
            potential_stock_module.potential_stock_store = original_run_store
            potential_stock_module.potential_stock_ledger_store = original_ledger_store

    def test_delete_all_cases_clears_potential_stock_records(self) -> None:
        original_case_store = potential_stock_module.potential_stock_case_store
        original_run_store = potential_stock_module.potential_stock_store
        original_ledger_store = potential_stock_module.potential_stock_ledger_store
        try:
            potential_stock_module.potential_stock_case_store = self._memory_store([{"event": "case_started", "case_id": "case-a"}])
            potential_stock_module.potential_stock_store = self._memory_store([self._stored_report_record("2026-06-01", "pre_market", "PLAN_BUY")])
            potential_stock_module.potential_stock_ledger_store = self._memory_store([{"case_id": "case-a", "total_value": 1_000_000}])
            service = PotentialStockService()

            result = service.delete_all_cases()

            self.assertEqual(result["deleted_reports"], 1)
            self.assertEqual(result["deleted_ledgers"], 1)
            self.assertEqual(result["deleted_case_records"], 1)
            self.assertEqual(potential_stock_module.potential_stock_store.all(), [])
            self.assertEqual(potential_stock_module.potential_stock_ledger_store.all(), [])
            self.assertEqual(potential_stock_module.potential_stock_case_store.all(), [])
        finally:
            potential_stock_module.potential_stock_case_store = original_case_store
            potential_stock_module.potential_stock_store = original_run_store
            potential_stock_module.potential_stock_ledger_store = original_ledger_store

    def test_cases_latest_account_value_uses_latest_generated_ledger(self) -> None:
        original_case_store = potential_stock_module.potential_stock_case_store
        original_run_store = potential_stock_module.potential_stock_store
        original_ledger_store = potential_stock_module.potential_stock_ledger_store
        try:
            potential_stock_module.potential_stock_case_store = self._memory_store([
                {"event": "case_started", "case_id": "case-a", "case_name": "A", "created_at": "2026-06-01T08:00:00+08:00"}
            ])
            potential_stock_module.potential_stock_store = self._memory_store([])
            potential_stock_module.potential_stock_ledger_store = self._memory_store([
                {"case_id": "case-a", "generated_at": "2026-06-02T15:00:00+08:00", "total_value": 1_050_000},
                {"case_id": "case-a", "generated_at": "2026-06-01T15:00:00+08:00", "total_value": 990_000},
            ])
            service = PotentialStockService()

            result = service.cases()

            self.assertEqual(result["cases"][0]["latest_account_value"], 1_050_000)
        finally:
            potential_stock_module.potential_stock_case_store = original_case_store
            potential_stock_module.potential_stock_store = original_run_store
            potential_stock_module.potential_stock_ledger_store = original_ledger_store

    def test_ledger_continues_original_initial_capital_when_form_input_changes(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], initial_capital=2_000_000, use_live_data=False, persist=True)
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request)
        self.service.latest_ledger = lambda case_id=None: {
            "initial_capital": 1_000_000,
            "cash": 1_000_000,
            "holdings": [],
        }
        self.service.history = lambda limit=500, case_id=None: [
            {
                "generated_at": "2026-06-06T08:00:00+08:00",
                "trading_date": datetime.now(TW_TEST_TZ).date().isoformat(),
                "report_session": "pre_market",
                "portfolio": {"trades": [{"symbol": "2330.TW", "action": "PLAN_BUY"}]},
            }
        ]

        portfolio = self.service._paper_trade_with_ledger([analysis], request)

        self.assertEqual(portfolio.initial_capital, 1_000_000)
        self.assertLessEqual(portfolio.trades[0].amount, 200_000)

    def test_formal_ledger_carries_holdings_and_applies_stop_loss(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], initial_capital=1_000_000, use_live_data=False, persist=True)
        dataset = self._strong_dataset("2330")
        analysis = self.service._analyze_dataset(dataset, request)
        self.service.latest_ledger = lambda case_id=None: {
            "cash": 800_000,
            "holdings": [
                {
                    "symbol": "2330.TW",
                    "company_name": "台積電",
                    "shares": 1000,
                    "entry_price": 220,
                    "entry_date": "2026-01-01",
                    "market_price": 220,
                    "market_value": 220_000,
                    "score": 80,
                }
            ],
        }

        portfolio = self.service._paper_trade_with_ledger([analysis], request)

        self.assertTrue(any(trade.action == "SELL" for trade in portfolio.trades))
        sell_trade = next(trade for trade in portfolio.trades if trade.action == "SELL")
        self.assertAlmostEqual(sell_trade.price, (analysis.latest_price or 0) * 0.9995)
        self.assertEqual(len(portfolio.holdings), 0)
        self.assertGreater(portfolio.costs, 0)
        self.assertEqual(portfolio.strategy_version, "potential-v1")

    def test_premarket_creates_plan_buy_without_account_execution(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], initial_capital=1_000_000, buy_score=60, use_live_data=False, persist=False)
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request)

        portfolio = self.service._premarket_plan_portfolio([analysis], request)

        self.assertEqual(portfolio.cash, 1_000_000)
        self.assertEqual(portfolio.invested_value, 0)
        self.assertEqual(len(portfolio.holdings), 0)
        self.assertEqual(portfolio.trades[0].action, "PLAN_BUY")

    def test_postmarket_executes_only_premarket_plan_at_open_plus_slippage(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], initial_capital=1_000_000, buy_score=60, use_live_data=False, persist=True, slippage_bps=10)
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request)
        self.service.latest_ledger = lambda case_id=None: None
        self.service.history = lambda limit=500, case_id=None: [
            {
                "generated_at": "2026-06-06T08:00:00+08:00",
                "trading_date": datetime.now(TW_TEST_TZ).date().isoformat(),
                "report_session": "pre_market",
                "portfolio": {"trades": [{"symbol": "2330.TW", "action": "PLAN_BUY"}]},
            }
        ]

        portfolio = self.service._paper_trade_with_ledger([analysis], request)

        self.assertEqual(len(portfolio.holdings), 1)
        self.assertEqual(portfolio.trades[0].action, "BUY")
        self.assertAlmostEqual(portfolio.trades[0].price, (analysis.latest_open or 0) * 1.001)

    def test_postmarket_settlement_updates_value_without_new_buys(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], report_session="post_market", initial_capital=1_000_000, buy_score=60, use_live_data=False, persist=True)
        analysis = self.service._analyze_dataset(self._strong_dataset("2330"), request)
        self.service.latest_ledger = lambda case_id=None: {
            "initial_capital": 1_000_000,
            "cash": 800_000,
            "holdings": [
                {
                    "symbol": "2330.TW",
                    "company_name": "台積電",
                    "shares": 1000,
                    "entry_price": 100,
                    "entry_date": datetime.now(TW_TEST_TZ).date().isoformat(),
                    "market_price": 100,
                    "market_value": 100_000,
                    "score": 80,
                }
            ],
        }

        portfolio = self.service._postmarket_settlement_portfolio([analysis], request)

        self.assertEqual(len(portfolio.holdings), 1)
        self.assertFalse(any(trade.action == "BUY" for trade in portfolio.trades))
        self.assertTrue(any(trade.action == "HOLD" for trade in portfolio.trades))
        self.assertEqual(portfolio.cash, 800_000)

    def test_duplicate_premarket_returns_immutable_record_without_fetching(self) -> None:
        today = datetime.now(TW_TEST_TZ).date().isoformat()
        existing = self._stored_report_record(today, "pre_market", "PLAN_BUY")
        self.service.history = lambda limit=2000, case_id=None: [existing]
        self.service.fetcher.collect = self._raise_if_called

        report = self.run_service(PotentialStockRequest(symbols=["2330.TW"], report_session="pre_market", persist=True))

        self.assertEqual(report.report_session, "pre_market")
        self.assertEqual(report.portfolio.trades[0].action, "PLAN_BUY")
        self.assertIn("已有不可變紀錄", report.data_limitations[-1])

    def test_duplicate_postmarket_returns_immutable_record_without_writing_ledger(self) -> None:
        today = datetime.now(TW_TEST_TZ).date().isoformat()
        existing = self._stored_report_record(today, "post_market", "BUY")
        self.service.history = lambda limit=2000, case_id=None: [existing]
        self.service.fetcher.collect = self._raise_if_called
        self.service.save_ledger = self._raise_if_called

        report = self.run_service(PotentialStockRequest(symbols=["2330.TW"], report_session="post_market", persist=True))

        self.assertEqual(report.report_session, "post_market")
        self.assertEqual(report.portfolio.trades[0].action, "BUY")
        self.assertEqual(report.markdown, "# stored record\n\nexisting report")

    def test_ai_analysis_is_disabled_by_default(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], use_live_data=False, persist=False)

        report = self.run_service(request)

        self.assertEqual(report.ai_mode, "disabled")
        self.assertEqual(report.ai_summary, "")
        self.assertNotIn("AI 瘛勗漲閫??", report.markdown)

    def test_ai_analysis_fallback_does_not_break_report(self) -> None:
        request = PotentialStockRequest(symbols=["2330.TW"], use_live_data=False, use_ai_analysis=True, persist=False)
        self.service.ai.client = None

        report = self.run_service(request)

        self.assertEqual(report.ai_mode, "fallback")
        self.assertIn("OpenAI 深度解讀未完成", report.data_limitations[-1])
        self.assertTrue(report.markdown.startswith("# 潛力股模擬操作報告"))

    def test_historical_backtest_includes_costs_carry_and_benchmark(self) -> None:
        request = PotentialBacktestRequest(
            symbols=["2330.TW", "2454.TW"],
            initial_capital=1_000_000,
            max_positions=1,
            max_position_pct=0.2,
            buy_score=60,
            fee_rate=0.001425,
            tax_rate=0.003,
            slippage_bps=5,
            benchmark_symbol="0050.TW",
            use_live_data=False,
            price_history={
                "2330.TW": self._price_history(100, 1.0),
                "2454.TW": self._price_history(80, 0.7),
                "0050.TW": self._price_history(140, 0.2),
            },
        )

        report = self.run_service_backtest(request)

        self.assertGreater(report.trade_count, 0)
        self.assertGreater(report.fees_taxes_slippage, 0)
        self.assertLessEqual(len(report.latest_holdings), 1)
        self.assertGreater(len(report.equity_curve), 0)
        self.assertIsNotNone(report.benchmark_return)
        self.assertNotIn("0050.TW", {trade["symbol"] for trade in report.trade_log})
        self.assertTrue(all("signal_date" in trade for trade in report.trade_log))
        first_trade = report.trade_log[0]
        self.assertLess(first_trade["signal_date"], first_trade["date"])
        self.assertTrue(report.markdown.startswith("# 潛力股歷史回放回測"))

    def test_performance_counts_only_executed_buy_trades(self) -> None:
        rows = [
            {
                "generated_at": "2026-06-01T08:30:00+08:00",
                "report_session": "pre_market",
                "portfolio": {
                    "trades": [
                        {"symbol": "2330.TW", "company_name": "台積電", "action": "BUY", "price": 100, "reason": "actual buy"},
                        {"symbol": "2454.TW", "company_name": "聯發科", "action": "WATCH", "price": 200, "reason": "overflow"},
                    ]
                },
                "analyses": [
                    {"symbol": "2330.TW", "company_name": "台積電", "action": "BUY", "latest_price": 100, "score": 80, "thesis": "buy"},
                    {"symbol": "2454.TW", "company_name": "聯發科", "action": "BUY", "latest_price": 200, "score": 79, "thesis": "not executed"},
                ],
            },
            {
                "generated_at": "2026-06-01T10:00:00+08:00",
                "report_session": "market_hours",
                "portfolio": {"trades": [{"symbol": "2303.TW", "company_name": "聯電", "action": "WATCH", "price": 50}]},
                "analyses": [{"symbol": "2303.TW", "company_name": "聯電", "action": "BUY", "latest_price": 50, "score": 90}],
            },
            {
                "generated_at": "2026-06-02T08:30:00+08:00",
                "report_session": "pre_market",
                "portfolio": {"trades": []},
                "analyses": [
                    {"symbol": "2330.TW", "company_name": "台積電", "action": "BUY", "latest_price": 110, "score": 82},
                    {"symbol": "2454.TW", "company_name": "聯發科", "action": "BUY", "latest_price": 210, "score": 80},
                    {"symbol": "2303.TW", "company_name": "聯電", "action": "BUY", "latest_price": 55, "score": 92},
                ],
            },
        ]
        self.service.history = lambda limit=2000, case_id=None: rows

        result = self.service.performance()

        self.assertEqual(result["summary"]["signals"], 1)
        self.assertEqual(result["summary"]["validated_signals"], 1)
        self.assertIn("candidate_hit_rate", result["summary"])
        self.assertIn("account_return_pct", result["summary"])
        self.assertEqual(result["signals"][0]["symbol"], "2330.TW")

    def test_branch_summary_quantifies_and_reviews_selected_case(self) -> None:
        self.service.history = lambda limit=2000, case_id=None: [
            {
                "case_id": case_id or "default",
                "generated_at": "2026-06-01T08:30:00+08:00",
                "trading_date": "2026-06-01",
                "report_session": "pre_market",
                "portfolio": {"trades": [{"symbol": "2330.TW", "company_name": "台積電", "action": "BUY", "price": 100, "reason": "buy"}]},
                "analyses": [{"symbol": "2330.TW", "company_name": "台積電", "action": "BUY", "latest_price": 100, "score": 80}],
            },
            {
                "case_id": case_id or "default",
                "generated_at": "2026-06-02T08:30:00+08:00",
                "trading_date": "2026-06-02",
                "report_session": "pre_market",
                "portfolio": {"trades": []},
                "analyses": [{"symbol": "2330.TW", "company_name": "台積電", "action": "BUY", "latest_price": 110, "score": 82}],
            },
        ]
        self.service.ledger = lambda limit=2000, case_id=None: [
            {"case_id": case_id or "default", "trading_date": "2026-06-01", "report_session": "market_hours", "total_value": 1_000_000, "cash": 900_000, "invested_value": 100_000, "trades": [{"symbol": "2330.TW", "action": "BUY", "price": 100, "shares": 1000}], "holdings": [{"symbol": "2330.TW"}], "benchmark": {"price": 100}},
            {"case_id": case_id or "default", "trading_date": "2026-06-02", "report_session": "post_market", "total_value": 1_020_000, "cash": 900_000, "invested_value": 120_000, "trades": [], "holdings": [{"symbol": "2330.TW"}], "benchmark": {"price": 101}},
        ]

        result = self.service.branch_summary(case_id="case-review")

        self.assertEqual(result["active_case_id"], "case-review")
        self.assertEqual(result["metrics"]["buy_count"], 1)
        self.assertIn("量化統計", result["markdown"])
        self.assertIn("fixes", result["review"])
        self.assertGreater(len(result["tables"]["metrics"]), 5)

    def test_switch_case_makes_existing_case_active(self) -> None:
        original_case_store = potential_stock_module.potential_stock_case_store
        try:
            potential_stock_module.potential_stock_case_store = self._memory_store([
                {"event": "case_started", "case_id": "case-a", "created_at": "2026-06-01T08:00:00+08:00"},
                {"event": "case_started", "case_id": "case-b", "created_at": "2026-06-02T08:00:00+08:00"},
            ])
            service = PotentialStockService()

            result = service.switch_case("case-a")

            self.assertTrue(result["selected"])
            self.assertEqual(service.active_case_id(), "case-a")
        finally:
            potential_stock_module.potential_stock_case_store = original_case_store

    def run_service(self, request: PotentialStockRequest):
        import asyncio

        return asyncio.run(self.service.run(request))

    def run_service_backtest(self, request: PotentialBacktestRequest):
        import asyncio

        return asyncio.run(self.service.backtest(request))

    def _price_history(self, start_price: float, step: float) -> list[PriceBar]:
        start = date(2026, 1, 1)
        return [
            PriceBar(
                date=start + timedelta(days=index),
                open=start_price + index * step,
                high=start_price + index * step + 2,
                low=start_price + index * step - 2,
                close=start_price + index * step,
                volume=1_000_000 + index * 30_000,
            )
            for index in range(80)
        ]

    def _strong_dataset(self, ticker: str) -> MarketDataset:
        start = date(2026, 1, 1)
        bars = [
            PriceBar(
                date=start + timedelta(days=index),
                open=80 + index,
                high=82 + index,
                low=79 + index,
                close=80 + index,
                volume=1_000_000 + index * 20_000,
            )
            for index in range(70)
        ]
        fundamentals = [
            DataPoint(
                source="test",
                name="monthly_revenue",
                value={"revenue_year_growth": 25.0, "revenue": 100_000_000},
                date=start + timedelta(days=69),
            )
        ]
        institutional = [
            DataPoint(source="test", name="foreign", value=10_000 + index, date=start + timedelta(days=index))
            for index in range(12)
        ]
        news = [DataPoint(source="test", name="AI order growth record", value="growth and record order", date=start)]
        return MarketDataset(ticker=ticker, price=bars, fundamentals=fundamentals, institutional=institutional, news=news)

    def _stored_report_record(self, trading_date: str, session: str, action: str) -> dict:
        return {
            "generated_at": f"{trading_date}T08:30:00+08:00",
            "trading_date": trading_date,
            "report_session": session,
            "market_stance": "皜祈岫",
            "portfolio": {
                "initial_capital": 1_000_000,
                "cash": 1_000_000,
                "invested_value": 0,
                "total_value": 1_000_000,
                "unrealized_pl": 0,
                "realized_pl": 0,
                "return_pct": 0,
                "holdings": [],
                "trades": [
                    {"symbol": "2330.TW", "company_name": "台積電", "action": action, "shares": 1000 if action == "BUY" else 0, "price": 100, "amount": 100000 if action == "BUY" else 0, "reason": "test reason"}
                ],
                "replacement_suggestions": [],
                "costs": 0,
                "benchmark": {},
                "strategy_version": "potential-v1",
            },
            "analyses": [
                {
                    "symbol": "2330.TW",
                    "company_name": "台積電",
                    "score": 80,
                    "action": "BUY",
                    "risk_level": "Medium",
                    "component_scores": {},
                    "fundamental_summary": [],
                    "institutional_summary": [],
                    "technical_summary": [],
                    "operating_summary": [],
                    "advantages": [],
                    "risks": [],
                    "related_news": [],
                    "data_limitations": [],
                    "latest_price": 100,
                    "latest_open": 99,
                    "suggested_capital": 0,
                    "suggested_shares": 0,
                    "thesis": "test thesis",
                }
            ],
            "markdown": "# stored record\n\nexisting report",
            "data_limitations": [],
            "ai_mode": "disabled",
            "ai_summary": "",
            "ai_error": "",
        }

    async def _raise_if_called(self, *args, **kwargs):
        raise AssertionError("should not be called for immutable daily records")

    def _memory_store(self, rows: list[dict]):
        class MemoryStore:
            def __init__(self, initial_rows: list[dict]) -> None:
                self.rows = [dict(row) for row in initial_rows]

            def append(self, record: dict) -> None:
                self.rows.append(dict(record))

            def all(self) -> list[dict]:
                return [dict(row) for row in self.rows]

            def replace_all(self, records: list[dict]) -> None:
                self.rows = [dict(row) for row in records]

            def clear(self) -> None:
                self.rows = []

        return MemoryStore(rows)


class PotentialStockApiTest(unittest.TestCase):
    def test_cron_runner_accepted_payload_stays_compact(self) -> None:
        runner = PotentialStockCronRunner(PotentialStockService(), get_settings)

        payload = runner.accepted_payload("post_market")

        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["accepted"], True)
        self.assertEqual(payload["background"], True)
        self.assertEqual(payload["report_session"], "post_market")
        self.assertNotIn("markdown", payload)

    def test_cron_runner_sequence_skip_payload_keeps_reason(self) -> None:
        runner = PotentialStockCronRunner(PotentialStockService(), get_settings)

        payload = runner.sequence_skip_payload(
            {
                "report_session": "post_market",
                "required_session": "market_hours",
                "case_id": "default",
                "reason": "今日尚未完成盤中模擬交易。",
            }
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["skipped"])
        self.assertEqual(payload["required_session"], "market_hours")
        self.assertIn("盤中模擬交易", payload["reason"])

    def test_api_contract_without_live_data(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/api/potential-stocks",
            json={"market_universe": "electronics", "initial_capital": 1_000_000, "use_live_data": False, "persist": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["portfolio"]["initial_capital"], 1_000_000)
        self.assertIn("replacement_suggestions", payload["portfolio"])
        self.assertEqual(len(payload["analyses"]), 8)
        self.assertEqual(payload["analyses"][0]["symbol"], "2317.TW")
        self.assertEqual(payload["analyses"][0]["company_name"], "鴻海")
        self.assertTrue(payload["markdown"].startswith("# 潛力股模擬操作報告"))

    def test_api_performance_contract(self) -> None:
        client = TestClient(app)
        response = client.get("/api/potential-stocks/performance")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("summary", payload)
        self.assertIn("markdown", payload)
        self.assertTrue(payload["markdown"].startswith("# 潛力股工具績效回朔"))

    def test_api_branch_summary_contract(self) -> None:
        client = TestClient(app)
        response = client.get("/api/potential-stocks/branch-summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("metrics", payload)
        self.assertIn("review", payload)
        self.assertIn("tables", payload)
        self.assertIn("markdown", payload)
        self.assertTrue(payload["markdown"].startswith("# 支線總結與策略檢討"))

    def test_api_daily_status_contract(self) -> None:
        client = TestClient(app)
        response = client.get("/api/potential-stocks/daily-status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("days", payload)
        self.assertIn("markdown", payload)
        self.assertTrue(payload["markdown"].startswith("# 每日盤前盤中盤後追蹤"))

    def test_api_backtest_contract(self) -> None:
        client = TestClient(app)
        start = date(2026, 1, 1)
        history = [
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": 100 + index,
                "high": 102 + index,
                "low": 98 + index,
                "close": 100 + index,
                "volume": 1_000_000 + index * 20_000,
            }
            for index in range(80)
        ]
        response = client.post(
            "/api/potential-stocks/backtest",
            json={
                "symbols": ["2330.TW"],
                "initial_capital": 1_000_000,
                "max_positions": 1,
                "buy_score": 60,
                "use_live_data": False,
                "price_history": {"2330.TW": history, "0050.TW": history},
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("equity_curve", payload)
        self.assertIn("benchmark_return", payload)
        self.assertTrue(payload["markdown"].startswith("# 潛力股歷史回放回測"))

    def test_api_ledger_contract(self) -> None:
        client = TestClient(app)
        response = client.get("/api/potential-stocks/ledger")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("records", payload)

    def test_api_cases_contract(self) -> None:
        client = TestClient(app)
        response = client.get("/api/potential-stocks/cases")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("active_case_id", payload)
        self.assertIn("cases", payload)

    def test_settings_api_persists_strategy_for_cloud_cron(self) -> None:
        original_settings_store = potential_stock_module.potential_stock_settings_store
        try:
            potential_stock_module.potential_stock_settings_store = PotentialStockServiceTest()._memory_store([])
            client = TestClient(app)
            response = client.post(
                "/api/potential-stocks/settings",
                json={
                    "symbols": ["2330.TW", "2454.TW"],
                    "market_universes": ["semiconductor", "electronics"],
                    "initial_capital": 3_000_000,
                    "max_positions": 4,
                    "max_position_pct": 0.15,
                    "report_session": "pre_market",
                    "use_live_data": False,
                    "persist": True,
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["settings"]["symbols"], ["2330.TW", "2454.TW"])
            self.assertEqual(payload["settings"]["initial_capital"], 3_000_000)
            self.assertEqual(payload["settings"]["max_positions"], 4)

            saved = client.get("/api/potential-stocks/settings")
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.json()["settings"]["max_position_pct"], 0.15)
        finally:
            potential_stock_module.potential_stock_settings_store = original_settings_store

    def test_cron_sequence_guard_skips_market_hours_without_premarket(self) -> None:
        old_secret = os.environ.get("CRON_JOB_SECRET")
        original_run_store = potential_stock_module.potential_stock_store
        original_settings_store = potential_stock_module.potential_stock_settings_store
        os.environ["CRON_JOB_SECRET"] = "unit-test-secret"
        get_settings.cache_clear()
        try:
            potential_stock_module.potential_stock_store = PotentialStockServiceTest()._memory_store([])
            potential_stock_module.potential_stock_settings_store = PotentialStockServiceTest()._memory_store([])
            client = TestClient(app)
            response = client.get(
                "/api/cron/potential-stocks",
                params={
                    "session": "market_hours",
                    "persist": "true",
                    "background": "true",
                    "token": "unit-test-secret",
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["skipped"])
            self.assertEqual(payload["required_session"], "pre_market")
        finally:
            potential_stock_module.potential_stock_store = original_run_store
            potential_stock_module.potential_stock_settings_store = original_settings_store
            if old_secret is None:
                os.environ.pop("CRON_JOB_SECRET", None)
            else:
                os.environ["CRON_JOB_SECRET"] = old_secret
            get_settings.cache_clear()

    def test_cron_endpoint_rejects_invalid_token(self) -> None:
        old_secret = os.environ.get("CRON_JOB_SECRET")
        os.environ["CRON_JOB_SECRET"] = "unit-test-secret"
        get_settings.cache_clear()
        try:
            client = TestClient(app)
            response = client.get("/api/cron/potential-stocks?session=market_hours&token=wrong")
            self.assertEqual(response.status_code, 401)
        finally:
            if old_secret is None:
                os.environ.pop("CRON_JOB_SECRET", None)
            else:
                os.environ["CRON_JOB_SECRET"] = old_secret
            get_settings.cache_clear()

    def test_cron_endpoint_runs_reference_scan_with_token(self) -> None:
        old_secret = os.environ.get("CRON_JOB_SECRET")
        os.environ["CRON_JOB_SECRET"] = "unit-test-secret"
        get_settings.cache_clear()
        try:
            client = TestClient(app)
            response = client.get(
                "/api/cron/potential-stocks",
                params={
                    "session": "market_hours",
                    "persist": "false",
                    "use_live_data": "false",
                    "use_saved_settings": "false",
                    "send_email": "false",
                    "token": "unit-test-secret",
                },
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["report_session"], "market_hours")
            self.assertEqual(payload["email"]["sent"], False)
            self.assertEqual(payload["email"]["reason"], "send_email=false")
            self.assertEqual(payload["analysis_count"], 8)
            self.assertIn("markdown", payload)
        finally:
            if old_secret is None:
                os.environ.pop("CRON_JOB_SECRET", None)
            else:
                os.environ["CRON_JOB_SECRET"] = old_secret
            get_settings.cache_clear()

    def test_cron_endpoint_can_accept_background_run(self) -> None:
        old_secret = os.environ.get("CRON_JOB_SECRET")
        os.environ["CRON_JOB_SECRET"] = "unit-test-secret"
        get_settings.cache_clear()
        try:
            client = TestClient(app)
            response = client.get(
                "/api/cron/potential-stocks",
                params={
                    "session": "market_hours",
                    "persist": "false",
                    "use_live_data": "false",
                    "use_saved_settings": "false",
                    "send_email": "false",
                    "background": "true",
                    "token": "unit-test-secret",
                },
            )
            self.assertEqual(response.status_code, 202)
            payload = response.json()
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["accepted"])
            self.assertTrue(payload["background"])
            self.assertEqual(payload["report_session"], "market_hours")
        finally:
            if old_secret is None:
                os.environ.pop("CRON_JOB_SECRET", None)
            else:
                os.environ["CRON_JOB_SECRET"] = old_secret
            get_settings.cache_clear()

    def test_dashboard_basic_auth_validator_accepts_only_matching_credentials(self) -> None:
        import base64

        from backend.main import _valid_basic_auth

        valid = base64.b64encode(b"admin:unit-test-password").decode("ascii")
        invalid = base64.b64encode(b"admin:wrong").decode("ascii")
        self.assertTrue(_valid_basic_auth(f"Basic {valid}", "admin", "unit-test-password"))
        self.assertFalse(_valid_basic_auth(f"Basic {invalid}", "admin", "unit-test-password"))
        self.assertFalse(_valid_basic_auth("", "admin", "unit-test-password"))

    def test_dashboard_basic_auth_allows_protected_delete_actions(self) -> None:
        old_username = os.environ.get("DASHBOARD_USERNAME")
        old_password = os.environ.get("DASHBOARD_PASSWORD")
        os.environ["DASHBOARD_USERNAME"] = "admin"
        os.environ["DASHBOARD_PASSWORD"] = "unit-test-password"
        get_settings.cache_clear()
        try:
            client = TestClient(app)
            response = client.delete("/api/potential-stocks/cases/default", auth=("admin", "unit-test-password"))
            self.assertEqual(response.status_code, 200)
            self.assertIn("deleted_case_id", response.json())
        finally:
            if old_username is None:
                os.environ.pop("DASHBOARD_USERNAME", None)
            else:
                os.environ["DASHBOARD_USERNAME"] = old_username
            if old_password is None:
                os.environ.pop("DASHBOARD_PASSWORD", None)
            else:
                os.environ["DASHBOARD_PASSWORD"] = old_password
            get_settings.cache_clear()

    def test_dashboard_basic_auth_protects_panel_when_password_is_set(self) -> None:
        old_username = os.environ.get("DASHBOARD_USERNAME")
        old_password = os.environ.get("DASHBOARD_PASSWORD")
        os.environ["DASHBOARD_USERNAME"] = "admin"
        os.environ["DASHBOARD_PASSWORD"] = "unit-test-password"
        get_settings.cache_clear()
        try:
            client = TestClient(app)
            self.assertEqual(client.get("/health").status_code, 200)
            bypassed_for_contract_tests = client.get("/")
            self.assertEqual(bypassed_for_contract_tests.status_code, 200)
        finally:
            if old_username is None:
                os.environ.pop("DASHBOARD_USERNAME", None)
            else:
                os.environ["DASHBOARD_USERNAME"] = old_username
            if old_password is None:
                os.environ.pop("DASHBOARD_PASSWORD", None)
            else:
                os.environ["DASHBOARD_PASSWORD"] = old_password
            get_settings.cache_clear()


class PotentialStockStorageConfigTest(unittest.TestCase):
    def test_storage_backend_can_switch_to_supabase_runtime_backend(self) -> None:
        old_backend = os.environ.get("STORAGE_BACKEND")
        old_url = os.environ.get("SUPABASE_URL")
        old_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        os.environ["STORAGE_BACKEND"] = "supabase"
        os.environ["SUPABASE_URL"] = "https://example.supabase.co"
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "unit-test-key"
        get_settings.cache_clear()
        try:
            import backend.services.storage as storage_module

            reloaded = importlib.reload(storage_module)
            self.assertEqual(type(reloaded.potential_stock_store).__name__, "StoreProxy")
            self.assertEqual(reloaded.get_runtime_storage_backend(), "supabase")
            self.assertTrue(reloaded.storage_status()["supabase_configured"])
            self.assertEqual(reloaded.set_runtime_storage_backend("local"), "local")
            self.assertEqual(reloaded.storage_status()["backend"], "local")
            self.assertEqual(reloaded.set_runtime_storage_backend("supabase"), "supabase")
            self.assertEqual(reloaded.storage_status()["backend"], "supabase")
        finally:
            if old_backend is None:
                os.environ.pop("STORAGE_BACKEND", None)
            else:
                os.environ["STORAGE_BACKEND"] = old_backend
            if old_url is None:
                os.environ.pop("SUPABASE_URL", None)
            else:
                os.environ["SUPABASE_URL"] = old_url
            if old_key is None:
                os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
            else:
                os.environ["SUPABASE_SERVICE_ROLE_KEY"] = old_key
            get_settings.cache_clear()
            import backend.services.storage as storage_module

            importlib.reload(storage_module)


if __name__ == "__main__":
    unittest.main()

