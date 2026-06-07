from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from backend.models import PotentialStockRequest
from backend.services.potential_stock_service import PotentialStockService


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "scheduled_reports" / "potential_stocks"
TZ = timezone(timedelta(hours=8))


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _parse_symbols(raw: str) -> list[str]:
    for separator in [";", "\n", "\t", " "]:
        raw = raw.replace(separator, ",")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name, "true" if default else "false").lower()
    return value in {"1", "true", "yes", "y", "on"}


def _session_by_time() -> str:
    hour = datetime.now(TZ).hour
    if hour < 9:
        return "pre_market"
    if hour < 14:
        return "market_hours"
    return "post_market"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate potential-stock paper-trading report.")
    parser.add_argument("--symbols", default=_env("POTENTIAL_STOCK_SYMBOLS"))
    parser.add_argument("--market-universe", default=_env("POTENTIAL_STOCK_UNIVERSE", "semiconductor"))
    parser.add_argument("--initial-capital", type=float, default=float(_env("POTENTIAL_INITIAL_CAPITAL", "3000000")))
    parser.add_argument("--max-positions", type=int, default=int(_env("POTENTIAL_MAX_POSITIONS", "5")))
    parser.add_argument("--max-position-pct", type=float, default=float(_env("POTENTIAL_MAX_POSITION_PCT", "0.2")))
    parser.add_argument("--buy-score", type=int, default=int(_env("POTENTIAL_BUY_SCORE", "70")))
    parser.add_argument("--watch-score", type=int, default=int(_env("POTENTIAL_WATCH_SCORE", "55")))
    parser.add_argument("--sell-score", type=int, default=int(_env("POTENTIAL_SELL_SCORE", "50")))
    parser.add_argument("--stop-loss-pct", type=float, default=float(_env("POTENTIAL_STOP_LOSS_PCT", "0.08")))
    parser.add_argument("--take-profit-pct", type=float, default=float(_env("POTENTIAL_TAKE_PROFIT_PCT", "0.2")))
    parser.add_argument("--swap-score-gap", type=int, default=int(_env("POTENTIAL_SWAP_SCORE_GAP", "10")))
    parser.add_argument("--min-hold-days", type=int, default=int(_env("POTENTIAL_MIN_HOLD_DAYS", "3")))
    parser.add_argument("--strategy-version", default=_env("POTENTIAL_STRATEGY_VERSION", "potential-v1"))
    parser.add_argument("--risk-reward-profile", choices=["conservative", "balanced", "aggressive"], default=_env("POTENTIAL_RISK_REWARD_PROFILE", "balanced"))
    parser.add_argument("--investment-horizon", choices=["short_weeks", "mid_term_3m", "long_6m", "multi_year"], default=_env("POTENTIAL_INVESTMENT_HORIZON", "mid_term_3m"))
    parser.add_argument("--session", choices=["auto", "pre_market", "market_hours", "post_market"], default=_env("POTENTIAL_REPORT_SESSION") or _session_by_time())
    parser.add_argument("--use-ai-analysis", action="store_true", default=_env_bool("POTENTIAL_USE_AI_ANALYSIS"))
    parser.add_argument("--no-us-tech-leading", action="store_true", default=_env_bool("POTENTIAL_NO_US_TECH_LEADING"))
    parser.add_argument("--no-live-data", action="store_true")
    parser.add_argument("--no-persist", action="store_true", default=_env_bool("POTENTIAL_NO_PERSIST"))
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    service = PotentialStockService()
    request = PotentialStockRequest(
        symbols=_parse_symbols(args.symbols),
        market_universe=args.market_universe,
        initial_capital=args.initial_capital,
        max_positions=args.max_positions,
        max_position_pct=args.max_position_pct,
        buy_score=args.buy_score,
        watch_score=args.watch_score,
        sell_score=args.sell_score,
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
        swap_score_gap=args.swap_score_gap,
        min_hold_days=args.min_hold_days,
        strategy_version=args.strategy_version,
        risk_reward_profile=args.risk_reward_profile,
        investment_horizon=args.investment_horizon,
        report_session=args.session,
        use_live_data=not args.no_live_data,
        use_us_tech_leading=not args.no_us_tech_leading,
        use_ai_analysis=args.use_ai_analysis,
        persist=not args.no_persist,
    )
    report = await service.run(request)
    performance = service.performance()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    base = REPORT_DIR / f"{stamp}_{request.market_universe}_{request.report_session}"
    report_md = base.with_suffix(".md")
    report_json = base.with_suffix(".json")
    performance_md = base.with_name(base.name + "_performance").with_suffix(".md")
    performance_json = base.with_name(base.name + "_performance").with_suffix(".json")

    report_md.write_text(report.markdown, encoding="utf-8")
    report_json.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    performance_md.write_text(performance["markdown"], encoding="utf-8")
    performance_json.write_text(json.dumps(performance, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Potential-stock report written: {report_md}")
    print(f"Performance lookback written: {performance_md}")


if __name__ == "__main__":
    asyncio.run(main())
