from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field

from backend.models import MarketDataset
from backend.services.fetchers import MarketDataFetcher
from backend.services.storage import potential_stock_research_store


TW_TZ = timezone(timedelta(hours=8))
RESEARCH_BUNDLE_VERSION = "research-bundle-v1"


class ResearchCollectRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    include_us_tech: bool = True
    max_symbols: int = 30


class ResearchCollectorService:
    US_TECH_LEADERS = ["NVDA", "AMD", "AVGO", "TSM", "ASML", "AMAT", "LRCX", "KLAC", "MU", "QQQ", "SMH", "SOXX"]

    def __init__(self) -> None:
        self.fetcher = MarketDataFetcher()
        self._background_tasks: set[asyncio.Task] = set()

    def schedule(self, request: ResearchCollectRequest) -> None:
        task = asyncio.create_task(self._run_background(request))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _run_background(self, request: ResearchCollectRequest) -> None:
        try:
            await self.collect(request)
        except Exception as exc:  # noqa: BLE001
            print(f"Research collector background run failed: {exc}")

    async def collect(self, request: ResearchCollectRequest) -> dict[str, Any]:
        generated_at = datetime.now(TW_TZ)
        symbols = self._normalize_symbols(request.symbols)[: max(1, min(100, request.max_symbols or 30))]
        datasets: list[MarketDataset] = []
        errors: list[dict[str, str]] = []
        for symbol in symbols:
            try:
                dataset = await self.fetcher.collect(self._finmind_symbol(symbol))
                dataset.ticker = symbol
                datasets.append(dataset)
                potential_stock_research_store.append(self._dataset_record(dataset, generated_at))
            except Exception as exc:  # noqa: BLE001
                errors.append({"symbol": symbol, "error": str(exc)})

        us_tech_context: dict[str, Any] = {}
        if request.include_us_tech:
            try:
                rows = await self.fetcher.fetch_us_daily_returns(self.US_TECH_LEADERS)
                us_tech_context = self._us_tech_context(rows)
                potential_stock_research_store.append(
                    {
                        "event": "us_tech_context_collected",
                        "version": RESEARCH_BUNDLE_VERSION,
                        "generated_at": generated_at.isoformat(),
                        "context": us_tech_context,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"symbol": "US_TECH_CONTEXT", "error": str(exc)})

        return {
            "ok": True,
            "version": RESEARCH_BUNDLE_VERSION,
            "generated_at": generated_at.isoformat(),
            "symbol_count": len(symbols),
            "collected_count": len(datasets),
            "error_count": len(errors),
            "errors": errors[:10],
            "quality": [self._dataset_quality(item) for item in datasets],
            "us_tech_available": bool(us_tech_context.get("available")),
        }

    def latest_dataset(self, symbol: str, max_age_minutes: int = 240) -> MarketDataset | None:
        target = self._normalize_symbols([symbol])[0]
        cutoff = datetime.now(TW_TZ) - timedelta(minutes=max(1, max_age_minutes))
        rows = [
            row
            for row in potential_stock_research_store.all()
            if row.get("event") == "dataset_collected" and row.get("symbol") == target
        ]
        rows.sort(key=lambda item: str(item.get("generated_at") or ""))
        for row in reversed(rows):
            generated_at = self._parse_dt(row.get("generated_at"))
            if generated_at and generated_at < cutoff:
                continue
            try:
                return MarketDataset.model_validate(row.get("dataset") or {})
            except Exception:
                continue
        return None

    def latest_datasets(self, symbols: list[str], max_age_minutes: int = 240) -> tuple[list[MarketDataset], list[str]]:
        datasets: list[MarketDataset] = []
        missing: list[str] = []
        for symbol in self._normalize_symbols(symbols):
            dataset = self.latest_dataset(symbol, max_age_minutes=max_age_minutes)
            if dataset:
                datasets.append(dataset)
            else:
                missing.append(symbol)
        return datasets, missing

    def latest_us_tech_context(self, max_age_minutes: int = 720) -> dict[str, Any] | None:
        cutoff = datetime.now(TW_TZ) - timedelta(minutes=max(1, max_age_minutes))
        rows = [row for row in potential_stock_research_store.all() if row.get("event") == "us_tech_context_collected"]
        rows.sort(key=lambda item: str(item.get("generated_at") or ""))
        for row in reversed(rows):
            generated_at = self._parse_dt(row.get("generated_at"))
            if generated_at and generated_at < cutoff:
                continue
            context = row.get("context") or {}
            if context:
                return context
        return None

    def status(self, limit: int = 50) -> dict[str, Any]:
        rows = potential_stock_research_store.all()
        dataset_rows = [row for row in rows if row.get("event") == "dataset_collected"]
        dataset_rows.sort(key=lambda item: str(item.get("generated_at") or ""), reverse=True)
        latest_by_symbol: dict[str, dict[str, Any]] = {}
        for row in dataset_rows:
            symbol = str(row.get("symbol") or "")
            if symbol and symbol not in latest_by_symbol:
                latest_by_symbol[symbol] = row
        latest = list(latest_by_symbol.values())[:limit]
        return {
            "ok": True,
            "version": RESEARCH_BUNDLE_VERSION,
            "bundle_count": len(dataset_rows),
            "latest_symbols": [
                {
                    "symbol": row.get("symbol"),
                    "generated_at": row.get("generated_at"),
                    "quality": row.get("quality") or {},
                }
                for row in latest
            ],
            "us_tech_context_available": bool(self.latest_us_tech_context(max_age_minutes=10_080)),
        }

    def _dataset_record(self, dataset: MarketDataset, generated_at: datetime) -> dict[str, Any]:
        return {
            "event": "dataset_collected",
            "version": RESEARCH_BUNDLE_VERSION,
            "generated_at": generated_at.isoformat(),
            "symbol": self._normalize_symbols([dataset.ticker])[0],
            "dataset": dataset.model_dump(mode="json"),
            "quality": self._dataset_quality(dataset),
        }

    def _dataset_quality(self, dataset: MarketDataset) -> dict[str, Any]:
        return {
            "symbol": self._normalize_symbols([dataset.ticker])[0],
            "price_rows": len(dataset.price),
            "institutional_rows": len(dataset.institutional),
            "fundamental_rows": len(dataset.fundamentals),
            "news_rows": len([item for item in dataset.news if not item.missing]),
            "event_rows": len([item for item in dataset.events if not item.missing]),
            "official_rows": len([item for item in dataset.events if isinstance(item.value, dict) and str(item.value.get("tier") or "").startswith("official")]),
            "ir_rows": len([item for item in dataset.events if isinstance(item.value, dict) and str(item.value.get("tier") or "") in {"company_ir", "conference_material"}]),
            "supply_chain_rows": len([item for item in dataset.events if isinstance(item.value, dict) and str(item.value.get("tier") or "") == "supply_chain_search"]),
            "missing_count": len(dataset.limitations),
            "limitations": dataset.limitations[:5],
            "latest_price_date": str(dataset.price[-1].date) if dataset.price else "",
        }

    def _us_tech_context(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        returns = [float(row["return_pct"]) for row in rows if self._float_or_none(row.get("return_pct")) is not None]
        if not returns:
            return {"available": False, "rows": rows, "limitation": "US market leader returns unavailable."}
        semi_symbols = {"NVDA", "AMD", "AVGO", "TSM", "ASML", "AMAT", "LRCX", "KLAC", "MU", "SMH", "SOXX"}
        semi_returns = [float(row["return_pct"]) for row in rows if row.get("symbol") in semi_symbols and self._float_or_none(row.get("return_pct")) is not None]
        return {
            "available": True,
            "rows": rows,
            "average_return_pct": sum(returns) / len(returns),
            "positive_ratio": sum(1 for item in returns if item > 0) / len(returns),
            "semiconductor_return_pct": sum(semi_returns) / len(semi_returns) if semi_returns else sum(returns) / len(returns),
            "leader_count": len(returns),
            "source": "ResearchCollector/Yahoo Finance chart",
        }

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        cleaned: list[str] = []
        for symbol in symbols or []:
            value = str(symbol).strip().upper()
            if not value:
                continue
            if value.isdigit():
                value = f"{value}.TW"
            if "." not in value and value.isdigit():
                value = f"{value}.TW"
            if value not in cleaned:
                cleaned.append(value)
        return cleaned

    def _finmind_symbol(self, symbol: str) -> str:
        return symbol.split(".")[0] if symbol.endswith((".TW", ".TWO")) else symbol

    def _parse_dt(self, value: Any) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TW_TZ)
        return parsed.astimezone(TW_TZ)

    def _float_or_none(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
