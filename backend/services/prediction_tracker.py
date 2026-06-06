from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from backend.data_fetchers.stock_fetcher import fetch_stock_data


ROOT = Path(__file__).resolve().parents[2]
PREDICTIONS_FILE = ROOT / "data" / "predictions.jsonl"


def record_prediction(result: dict[str, Any]) -> dict[str, Any]:
    stock = result.get("market_data", {}).get("stock", {})
    scores = result.get("local_scores", {})
    revised = scores.get("revised_score", {})
    action = result.get("action_plan", {})
    truthfulness = result.get("truthfulness", {})
    record = {
        "prediction_id": f"{result.get('symbol')}-{result.get('timestamp')}",
        "symbol": result.get("symbol"),
        "mode": result.get("mode"),
        "analysis_time": result.get("timestamp"),
        "price": stock.get("close"),
        "price_data_date": result.get("data_freshness", {}).get("price_data_date"),
        "market_state": result.get("summary", {}).get("market_state"),
        "direction_score": revised.get("direction_score"),
        "timing_score": revised.get("timing_score"),
        "valuation_score": revised.get("valuation_score"),
        "risk_score": revised.get("risk_score"),
        "coverage_score": revised.get("data_coverage"),
        "truthfulness_score": revised.get("truthfulness_score") or truthfulness.get("truthfulness_score"),
        "overall_score": revised.get("overall_score") or scores.get("coverage_adjusted_score"),
        "recommendation": action.get("recommendation"),
        "sell_zone": action.get("sell_advice"),
        "buyback_zone": action.get("buy_advice"),
        "p0_missing_count": truthfulness.get("p0_missing_count"),
        "truthfulness_warnings": truthfulness.get("warnings", []),
        "validated": {},
    }
    PREDICTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PREDICTIONS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def validate_predictions() -> list[dict[str, Any]]:
    records = _read_records()
    validations: list[dict[str, Any]] = []
    for record in records:
        symbol = record.get("symbol")
        start_price = record.get("price")
        if not symbol or not start_price:
            continue
        try:
            analysis_time = datetime.fromisoformat(str(record.get("analysis_time")).replace("Z", "+00:00"))
        except Exception:
            continue
        stock = fetch_stock_data(symbol).get("data", {})
        history = stock.get("history") or stock.get("bars") or []
        for days, label in [(7, "7d"), (30, "30d"), (90, "90d")]:
            if datetime.now(analysis_time.tzinfo) < analysis_time + timedelta(days=days):
                continue
            window = [row for row in history if row.get("date") and row["date"] >= record.get("price_data_date", "")]
            if not window:
                validations.append(_empty_validation(record, label))
                continue
            end = window[min(len(window) - 1, days)]
            actual_return = (float(end["close"]) - float(start_price)) / float(start_price)
            max_drawdown = min((float(row["low"]) - float(start_price)) / float(start_price) for row in window[: days + 1])
            direction = record.get("direction_score") or 50
            correct = actual_return > 0 if direction >= 60 else actual_return < 0 if direction <= 40 else abs(actual_return) < 0.03
            validations.append(
                {
                    "prediction_id": record.get("prediction_id"),
                    "horizon": label,
                    "actual_return": round(actual_return, 4),
                    "max_drawdown": round(max_drawdown, 4),
                    "correct": correct,
                }
            )
    return validations


def _empty_validation(record: dict[str, Any], horizon: str) -> dict[str, Any]:
    return {"prediction_id": record.get("prediction_id"), "horizon": horizon, "actual_return": None, "max_drawdown": None, "correct": None}


def _read_records() -> list[dict[str, Any]]:
    if not PREDICTIONS_FILE.exists():
        return []
    rows = []
    for line in PREDICTIONS_FILE.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.validate:
        print(json.dumps(validate_predictions(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
