from __future__ import annotations

from backend.models import AgentView, AlphaReport, AlphaSignal, MarketDataset
from backend.services.openai_service import OpenAIResearchService


class AlphaDiscoveryEngine:
    def __init__(self) -> None:
        self.ai = OpenAIResearchService()

    async def run(self, dataset: MarketDataset, manual_context: str = "") -> AlphaReport:
        ai = await self.ai.analyze(dataset, manual_context)
        raw_signals = ai.get("alpha_signals", [])
        if not isinstance(raw_signals, list):
            raw_signals = [raw_signals]
        signals = [self._signal(item) for item in raw_signals]
        state = self._market_state(ai.get("market_state"))
        conviction = int(ai.get("conviction_score") or self._score(signals, dataset))
        report = AlphaReport(
            ticker=dataset.ticker,
            market_state=state,
            conviction_score=max(0, min(100, conviction)),
            suggested_action=ai.get("suggested_action") or "Observe",
            estimated_range=ai.get("estimated_range") or "Data Missing",
            alpha_signals=signals,
            bull_agent=AgentView(
                thesis=ai.get("bull_thesis") or "Data Missing",
                evidence=[s.evidence for s in signals if s.direction == "bullish"],
            ),
            bear_agent=AgentView(
                thesis=ai.get("bear_thesis") or "Data Missing",
                evidence=[s.evidence for s in signals if s.direction == "bearish"],
                risks=ai.get("risks") or [],
            ),
            market_mispricing=ai.get("mispricing") or ["Data Missing"],
            data_limitations=dataset.limitations + list(ai.get("risks") or []),
            markdown=ai.get("markdown") or "",
            raw_ai_text=ai.get("raw_ai_text") or "",
        )
        if not report.markdown:
            report.markdown = self._markdown(report)
        return report

    def _market_state(self, raw: str | None) -> str:
        allowed = {"Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"}
        if raw in allowed:
            return raw
        if raw in {"Neutral-Bullish", "Neutral-Bullish / 中性偏多", "中性偏多", "Insufficient Data", "Insufficient Data / 資料不足"}:
            return "Neutral"
        return "Neutral"

    def _signal(self, raw: dict | str | None) -> AlphaSignal:
        if not isinstance(raw, dict):
            text = str(raw or "Data Missing")
            return AlphaSignal(
                name="Unstructured alpha signal",
                direction="neutral",
                strength=0,
                evidence=text,
                source="AI output",
                leading=False,
            )
        return AlphaSignal(
            name=str(raw.get("name") or "Unnamed signal"),
            direction=raw.get("direction") if raw.get("direction") in {"bullish", "bearish", "neutral"} else "neutral",
            strength=max(0, min(100, int(raw.get("strength") or 0))),
            evidence=str(raw.get("evidence") or "Data Missing"),
            source=str(raw.get("source") or "Data Missing"),
            leading=bool(raw.get("leading", True)),
        )

    def _score(self, signals: list[AlphaSignal], dataset: MarketDataset) -> int:
        score = 50
        for signal in signals:
            weight = signal.strength / 10
            score += weight if signal.direction == "bullish" else -weight if signal.direction == "bearish" else 0
        score -= len(dataset.limitations) * 4
        if dataset.scfi and dataset.scfi[0].missing:
            score -= 8
        if dataset.news and dataset.news[0].missing:
            score -= 4
        return int(max(0, min(100, score)))

    def _markdown(self, report: AlphaReport) -> str:
        def bullets(items: list[str]) -> str:
            return "\n".join(f"- {item}" for item in items) if items else "- Data Missing"

        signal_lines = [
            f"{s.name}: {s.evidence} ({s.direction}, strength {s.strength}, source: {s.source})"
            for s in report.alpha_signals
        ]
        return f"""# AI Alpha Research Report（AI Alpha 研究報告）

## Executive Summary（重點摘要）
- Ticker（股票代號）：{report.ticker}
- Market State（市場狀態）：{report.market_state}
- Conviction Score（信心分數）：{report.conviction_score}/100
- Suggested Action（建議動作）：{report.suggested_action}
- Estimated Range（預估區間）：{report.estimated_range}

## Alpha Discovery（Alpha 訊號）
{bullets(signal_lines)}

## Bull Agent（多方論點）
{report.bull_agent.thesis}

## Bear Agent（空方論點）
{report.bear_agent.thesis}

## Market Mispricing（市場可能錯估）
{bullets(report.market_mispricing)}

## Data Limitations（資料限制）
{bullets(report.data_limitations)}

## Disclaimer（免責聲明）
這不是投資建議，只是研究與輔助決策資訊；資料缺漏或推論資料不得作為強結論。"""
