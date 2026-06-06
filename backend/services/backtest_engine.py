from __future__ import annotations

from datetime import date, timedelta
from statistics import pstdev
from typing import Any

from backend.models import BacktestReport, BacktestRequest, PriceBar, Trade


class BacktestEngine:
    def run(self, request: BacktestRequest) -> BacktestReport:
        bars = sorted(request.price_bars, key=lambda item: item.date)
        limitations: list[str] = []
        if not bars:
            limitations.append("Data Missing: OHLCV history required.")
            return self._empty(request, limitations)
        if any(bar.scfi is None for bar in bars):
            limitations.append("Data Missing: SCFI history incomplete.")
        if any(bar.foreign is None or bar.trust is None for bar in bars):
            limitations.append("Data Missing: institutional flow incomplete.")
        if all(bar.dividend == 0 for bar in bars):
            limitations.append("Data Missing: dividend/ex-dividend data missing or zero.")

        strategy = self._simulate_strategy(request, bars)
        buy_hold = self._simulate_buy_hold(request, bars)
        ai_accuracy = self._prediction_accuracy(request, bars)
        markdown = self._markdown(request, strategy, buy_hold, ai_accuracy, limitations)
        return BacktestReport(
            strategy=request.strategy,
            total_return=strategy["total_return"],
            annualized_return=strategy["annualized_return"],
            max_drawdown=strategy["max_drawdown"],
            win_rate=strategy["win_rate"],
            trade_count=len(strategy["trades"]),
            fees_and_taxes=strategy["costs"],
            buy_hold_return=buy_hold["total_return"],
            volatility_reduced=strategy["volatility"] < buy_hold["volatility"],
            return_improved=strategy["total_return"] > buy_hold["total_return"],
            trade_log=strategy["trades"],
            ai_accuracy=ai_accuracy,
            data_limitations=limitations,
            markdown=markdown,
        )

    def _simulate_strategy(self, request: BacktestRequest, bars: list[PriceBar]) -> dict[str, Any]:
        cash = 0.0
        lots = request.initial_lots
        trades: list[Trade] = []
        equity: list[float] = []
        sold250 = sold260 = sold270 = weak_reduced = False

        def sell(bar: PriceBar, sell_lots: float, price: float, reason: str) -> None:
            nonlocal cash, lots
            sell_lots = min(sell_lots, max(0, lots - request.core_lots))
            if sell_lots <= 0:
                return
            gross = sell_lots * 1000 * price
            cost = gross * (request.fee_rate + request.tax_rate)
            cash += gross - cost
            lots -= sell_lots
            trades.append(Trade(date=bar.date, action="SELL", lots=sell_lots, price=price, cost=cost, reason=reason))

        def buy(bar: PriceBar, buy_lots: float, price: float, reason: str) -> None:
            nonlocal cash, lots
            buy_lots = min(buy_lots, max(0, request.initial_lots - lots))
            if buy_lots <= 0:
                return
            gross = buy_lots * 1000 * price
            cost = gross * request.fee_rate
            cash -= gross + cost
            lots += buy_lots
            trades.append(Trade(date=bar.date, action="BUY", lots=buy_lots, price=price, cost=cost, reason=reason))

        for index, bar in enumerate(bars):
            scfi_weak = self._scfi_weak(bars, index)
            institution_weak = self._institution_weak(bars, index)
            ma20 = self._ma(bars, index, 20)
            ma60 = self._ma(bars, index, 60)

            if request.strategy in {"evergreen_staged", "price_range"}:
                if not sold250 and bar.high >= 250:
                    sell(bar, 3, 250, "250 sell 3 lots")
                    sold250 = True
                if not sold260 and bar.high >= 260:
                    sell(bar, 3, 260, "260 sell 3 lots")
                    sold260 = True
                if not sold270 and bar.high >= 270:
                    sell(bar, 4, 270, "270 sell 4 lots")
                    sold270 = True
                if bar.low <= 230 < bar.high:
                    buy(bar, 10, min(230, bar.close), "220-230 buyback")
            if request.strategy in {"evergreen_staged", "scfi_weak"} and scfi_weak and not weak_reduced:
                sell(bar, 3, bar.close, "SCFI down 3 periods")
                weak_reduced = True
            if request.strategy in {"evergreen_staged", "institution_weak"} and institution_weak and not weak_reduced:
                sell(bar, 3, bar.close, "foreign selling and trust weakening")
                weak_reduced = True
            if request.strategy == "moving_average" and ma20 and ma60:
                if bar.close < ma20 < ma60:
                    sell(bar, 5, bar.close, "price below 20MA and 20MA below 60MA")
                elif bar.close > ma20 > ma60:
                    buy(bar, 5, bar.close, "trend recovery")

            equity.append(cash + lots * 1000 * bar.close)
        return self._metrics(equity, trades, request.initial_lots * 1000 * request.cost_basis, bars)

    def _simulate_buy_hold(self, request: BacktestRequest, bars: list[PriceBar]) -> dict[str, Any]:
        equity = [request.initial_lots * 1000 * bar.close for bar in bars]
        return self._metrics(equity, [], request.initial_lots * 1000 * request.cost_basis, bars)

    def _metrics(self, equity: list[float], trades: list[Trade], initial: float, bars: list[PriceBar]) -> dict[str, Any]:
        final = equity[-1]
        total = (final - initial) / initial
        days = max(1, (bars[-1].date - bars[0].date).days)
        annualized = (1 + total) ** (365 / days) - 1
        peak = equity[0]
        max_dd = 0.0
        for value in equity:
            peak = max(peak, value)
            max_dd = min(max_dd, (value - peak) / peak)
        returns = [(equity[i] - equity[i - 1]) / equity[i - 1] for i in range(1, len(equity))]
        volatility = pstdev(returns) * (252 ** 0.5) if len(returns) > 1 else 0.0
        wins = [trade for trade in trades if trade.action == "SELL" and trade.price > initial / max(1, trades[0].lots * 1000 if trades else 1000)]
        return {
            "total_return": total,
            "annualized_return": annualized,
            "max_drawdown": max_dd,
            "win_rate": len(wins) / len(trades) if trades else None,
            "trades": trades,
            "costs": sum(trade.cost for trade in trades),
            "volatility": volatility,
            "final": final,
        }

    def _prediction_accuracy(self, request: BacktestRequest, bars: list[PriceBar]) -> dict[str, Any]:
        validations: list[dict[str, Any]] = []
        for prediction in request.predictions:
            start = next((i for i, bar in enumerate(bars) if bar.date >= prediction.date), None)
            if start is None:
                continue
            for horizon in (7, 30, 90):
                target_date = bars[start].date + timedelta(days=horizon)
                end = next((i for i, bar in enumerate(bars) if i > start and bar.date >= target_date), None)
                if end is None:
                    continue
                window = bars[start : end + 1]
                start_close = bars[start].close
                end_close = bars[end].close
                actual_return = (end_close - start_close) / start_close
                max_drawdown = min((bar.low - start_close) / start_close for bar in window)
                hit_range = None
                if prediction.target_low is not None and prediction.target_high is not None:
                    hit_range = any(bar.high >= prediction.target_low and bar.low <= prediction.target_high for bar in window)
                bullish = "Bullish" in prediction.market_state
                bearish = "Bearish" in prediction.market_state
                correct = actual_return > 0 if bullish else actual_return < 0 if bearish else abs(actual_return) < 0.03
                validations.append(
                    {
                        "date": prediction.date.isoformat(),
                        "horizon": horizon,
                        "state": prediction.market_state,
                        "score": prediction.conviction_score,
                        "actual_return": actual_return,
                        "hit_range": hit_range,
                        "max_drawdown": max_drawdown,
                        "correct": correct,
                    }
                )
        return {
            "validations": validations,
            "bullish_win_rate": self._rate([v for v in validations if "Bullish" in v["state"]]),
            "bearish_win_rate": self._rate([v for v in validations if "Bearish" in v["state"]]),
            "average_return": sum(v["actual_return"] for v in validations) / len(validations) if validations else None,
            "bias": self._bias(validations),
        }

    def _markdown(self, request: BacktestRequest, strategy: dict[str, Any], buy_hold: dict[str, Any], ai_accuracy: dict[str, Any], limitations: list[str]) -> str:
        def p(value: float | None) -> str:
            return "Data Missing" if value is None else f"{value * 100:.2f}%"

        trades = "\n".join(f"- {t.date} {t.action} {t.lots} lots @ {t.price}: {t.reason}" for t in strategy["trades"]) or "- No trades."
        validations = "\n".join(
            f"- {v['date']} {v['horizon']}D {v['state']} score {v['score']}: return {p(v['actual_return'])}, hit_range={v['hit_range']}, max_dd={p(v['max_drawdown'])}, correct={v['correct']}"
            for v in ai_accuracy["validations"]
        ) or "- Data Missing: no valid prediction records."
        limits = "\n".join(f"- {item}" for item in limitations) or "- No major missing fields detected."
        return f"""# 回測報告（Backtest Report）

## 策略摘要（Strategy Summary）
策略（Strategy）：{request.strategy}
初始張數（Initial lots）：{request.initial_lots}
核心張數（Core lots）：{request.core_lots}

## 績效表現（Performance）
- 總報酬（Total return）：{p(strategy['total_return'])}
- 年化報酬（Annualized return）：{p(strategy['annualized_return'])}
- 最大回撤（Max drawdown）：{p(strategy['max_drawdown'])}
- 勝率（Win rate）：{p(strategy['win_rate'])}
- 稅費與手續費（Trading fees and taxes）：{strategy['costs']:.0f}

## 與買進持有比較（Compare with Buy and Hold）
- 買進持有報酬（Buy and Hold return）：{p(buy_hold['total_return'])}
- 是否提高報酬（Return improved）：{strategy['total_return'] > buy_hold['total_return']}
- 是否降低波動（Volatility reduced）：{strategy['volatility'] < buy_hold['volatility']}

## 回撤分析（Drawdown Analysis）
策略最大回撤（Strategy max drawdown）為 {p(strategy['max_drawdown'])}；買進持有最大回撤（Buy and Hold max drawdown）為 {p(buy_hold['max_drawdown'])}。

## 交易紀錄（Trade Log）
{trades}

## AI 預測準確率（AI Prediction Accuracy）
- 偏多勝率（Bullish win rate）：{p(ai_accuracy['bullish_win_rate'])}
- 偏空勝率（Bearish win rate）：{p(ai_accuracy['bearish_win_rate'])}
- 平均報酬（Average return）：{p(ai_accuracy['average_return'])}
- 偏誤（Bias）：{ai_accuracy['bias']}

## AI 預測驗證紀錄（AI Prediction Validation Log）
{validations}

## 弱點（Weaknesses）
- Missing SCFI/institutional/dividend data weakens conclusions.
- Range strategies can underperform in strong trend markets.

## 建議改進（Recommended Improvements）
- Persist daily predictions and validate them after 7, 30, and 90 days.
- Add slippage, tax lots, dividends, and event labels.

## 資料限制（Data Limitations）
{limits}

## 免責聲明（Disclaimer）
回測不能保證未來報酬。
"""

    def _scfi_weak(self, bars: list[PriceBar], index: int) -> bool:
        if index < 3:
            return False
        values = [bar.scfi for bar in bars[index - 3 : index + 1]]
        return all(value is not None for value in values) and values[3] < values[2] < values[1] < values[0]

    def _institution_weak(self, bars: list[PriceBar], index: int) -> bool:
        if index < 2:
            return False
        rows = bars[index - 2 : index + 1]
        return all(row.foreign is not None and row.trust is not None for row in rows) and all(row.foreign < 0 for row in rows) and rows[-1].trust < rows[-2].trust

    def _ma(self, bars: list[PriceBar], index: int, window: int) -> float | None:
        if index + 1 < window:
            return None
        return sum(bar.close for bar in bars[index + 1 - window : index + 1]) / window

    def _rate(self, rows: list[dict[str, Any]]) -> float | None:
        return sum(1 for row in rows if row["correct"]) / len(rows) if rows else None

    def _bias(self, validations: list[dict[str, Any]]) -> str:
        if not validations:
            return "Data Missing"
        avg = sum(v["actual_return"] for v in validations) / len(validations)
        if avg < -0.03:
            return "AI may be overly optimistic."
        if avg > 0.03:
            return "AI may be overly pessimistic or too conservative."
        return "No strong optimism/pessimism bias detected."

    def _empty(self, request: BacktestRequest, limitations: list[str]) -> BacktestReport:
        return BacktestReport(
            strategy=request.strategy,
            total_return=0,
            annualized_return=0,
            max_drawdown=0,
            win_rate=None,
            trade_count=0,
            fees_and_taxes=0,
            buy_hold_return=0,
            volatility_reduced=False,
            return_improved=False,
            trade_log=[],
            ai_accuracy={"validations": [], "bias": "Data Missing"},
            data_limitations=limitations,
            markdown="# 回測報告（Backtest Report）\n\n資料缺漏（Data Missing）：需要 OHLCV 歷史資料。",
        )
