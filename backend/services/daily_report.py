from __future__ import annotations

from datetime import date

from backend.models import AlphaReport, MarketDataset, PredictionRecord
from backend.services.storage import prediction_store, report_store


class DailyReportService:
    def save(self, dataset: MarketDataset, report: AlphaReport) -> PredictionRecord:
        prediction = PredictionRecord(
            date=date.today(),
            ticker=report.ticker,
            market_state=report.market_state,
            conviction_score=report.conviction_score,
            suggested_action=report.suggested_action,
            reasons="; ".join(signal.evidence for signal in report.alpha_signals[:3]),
        )
        prediction_store.append(prediction.model_dump(mode="json"))
        report_store.append(
            {
                "date": date.today().isoformat(),
                "ticker": report.ticker,
                "dataset_generated_at": dataset.generated_at.isoformat(),
                "market_state": report.market_state,
                "conviction_score": report.conviction_score,
                "markdown": report.markdown,
                "data_limitations": report.data_limitations,
            }
        )
        return prediction

    def latest(self) -> list[dict]:
        return report_store.all()[-30:]

    def predictions(self) -> list[dict]:
        return prediction_store.all()

