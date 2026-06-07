from __future__ import annotations

from datetime import date, timedelta
from typing import Any
import httpx

from backend.config import get_settings
from backend.models import DataPoint, MarketDataset, PriceBar


class MarketDataFetcher:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def collect(self, ticker: str) -> MarketDataset:
        dataset = MarketDataset(ticker=ticker)
        async with httpx.AsyncClient(timeout=self.settings.request_timeout) as client:
            dataset.price = await self.fetch_finmind_prices(client, ticker)
            dataset.institutional = await self.fetch_finmind_institutional(client, ticker)
            dataset.scfi = await self.fetch_scfi(client)
            dataset.fundamentals = await self.fetch_fundamentals(client, ticker)
            dataset.news = await self.fetch_news(client, ticker)

        if not dataset.price:
            dataset.limitations.append("Data Missing: price OHLCV history unavailable.")
        if not dataset.institutional:
            dataset.limitations.append("Data Missing: institutional buy/sell history unavailable.")
        if not dataset.scfi:
            dataset.limitations.append("Data Missing: SCFI route-level history unavailable or requires subscription/source upload.")
        if not dataset.fundamentals:
            dataset.limitations.append("Data Missing: monthly revenue/fundamental data unavailable.")
        if not dataset.news:
            dataset.limitations.append("Data Missing: news/event feed unavailable.")
        return dataset

    async def fetch_us_daily_returns(self, symbols: list[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.settings.request_timeout) as client:
            for symbol in symbols:
                row = await self.fetch_yahoo_daily_return(client, symbol)
                if row:
                    rows.append(row)
        return rows

    async def fetch_yahoo_daily_return(self, client: httpx.AsyncClient, symbol: str) -> dict[str, Any] | None:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {"range": "5d", "interval": "1d"}
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            result = (response.json().get("chart", {}).get("result") or [None])[0]
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            return None
        if not result:
            return None
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        opens = quote.get("open") or []
        valid: list[tuple[Any, float, float | None]] = []
        for idx, close in enumerate(closes):
            try:
                close_value = float(close)
            except (TypeError, ValueError):
                continue
            open_value = None
            try:
                open_value = float(opens[idx])
            except (IndexError, TypeError, ValueError):
                pass
            stamp = timestamps[idx] if idx < len(timestamps) else None
            valid.append((stamp, close_value, open_value))
        if len(valid) < 2:
            return None
        previous_close = valid[-2][1]
        latest_close = valid[-1][1]
        if previous_close <= 0:
            return None
        return {
            "symbol": symbol,
            "previous_close": previous_close,
            "latest_close": latest_close,
            "latest_open": valid[-1][2],
            "return_pct": (latest_close - previous_close) / previous_close,
            "timestamp": valid[-1][0],
            "source": "Yahoo Finance chart",
        }

    async def fetch_finmind_prices(self, client: httpx.AsyncClient, ticker: str) -> list[PriceBar]:
        start = (date.today() - timedelta(days=420)).isoformat()
        params = {"dataset": "TaiwanStockPrice", "data_id": ticker, "start_date": start}
        if self.settings.finmind_token:
            params["token"] = self.settings.finmind_token
        data = await self._finmind_get(client, params)
        bars: list[PriceBar] = []
        for row in data:
            try:
                bars.append(
                    PriceBar(
                        date=date.fromisoformat(row["date"]),
                        open=float(row["open"]),
                        high=float(row["max"]),
                        low=float(row["min"]),
                        close=float(row["close"]),
                        volume=float(row.get("Trading_Volume") or row.get("trading_volume") or 0),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return bars

    async def fetch_finmind_institutional(self, client: httpx.AsyncClient, ticker: str) -> list[DataPoint]:
        start = (date.today() - timedelta(days=90)).isoformat()
        params = {"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "data_id": ticker, "start_date": start}
        if self.settings.finmind_token:
            params["token"] = self.settings.finmind_token
        rows = await self._finmind_get(client, params)
        points: list[DataPoint] = []
        for row in rows[-60:]:
            points.append(
                DataPoint(
                    source="FinMind",
                    name=str(row.get("name") or row.get("institutional_investors") or "institutional_flow"),
                    value=row.get("buy", 0) if "buy" in row else row,
                    date=_safe_date(row.get("date")),
                    url="https://api.finmindtrade.com/docs",
                )
            )
        return points

    async def fetch_fundamentals(self, client: httpx.AsyncClient, ticker: str) -> list[DataPoint]:
        start = (date.today() - timedelta(days=420)).isoformat()
        params = {"dataset": "TaiwanStockMonthRevenue", "data_id": ticker, "start_date": start}
        if self.settings.finmind_token:
            params["token"] = self.settings.finmind_token
        rows = await self._finmind_get(client, params)
        points: list[DataPoint] = []
        for row in rows[-12:]:
            points.append(
                DataPoint(
                    source="FinMind",
                    name="monthly_revenue",
                    value=row,
                    date=_safe_date(row.get("date")),
                    url="https://api.finmindtrade.com/docs",
                )
            )
        return points

    async def fetch_scfi(self, client: httpx.AsyncClient) -> list[DataPoint]:
        # Shanghai Shipping Exchange publishes latest composite SCFI publicly, but detailed route history can be delayed or subscription-based.
        url = "https://www.sse.net.cn/indexIntro?indexName=scfi"
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return [DataPoint(source="Shanghai Shipping Exchange", name="SCFI", missing=True, note=f"Data Missing: {exc}")]
        return [
            DataPoint(
                source="Shanghai Shipping Exchange",
                name="SCFI public page",
                value="latest public SCFI page fetched; parse/upload detailed history for route-level backtests",
                url=url,
                missing=False,
            )
        ]

    async def fetch_news(self, client: httpx.AsyncClient, ticker: str) -> list[DataPoint]:
        if not self.settings.news_api_key:
            return [DataPoint(source="NewsAPI", name="news", missing=True, note="Data Missing: NEWS_API_KEY not configured.")]
        query = f"{ticker} 長榮 海運 OR Evergreen Marine"
        params = {"q": query, "language": "zh", "sortBy": "publishedAt", "apiKey": self.settings.news_api_key}
        try:
            response = await client.get("https://newsapi.org/v2/everything", params=params)
            response.raise_for_status()
            articles = response.json().get("articles", [])[:10]
        except httpx.HTTPError as exc:
            return [DataPoint(source="NewsAPI", name="news", missing=True, note=f"Data Missing: {exc}")]
        return [
            DataPoint(
                source="NewsAPI",
                name=article.get("title") or "news",
                value=article.get("description"),
                url=article.get("url"),
                date=_safe_date((article.get("publishedAt") or "")[:10]),
            )
            for article in articles
        ]

    async def _finmind_get(self, client: httpx.AsyncClient, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            response = await client.get("https://api.finmindtrade.com/api/v4/data", params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        if payload.get("status") not in (200, "200"):
            return []
        return payload.get("data") or []


def _safe_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None
