from __future__ import annotations

from datetime import date as Date, datetime as DateTime
from typing import Any, Literal
from pydantic import BaseModel, Field


MarketState = Literal["Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"]


class DataPoint(BaseModel):
    source: str
    name: str
    value: Any = None
    date: Date | None = None
    url: str | None = None
    missing: bool = False
    note: str = ""


class PriceBar(BaseModel):
    date: Date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    scfi: float | None = None
    foreign: float | None = None
    trust: float | None = None
    dividend: float = 0
    event: str = ""


class MarketDataset(BaseModel):
    ticker: str
    generated_at: DateTime = Field(default_factory=DateTime.utcnow)
    price: list[PriceBar] = Field(default_factory=list)
    institutional: list[DataPoint] = Field(default_factory=list)
    scfi: list[DataPoint] = Field(default_factory=list)
    fundamentals: list[DataPoint] = Field(default_factory=list)
    news: list[DataPoint] = Field(default_factory=list)
    events: list[DataPoint] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AlphaSignal(BaseModel):
    name: str
    direction: Literal["bullish", "bearish", "neutral"]
    strength: int = Field(ge=0, le=100)
    evidence: str
    source: str
    leading: bool = True


class AgentView(BaseModel):
    thesis: str
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class AlphaReport(BaseModel):
    ticker: str
    market_state: MarketState
    conviction_score: int = Field(ge=0, le=100)
    suggested_action: str
    estimated_range: str
    alpha_signals: list[AlphaSignal]
    bull_agent: AgentView
    bear_agent: AgentView
    market_mispricing: list[str]
    data_limitations: list[str]
    markdown: str
    raw_ai_text: str = ""


class PredictionRecord(BaseModel):
    date: Date
    ticker: str
    market_state: MarketState
    conviction_score: int
    suggested_action: str
    target_low: float | None = None
    target_high: float | None = None
    reasons: str = ""


class BacktestRequest(BaseModel):
    strategy: str = "evergreen_staged"
    initial_lots: float = 30
    core_lots: float = 20
    cost_basis: float = 192
    fee_rate: float = 0.001425
    tax_rate: float = 0.003
    price_bars: list[PriceBar] = Field(default_factory=list)
    predictions: list[PredictionRecord] = Field(default_factory=list)


class Trade(BaseModel):
    date: Date
    action: Literal["BUY", "SELL"]
    lots: float
    price: float
    cost: float
    reason: str


class BacktestReport(BaseModel):
    strategy: str
    total_return: float
    annualized_return: float
    max_drawdown: float
    win_rate: float | None
    trade_count: int
    fees_and_taxes: float
    buy_hold_return: float
    volatility_reduced: bool
    return_improved: bool
    trade_log: list[Trade]
    ai_accuracy: dict[str, Any]
    data_limitations: list[str]
    markdown: str


class ResearchRequest(BaseModel):
    ticker: str = "2603"
    use_live_data: bool = True
    manual_context: str = ""
    dataset: MarketDataset | None = None


class PotentialStockRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    market_universe: Literal["semiconductor", "electronics", "industrial", "financial", "custom"] = "semiconductor"
    market_universes: list[Literal["semiconductor", "electronics", "industrial", "financial", "custom"]] = Field(default_factory=list)
    initial_capital: float = 3_000_000
    max_positions: int = 5
    candidate_limit: int = 10
    max_position_pct: float = 0.2
    buy_score: int = 70
    watch_score: int = 55
    sell_score: int = 50
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.2
    swap_score_gap: int = 10
    min_hold_days: int = 3
    fee_rate: float = 0.001425
    tax_rate: float = 0.003
    slippage_bps: float = 5
    benchmark_symbol: str = "0050.TW"
    strategy_version: str = "potential-v1"
    risk_reward_profile: Literal["conservative", "balanced", "aggressive"] = "balanced"
    investment_horizon: Literal["short_weeks", "mid_term_3m", "long_6m", "multi_year"] = "mid_term_3m"
    report_session: Literal["auto", "pre_market", "market_hours", "post_market"] = "auto"
    use_live_data: bool = True
    use_saved_research: bool = True
    use_dynamic_universe: bool = True
    use_us_tech_leading: bool = True
    use_ai_analysis: bool = False
    persist: bool = True


class PotentialStockAnalysis(BaseModel):
    symbol: str
    company_name: str = ""
    score: int = Field(ge=0, le=100)
    action: Literal["BUY", "HOLD", "WATCH", "AVOID"]
    risk_level: Literal["Low", "Medium", "High"]
    component_scores: dict[str, int] = Field(default_factory=dict)
    fundamental_summary: list[str] = Field(default_factory=list)
    institutional_summary: list[str] = Field(default_factory=list)
    technical_summary: list[str] = Field(default_factory=list)
    operating_summary: list[str] = Field(default_factory=list)
    us_market_summary: list[str] = Field(default_factory=list)
    score_explanation: list[str] = Field(default_factory=list)
    news_impact_summary: list[str] = Field(default_factory=list)
    advantages: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    related_news: list[str] = Field(default_factory=list)
    evidence_links: list[dict[str, Any]] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)
    latest_price: float | None = None
    latest_open: float | None = None
    suggested_capital: float = 0
    suggested_shares: int = 0
    thesis: str = ""


class PaperTradeDecision(BaseModel):
    symbol: str
    company_name: str = ""
    action: Literal["PLAN_BUY", "BUY", "HOLD", "WATCH", "AVOID", "SELL"]
    shares: int = 0
    price: float | None = None
    amount: float = 0
    reason: str
    premarket_action: str = ""
    premarket_score: int | None = None
    intraday_score: int | None = None
    decision_change: str = ""
    decision_basis: str = ""


class PaperPortfolio(BaseModel):
    initial_capital: float
    cash: float
    invested_value: float
    total_value: float
    unrealized_pl: float
    realized_pl: float = 0
    return_pct: float
    holdings: list[dict[str, Any]] = Field(default_factory=list)
    trades: list[PaperTradeDecision] = Field(default_factory=list)
    replacement_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    costs: float = 0
    benchmark: dict[str, Any] = Field(default_factory=dict)
    strategy_version: str = "potential-v1"


class PotentialStockReport(BaseModel):
    generated_at: DateTime = Field(default_factory=DateTime.utcnow)
    report_session: Literal["pre_market", "market_hours", "post_market"]
    market_stance: str
    analyses: list[PotentialStockAnalysis]
    portfolio: PaperPortfolio
    markdown: str
    data_limitations: list[str] = Field(default_factory=list)
    ai_summary: str = ""
    ai_mode: Literal["disabled", "openai", "fallback"] = "disabled"
    ai_error: str = ""
    scan_universe_size: int = 0
    scan_universe_symbols: list[str] = Field(default_factory=list)
    selected_candidate_symbols: list[str] = Field(default_factory=list)


class PotentialBacktestRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    market_universe: Literal["semiconductor", "electronics", "industrial", "financial", "custom"] = "semiconductor"
    initial_capital: float = 1_000_000
    max_positions: int = 5
    max_position_pct: float = 0.2
    buy_score: int = 70
    fee_rate: float = 0.001425
    tax_rate: float = 0.003
    slippage_bps: float = 5
    benchmark_symbol: str = "0050.TW"
    risk_reward_profile: Literal["conservative", "balanced", "aggressive"] = "balanced"
    investment_horizon: Literal["short_weeks", "mid_term_3m", "long_6m", "multi_year"] = "mid_term_3m"
    use_live_data: bool = True
    price_history: dict[str, list[PriceBar]] = Field(default_factory=dict)


class PotentialBacktestReport(BaseModel):
    initial_capital: float
    final_value: float
    total_return: float
    benchmark_return: float | None = None
    excess_return: float | None = None
    max_drawdown: float
    trade_count: int
    fees_taxes_slippage: float
    latest_holdings: list[dict[str, Any]] = Field(default_factory=list)
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    trade_log: list[dict[str, Any]] = Field(default_factory=list)
    benchmark: dict[str, Any] = Field(default_factory=dict)
    data_limitations: list[str] = Field(default_factory=list)
    markdown: str
