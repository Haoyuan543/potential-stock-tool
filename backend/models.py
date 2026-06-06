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
