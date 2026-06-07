from __future__ import annotations

from datetime import date, timedelta
from html import unescape
import re
from typing import Any
from urllib.parse import quote

import httpx

from backend.config import get_settings
from backend.models import DataPoint


class OfficialResearchFetcher:
    STOCK_NAMES = {
        "2330": "台積電",
        "2454": "聯發科",
        "2303": "聯電",
        "2379": "瑞昱",
        "3034": "聯詠",
        "3711": "日月光投控",
        "3443": "創意",
        "3661": "世芯-KY",
        "2317": "鴻海",
        "2382": "廣達",
        "3231": "緯創",
        "2356": "英業達",
        "6669": "緯穎",
        "3017": "奇鋐",
        "2308": "台達電",
        "4938": "和碩",
        "2603": "長榮",
        "2609": "陽明",
        "2615": "萬海",
        "2881": "富邦金",
        "2882": "國泰金",
        "2891": "中信金",
    }
    COMPANY_IR_URLS = {
        "2330": "https://investor.tsmc.com/chinese",
        "2454": "https://www.mediatek.tw/investor-relations",
        "2303": "https://www.umc.com/zh-TW/IR",
        "2379": "https://www.realtek.com/InvestorRelations",
        "3034": "https://www.novatek.com.tw/InvestorRelations",
        "3711": "https://www.aseglobal.com/ch/investor-relations",
        "3443": "https://www.guc-asic.com/tw/investor",
        "3661": "https://www.alchip.com/investor-relations/",
        "2317": "https://www.foxconn.com/zh-tw/investor-relations",
        "2382": "https://www.quantatw.com/Quanta/chinese/investment/index.aspx",
        "3231": "https://www.wistron.com/CMS/Page/16",
        "2356": "https://www.inventec.com/tw/investor-relations",
        "6669": "https://www.wiwynn.com/zh/investor-relations",
        "2308": "https://www.deltaww.com/zh-TW/Investors",
    }
    SUPPLY_CHAIN_KEYWORDS = [
        "CoWoS",
        "HBM",
        "ASIC",
        "AI server",
        "GB200",
        "GB300",
        "CPO",
        "先進封裝",
        "ABF",
        "液冷",
        "矽光子",
        "DDR",
        "DDR5",
        "產能",
        "訂單",
        "NVIDIA",
        "輝達",
    ]

    def __init__(self) -> None:
        self.settings = get_settings()

    async def collect(self, client: httpx.AsyncClient, ticker: str) -> list[DataPoint]:
        stock_id = self._stock_id(ticker)
        tasks = [
            self.fetch_mops_material_info(client, stock_id),
            self.fetch_twse_material_info(client, stock_id),
            self.fetch_tpex_material_info(client, stock_id),
            self.fetch_exchange_alerts(client, stock_id),
            self.fetch_ir_and_conference_links(client, stock_id),
            self.fetch_supply_chain_keyword_news(client, stock_id),
        ]
        results: list[DataPoint] = []
        for task in tasks:
            try:
                results.extend(await task)
            except Exception as exc:  # noqa: BLE001
                results.append(
                    DataPoint(
                        source="Research v2",
                        name="source fetch failed",
                        missing=True,
                        note=f"Data Missing: official/source fetch failed: {exc}",
                    )
                )
        return self._dedupe(results)[:30]

    async def fetch_mops_material_info(self, client: httpx.AsyncClient, stock_id: str) -> list[DataPoint]:
        today = date.today()
        url = "https://mops.twse.com.tw/mops/web/ajax_t05st01"
        params = {
            "encodeURIComponent": "1",
            "step": "1",
            "firstin": "1",
            "off": "1",
            "TYPEK": "all",
            "co_id": stock_id,
            "year": str(today.year - 1911),
            "month": str(today.month),
        }
        response = await client.post(url, data=params, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        rows = self._html_rows(response.text)
        points = []
        for row in rows[:8]:
            text = " ".join(row)
            if stock_id not in text and self._stock_name(stock_id) not in text:
                continue
            points.append(
                self._point(
                    "MOPS 重大訊息",
                    row[2] if len(row) > 2 else "重大訊息",
                    text,
                    "official_mops",
                    "https://mops.twse.com.tw/mops/web/t05st01",
                    98,
                )
            )
        return points or [
            self._point(
                "MOPS 重大訊息",
                "本月重大訊息未直接取得",
                f"{stock_id} 本月 MOPS 重大訊息未由自動抓取取得；可用 MOPS 查詢頁人工確認。",
                "official_mops",
                "https://mops.twse.com.tw/mops/web/t05st01",
                55,
                missing=True,
            )
        ]

    async def fetch_twse_material_info(self, client: httpx.AsyncClient, stock_id: str) -> list[DataPoint]:
        return await self._fetch_openapi_rows(
            client,
            "https://openapi.twse.com.tw/v1/opendata/t187ap04_L",
            stock_id,
            "TWSE 上市公司每日重大訊息",
            "official_mops",
            95,
        )

    async def fetch_tpex_material_info(self, client: httpx.AsyncClient, stock_id: str) -> list[DataPoint]:
        urls = [
            "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O",
            "https://www.tpex.org.tw/openapi/v1/t187ap04_O",
        ]
        points: list[DataPoint] = []
        for url in urls:
            points.extend(await self._fetch_openapi_rows(client, url, stock_id, "TPEx 上櫃公司每日重大訊息", "official_mops", 94, tolerate_error=True))
            if points:
                break
        return points

    async def fetch_exchange_alerts(self, client: httpx.AsyncClient, stock_id: str) -> list[DataPoint]:
        endpoints = [
            ("TWSE 注意股票", "https://openapi.twse.com.tw/v1/announcement/notice", "exchange_alert", 88),
            ("TWSE 處置股票", "https://openapi.twse.com.tw/v1/announcement/punish", "exchange_alert", 90),
            ("TPEx 注意股票", "https://www.tpex.org.tw/openapi/v1/tpex_trading_attention", "exchange_alert", 88),
            ("TPEx 處置股票", "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information", "exchange_alert", 90),
        ]
        points: list[DataPoint] = []
        for source, url, tier, credibility in endpoints:
            points.extend(await self._fetch_openapi_rows(client, url, stock_id, source, tier, credibility, tolerate_error=True))
        return points

    async def fetch_ir_and_conference_links(self, client: httpx.AsyncClient, stock_id: str) -> list[DataPoint]:
        points: list[DataPoint] = []
        ir_url = self.COMPANY_IR_URLS.get(stock_id)
        if ir_url:
            title = await self._page_title(client, ir_url)
            points.append(self._point("公司 IR", title or f"{self._stock_name(stock_id)} 投資人關係", "公司投資人關係頁，可追蹤法說、簡報、財報與營運展望。", "company_ir", ir_url, 86))
        mops_conference_url = f"https://mops.twse.com.tw/mops/web/t100sb07?co_id={quote(stock_id)}"
        points.append(self._point("法說會/簡報", f"{self._stock_name(stock_id)} 法說會與簡報查詢", "法說簡報與法人說明會資料需以 MOPS/公司 IR 頁交叉確認。", "conference_material", mops_conference_url, 84))
        return points

    async def fetch_supply_chain_keyword_news(self, client: httpx.AsyncClient, stock_id: str) -> list[DataPoint]:
        if not self.settings.news_api_key:
            return [
                self._point("供應鏈關鍵字搜尋", "NewsAPI 未設定", "Data Missing: NEWS_API_KEY not configured for supply-chain keyword search.", "supply_chain_search", None, 45, missing=True)
            ]
        stock_name = self._stock_name(stock_id)
        query = f'("{stock_id}" OR "{stock_name}") AND ({" OR ".join(self.SUPPLY_CHAIN_KEYWORDS)})'
        params = {"q": query, "language": "zh", "sortBy": "publishedAt", "pageSize": 10, "apiKey": self.settings.news_api_key}
        response = await client.get("https://newsapi.org/v2/everything", params=params)
        response.raise_for_status()
        articles = response.json().get("articles", [])[:8]
        points = []
        for article in articles:
            article_url = str(article.get("url") or "")
            if not self._usable_url(article_url):
                continue
            text = " ".join([str(article.get("title") or ""), str(article.get("description") or "")])
            keywords = [keyword for keyword in self.SUPPLY_CHAIN_KEYWORDS if keyword.lower() in text.lower()]
            points.append(
                self._point(
                    "供應鏈關鍵字搜尋",
                    article.get("title") or "供應鏈新聞",
                    article.get("description") or "",
                    "supply_chain_search",
                    article_url,
                    68,
                    matched_keywords=keywords,
                    published_at=str(article.get("publishedAt") or "")[:10],
                )
            )
        return points

    async def _fetch_openapi_rows(
        self,
        client: httpx.AsyncClient,
        url: str,
        stock_id: str,
        source: str,
        tier: str,
        credibility: int,
        tolerate_error: bool = False,
    ) -> list[DataPoint]:
        try:
            response = await client.get(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            rows = response.json()
        except (httpx.HTTPError, ValueError):
            if tolerate_error:
                return []
            raise
        if not isinstance(rows, list):
            return []
        points = []
        stock_name = self._stock_name(stock_id)
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = " ".join(str(value) for value in row.values())
            if stock_id not in text and stock_name not in text:
                continue
            title = self._row_title(row)
            points.append(self._point(source, title, row, tier, url, credibility))
        return points[:8]

    async def _page_title(self, client: httpx.AsyncClient, url: str) -> str:
        try:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
        except httpx.HTTPError:
            return ""
        match = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return self._clean_text(match.group(1))[:80]

    def _html_rows(self, html: str) -> list[list[str]]:
        rows: list[list[str]] = []
        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.IGNORECASE | re.DOTALL)
            cleaned = [self._clean_text(cell) for cell in cells]
            cleaned = [cell for cell in cleaned if cell]
            if cleaned:
                rows.append(cleaned)
        return rows

    def _clean_text(self, value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", value)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _row_title(self, row: dict[str, Any]) -> str:
        preferred_keys = ("公司名稱", "公司簡稱", "證券名稱", "證券代號", "主旨", "標題", "說明", "處置條件")
        values = [str(row.get(key) or "") for key in preferred_keys if row.get(key)]
        if values:
            return " ".join(values)[:90]
        return " ".join(str(value) for value in list(row.values())[:3])[:90] or "官方公告"

    def _usable_url(self, url: str) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        blocked_hosts = ("consent.yahoo.com", "guce.yahoo.com")
        return not any(host in url for host in blocked_hosts)

    def _point(
        self,
        source: str,
        name: str,
        value: Any,
        tier: str,
        url: str | None,
        credibility: int,
        missing: bool = False,
        **extra: Any,
    ) -> DataPoint:
        payload = value if isinstance(value, dict) else {"summary": value}
        if isinstance(payload, dict):
            payload = {**payload, "tier": tier, "credibility": credibility, **extra}
        return DataPoint(source=source, name=str(name or source), value=payload, url=url, missing=missing)

    def _dedupe(self, points: list[DataPoint]) -> list[DataPoint]:
        seen: set[tuple[str, str, str]] = set()
        unique: list[DataPoint] = []
        for point in points:
            key = (point.source, point.name, point.url or "")
            if key in seen:
                continue
            seen.add(key)
            unique.append(point)
        return unique

    def _stock_id(self, ticker: str) -> str:
        return str(ticker).split(".")[0].upper()

    def _stock_name(self, stock_id: str) -> str:
        return self.STOCK_NAMES.get(stock_id, stock_id)
