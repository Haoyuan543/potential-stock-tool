from __future__ import annotations

import json
from openai import AsyncOpenAI

from backend.config import get_settings
from backend.models import MarketDataset


SYSTEM_PROMPT = """You are an AI investment research analyst.
Do not summarize news. Find market mispricing, ignored signals, leading indicators,
divergences, and wrong expectations. Always mark Data Missing when evidence is absent.
Be conservative: missing or stale freight, institutional, market regime, or event data must reduce confidence.
Do not output Bullish unless evidence quality is high and risks are not elevated.
Return concise JSON with keys:
market_state, conviction_score, suggested_action, estimated_range, alpha_signals,
bull_thesis, bear_thesis, mispricing, risks, markdown.
"""


class OpenAIResearchService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None

    async def analyze(self, dataset: MarketDataset, manual_context: str = "") -> dict:
        if not self.client:
            return self._offline_analysis(dataset, manual_context)

        payload = {
            "ticker": dataset.ticker,
            "data": dataset.model_dump(mode="json"),
            "manual_context": manual_context,
        }
        response = await self.client.responses.create(
            model=self.settings.openai_model,
            instructions=SYSTEM_PROMPT,
            input=json.dumps(payload, ensure_ascii=False),
        )
        text = response.output_text
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = self._offline_analysis(dataset, manual_context)
            parsed["raw_ai_text"] = text
        return parsed

    def _offline_analysis(self, dataset: MarketDataset, manual_context: str = "") -> dict:
        latest = dataset.price[-1] if dataset.price else None
        prev = dataset.price[-21] if len(dataset.price) > 21 else None
        momentum = ((latest.close - prev.close) / prev.close) if latest and prev else 0
        score = 50 + int(momentum * 100)
        coverage_penalty = 0
        if dataset.limitations:
            coverage_penalty += min(20, len(dataset.limitations) * 4)
        if dataset.scfi and not dataset.scfi[0].missing:
            score += 5
        else:
            coverage_penalty += 8
        if dataset.news and not dataset.news[0].missing:
            score += 3
        else:
            coverage_penalty += 4
        score = max(0, min(100, score - coverage_penalty))
        state = "Bullish" if score >= 70 and coverage_penalty <= 8 else "Bearish" if score <= 35 else "Neutral"
        action = "Observe; insufficient evidence for aggressive action." if coverage_penalty else "Observe"
        return {
            "market_state": state,
            "conviction_score": score,
            "suggested_action": action,
            "estimated_range": "Data Missing" if not latest else f"{latest.close * 0.9:.2f}-{latest.close * 1.15:.2f}",
            "alpha_signals": [
                {
                    "name": "Price momentum",
                    "direction": "bullish" if momentum > 0 else "bearish" if momentum < 0 else "neutral",
                    "strength": min(100, abs(int(momentum * 100))),
                    "evidence": "Derived from latest close vs 20 trading days ago.",
                    "source": "FinMind/TaiwanStockPrice",
                    "leading": False,
                }
            ],
            "bull_thesis": "Potential upside if freight rates, institutional flows, and revenue improve together.",
            "bear_thesis": "Risk rises if SCFI weakens, foreign investors sell, or Red Sea normalization increases effective capacity.",
            "mispricing": [manual_context or "Data Missing: no manual market-mispricing context provided."],
            "risks": dataset.limitations,
            "markdown": "",
            "raw_ai_text": "",
        }
