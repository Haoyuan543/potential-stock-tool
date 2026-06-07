from __future__ import annotations

import asyncio
from datetime import date
from html import unescape
import re
from typing import Any
from urllib.parse import quote

import httpx

from backend.config import get_settings
from backend.models import DataPoint
from backend.search.web_search import web_search


class OfficialResearchFetcher:
    """Collect first-party and stock-specific intelligence without using AI tokens."""

    STOCK_PROFILES: dict[str, dict[str, Any]] = {
        "2330": {
            "name": "台積電",
            "role": "晶圓代工 / 先進製程 / 先進封裝",
            "aliases": ["台積電", "TSMC", "Taiwan Semiconductor", "2330"],
            "drivers": ["CoWoS", "HBM", "AI accelerator", "NVIDIA", "輝達", "Apple", "3nm", "2nm", "先進封裝", "產能", "資本支出"],
            "risks": ["地緣政治", "出口管制", "客戶砍單", "毛利率", "電價", "設備延遲"],
            "us_leaders": ["NVDA", "AMD", "AVGO", "AAPL", "ASML"],
            "ir_url": "https://investor.tsmc.com/chinese",
        },
        "2454": {
            "name": "聯發科",
            "role": "IC 設計 / 手機 SoC / 車用與 ASIC",
            "aliases": ["聯發科", "MediaTek", "2454"],
            "drivers": ["手機晶片", "天璣", "AI PC", "ASIC", "Wi-Fi 7", "邊緣 AI", "車用晶片", "Android", "出貨", "市占"],
            "risks": ["中國手機需求", "庫存調整", "高通競爭", "毛利率", "價格競爭"],
            "us_leaders": ["QCOM", "NVDA", "AMD", "AAPL"],
            "ir_url": "https://www.mediatek.tw/investor-relations",
        },
        "2303": {
            "name": "聯電",
            "role": "成熟製程晶圓代工 / 車用與工控",
            "aliases": ["聯電", "UMC", "2303"],
            "drivers": ["成熟製程", "車用", "工控", "產能利用率", "晶圓代工", "28nm", "22nm", "價格", "庫存去化"],
            "risks": ["成熟製程供過於求", "中國產能", "價格壓力", "利用率下滑"],
            "us_leaders": ["TXN", "ADI", "ON", "STM"],
            "ir_url": "https://www.umc.com/zh-TW/IR",
        },
        "2379": {
            "name": "瑞昱",
            "role": "IC 設計 / 網通 / PC 音訊與乙太網路",
            "aliases": ["瑞昱", "Realtek", "2379"],
            "drivers": ["Wi-Fi 7", "乙太網路", "交換器", "PC", "AI PC", "網通", "市占", "出貨"],
            "risks": ["PC 需求", "庫存", "價格競爭", "中國競爭"],
            "us_leaders": ["AVGO", "QCOM", "MRVL", "INTC"],
            "ir_url": "https://www.realtek.com/InvestorRelations",
        },
        "3034": {
            "name": "聯詠",
            "role": "驅動 IC / 面板供應鏈",
            "aliases": ["聯詠", "Novatek", "3034"],
            "drivers": ["DDIC", "OLED", "面板", "TV", "手機", "TDDI", "驅動 IC", "庫存去化", "報價"],
            "risks": ["面板景氣", "中國競爭", "庫存", "價格下跌"],
            "us_leaders": ["AAPL", "QCOM"],
            "ir_url": "https://www.novatek.com.tw/InvestorRelations",
        },
        "3711": {
            "name": "日月光投控",
            "role": "封測 / SiP / 先進封裝",
            "aliases": ["日月光", "日月光投控", "ASE", "3711"],
            "drivers": ["封測", "先進封裝", "SiP", "AI chip", "CoWoS", "測試", "稼動率", "Apple", "NVIDIA"],
            "risks": ["消費電子需求", "封測價格", "稼動率", "匯率"],
            "us_leaders": ["NVDA", "AAPL", "AMD", "AVGO"],
            "ir_url": "https://www.aseglobal.com/ch/investor-relations",
        },
        "3443": {
            "name": "創意",
            "role": "ASIC / 設計服務 / 台積電先進製程生態系",
            "aliases": ["創意", "GUC", "3443"],
            "drivers": ["ASIC", "AI ASIC", "NRE", "先進製程", "台積電", "HPC", "客戶量產", "NVIDIA", "CSP"],
            "risks": ["客戶集中", "NRE 波動", "專案遞延", "估值"],
            "us_leaders": ["NVDA", "AVGO", "GOOGL", "AMZN", "MSFT"],
            "ir_url": "https://www.guc-asic.com/tw/investor",
        },
        "3661": {
            "name": "世芯-KY",
            "role": "ASIC / AI 晶片設計服務",
            "aliases": ["世芯", "世芯-KY", "Alchip", "3661"],
            "drivers": ["ASIC", "AI ASIC", "CSP", "HPC", "先進製程", "NRE", "量產", "客戶訂單"],
            "risks": ["客戶集中", "中國客戶", "出口管制", "專案遞延", "估值"],
            "us_leaders": ["NVDA", "AVGO", "GOOGL", "AMZN", "MSFT"],
            "ir_url": "https://www.alchip.com/investor-relations/",
        },
        "2317": {
            "name": "鴻海",
            "role": "EMS / AI server / 電動車",
            "aliases": ["鴻海", "Foxconn", "Hon Hai", "2317"],
            "drivers": ["AI server", "GB200", "GB300", "NVIDIA", "電動車", "iPhone", "雲端伺服器", "液冷", "機櫃"],
            "risks": ["蘋果需求", "毛利率", "匯率", "中國生產", "電動車虧損"],
            "us_leaders": ["NVDA", "AAPL", "MSFT", "AMZN"],
            "ir_url": "https://www.foxconn.com/zh-tw/investor-relations",
        },
        "2382": {
            "name": "廣達",
            "role": "ODM / AI server / 雲端伺服器",
            "aliases": ["廣達", "Quanta", "2382"],
            "drivers": ["AI server", "GB200", "GB300", "NVIDIA", "CSP", "雲端伺服器", "液冷", "機櫃", "出貨"],
            "risks": ["毛利率", "零組件缺貨", "出貨遞延", "客戶集中"],
            "us_leaders": ["NVDA", "MSFT", "AMZN", "GOOGL", "META"],
            "ir_url": "https://www.quantatw.com/Quanta/chinese/investment/index.aspx",
        },
        "3231": {
            "name": "緯創",
            "role": "ODM / AI server / ICT 製造",
            "aliases": ["緯創", "Wistron", "3231"],
            "drivers": ["AI server", "GB200", "GB300", "NVIDIA", "伺服器", "液冷", "CSP", "出貨"],
            "risks": ["毛利率", "零組件缺貨", "出貨遞延", "客戶集中"],
            "us_leaders": ["NVDA", "MSFT", "AMZN", "GOOGL"],
            "ir_url": "https://www.wistron.com/CMS/Page/16",
        },
        "2356": {
            "name": "英業達",
            "role": "ODM / server / notebook",
            "aliases": ["英業達", "Inventec", "2356"],
            "drivers": ["AI server", "伺服器", "筆電", "雲端", "液冷", "出貨", "CSP"],
            "risks": ["毛利率", "筆電需求", "零組件", "出貨遞延"],
            "us_leaders": ["NVDA", "MSFT", "AMZN"],
            "ir_url": "https://www.inventec.com/tw/investor-relations",
        },
        "6669": {
            "name": "緯穎",
            "role": "雲端資料中心 / AI server",
            "aliases": ["緯穎", "Wiwynn", "6669"],
            "drivers": ["AI server", "CSP", "資料中心", "GB200", "GB300", "NVIDIA", "液冷", "機櫃", "出貨"],
            "risks": ["客戶集中", "出貨遞延", "毛利率", "供應鏈缺料"],
            "us_leaders": ["NVDA", "MSFT", "AMZN", "META"],
            "ir_url": "https://www.wiwynn.com/zh/investor-relations",
        },
        "2308": {
            "name": "台達電",
            "role": "電源 / 散熱 / 工業自動化 / AI data center",
            "aliases": ["台達電", "Delta Electronics", "2308"],
            "drivers": ["AI data center", "電源", "散熱", "液冷", "電動車", "工業自動化", "能源管理", "HVDC"],
            "risks": ["匯率", "工業需求", "毛利率", "零組件"],
            "us_leaders": ["NVDA", "TSLA", "MSFT", "AMZN"],
            "ir_url": "https://www.deltaww.com/zh-TW/Investors",
        },
        "2603": {
            "name": "長榮",
            "role": "貨櫃航運 / 運價循環 / 紅海與港口壅塞",
            "aliases": ["長榮", "長榮海運", "Evergreen Marine", "2603"],
            "drivers": ["SCFI", "CCFI", "運價", "紅海", "繞航", "港口壅塞", "美西線", "歐洲線", "旺季", "艙位"],
            "risks": ["運價下跌", "新船供給", "需求轉弱", "油價", "停火", "塞港緩解"],
            "us_leaders": ["ZIM", "MATX", "MAERSK-B.CO"],
            "ir_url": "https://www.evergreen-marine.com/tw/ir/",
        },
        "2881": {
            "name": "富邦金",
            "role": "金控 / 壽險 / 銀行 / 投資收益",
            "aliases": ["富邦金", "Fubon Financial", "2881"],
            "drivers": ["升息", "降息", "殖利率", "債券評價", "壽險", "銀行利差", "股利", "資本適足"],
            "risks": ["匯損", "避險成本", "債券跌價", "信用風險", "金融監理"],
            "us_leaders": ["JPM", "BAC", "KRE", "TLT"],
            "ir_url": "https://www.fubon.com/financialholdings/investor/index.html",
        },
    }

    GENERIC_PROFILE = {
        "name": "",
        "role": "台股個股",
        "aliases": [],
        "drivers": ["營收", "法人買賣超", "法說", "訂單", "產能", "毛利率", "庫存", "股利", "展望"],
        "risks": ["下修", "減產", "處置", "注意股", "訴訟", "匯損", "需求轉弱"],
        "us_leaders": [],
        "ir_url": "",
    }

    def __init__(self) -> None:
        self.settings = get_settings()

    async def collect(self, client: httpx.AsyncClient, ticker: str) -> list[DataPoint]:
        stock_id = self._stock_id(ticker)
        profile = self.profile_for(stock_id)
        tasks = [
            self.fetch_mops_material_info(client, stock_id, profile),
            self.fetch_twse_material_info(client, stock_id, profile),
            self.fetch_tpex_material_info(client, stock_id, profile),
            self.fetch_exchange_alerts(client, stock_id, profile),
            self.fetch_ir_and_conference_links(client, stock_id, profile),
            self.fetch_supply_chain_keyword_news(client, stock_id, profile),
            self.fetch_stock_driven_web_intel(stock_id, profile),
        ]
        results: list[DataPoint] = []
        for task in tasks:
            try:
                results.extend(await task)
            except Exception as exc:  # noqa: BLE001
                results.append(
                    DataPoint(
                        source="Research v3",
                        name="source fetch failed",
                        missing=True,
                        note=f"Data Missing: official/source fetch failed: {exc}",
                    )
                )
        return self._dedupe_and_rank(results)[:40]

    def profile_for(self, stock_id: str) -> dict[str, Any]:
        profile = {**self.GENERIC_PROFILE, **self.STOCK_PROFILES.get(stock_id, {})}
        aliases = list(dict.fromkeys([stock_id, profile.get("name") or "", *profile.get("aliases", [])]))
        profile["aliases"] = [item for item in aliases if item]
        if not profile.get("name"):
            profile["name"] = stock_id
        return profile

    async def fetch_mops_material_info(self, client: httpx.AsyncClient, stock_id: str, profile: dict[str, Any]) -> list[DataPoint]:
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
        for row in rows[:10]:
            text = " ".join(row)
            if not self._mentions_stock(text, stock_id, profile):
                continue
            title = row[2] if len(row) > 2 else "重大訊息"
            points.append(self._point("MOPS 重大訊息", title, text, "official_mops", "https://mops.twse.com.tw/mops/web/t05st01", 98, profile))
        return points or [
            self._point("MOPS 重大訊息", "當月無重大訊息命中", f"{profile['name']} 目前未從 MOPS 當月重大訊息取得可用事件。", "official_mops", "https://mops.twse.com.tw/mops/web/t05st01", 55, profile, missing=True)
        ]

    async def fetch_twse_material_info(self, client: httpx.AsyncClient, stock_id: str, profile: dict[str, Any]) -> list[DataPoint]:
        return await self._fetch_openapi_rows(client, "https://openapi.twse.com.tw/v1/opendata/t187ap04_L", stock_id, profile, "TWSE 上市公司每日重大訊息", "official_mops", 95)

    async def fetch_tpex_material_info(self, client: httpx.AsyncClient, stock_id: str, profile: dict[str, Any]) -> list[DataPoint]:
        urls = [
            "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O",
            "https://www.tpex.org.tw/openapi/v1/t187ap04_O",
        ]
        points: list[DataPoint] = []
        for url in urls:
            points.extend(await self._fetch_openapi_rows(client, url, stock_id, profile, "TPEx 上櫃公司每日重大訊息", "official_mops", 94, tolerate_error=True))
            if points:
                break
        return points

    async def fetch_exchange_alerts(self, client: httpx.AsyncClient, stock_id: str, profile: dict[str, Any]) -> list[DataPoint]:
        endpoints = [
            ("TWSE 注意股票", "https://openapi.twse.com.tw/v1/announcement/notice", "exchange_alert", 88),
            ("TWSE 處置股票", "https://openapi.twse.com.tw/v1/announcement/punish", "exchange_alert", 90),
            ("TPEx 注意股票", "https://www.tpex.org.tw/openapi/v1/tpex_trading_attention", "exchange_alert", 88),
            ("TPEx 處置股票", "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information", "exchange_alert", 90),
        ]
        points: list[DataPoint] = []
        for source, url, tier, credibility in endpoints:
            points.extend(await self._fetch_openapi_rows(client, url, stock_id, profile, source, tier, credibility, tolerate_error=True))
        return points

    async def fetch_ir_and_conference_links(self, client: httpx.AsyncClient, stock_id: str, profile: dict[str, Any]) -> list[DataPoint]:
        points: list[DataPoint] = []
        ir_url = str(profile.get("ir_url") or "")
        if ir_url:
            title = await self._page_title(client, ir_url)
            points.append(self._point("公司 IR", title or f"{profile['name']} 投資人關係", f"{profile['role']} 官方 IR，可追蹤財報、法說、展望與重大營運更新。", "company_ir", ir_url, 86, profile))
        mops_conference_url = f"https://mops.twse.com.tw/mops/web/t100sb07?co_id={quote(stock_id)}"
        points.append(self._point("法說會/簡報", f"{profile['name']} 法說會與簡報查詢", f"{profile['role']} 法說簡報與法人說明會資料，需與公司 IR/MOPS 交叉確認。", "conference_material", mops_conference_url, 84, profile))
        return points

    async def fetch_supply_chain_keyword_news(self, client: httpx.AsyncClient, stock_id: str, profile: dict[str, Any]) -> list[DataPoint]:
        if not self.settings.news_api_key:
            return [
                self._point("供應鏈關鍵字搜尋", "NewsAPI 未設定", "Data Missing: NEWS_API_KEY not configured for stock-driven keyword search.", "supply_chain_search", None, 45, profile, missing=True)
            ]
        points: list[DataPoint] = []
        for query in self._newsapi_queries(stock_id, profile):
            params = {"q": query, "language": "zh", "sortBy": "publishedAt", "pageSize": 10, "apiKey": self.settings.news_api_key}
            response = await client.get("https://newsapi.org/v2/everything", params=params)
            response.raise_for_status()
            for article in response.json().get("articles", [])[:10]:
                article_url = str(article.get("url") or "")
                if not self._usable_url(article_url):
                    continue
                title = str(article.get("title") or "")
                summary = str(article.get("description") or "")
                text = f"{title} {summary}"
                relevance = self._relevance(text, profile)
                if relevance < 8:
                    continue
                points.append(
                    self._point(
                        "股性關鍵字新聞",
                        title or "股性相關新聞",
                        summary,
                        "supply_chain_search",
                        article_url,
                        68,
                        profile,
                        query=query,
                        relevance_score=relevance,
                        published_at=str(article.get("publishedAt") or "")[:10],
                    )
                )
        return points

    async def fetch_stock_driven_web_intel(self, stock_id: str, profile: dict[str, Any]) -> list[DataPoint]:
        queries = self._web_queries(stock_id, profile)
        result = await asyncio.to_thread(web_search, queries, 4)
        points: list[DataPoint] = []
        for row in result.get("results", [])[:16]:
            url = str(row.get("url") or "")
            if not self._usable_url(url):
                continue
            title = str(row.get("title") or "")
            snippet = str(row.get("snippet") or "")
            text = f"{title} {snippet}"
            relevance = self._relevance(text, profile)
            if relevance < 8:
                continue
            points.append(
                self._point(
                    "股性網路搜尋",
                    title or "股性相關搜尋結果",
                    snippet,
                    "supply_chain_search",
                    url,
                    62,
                    profile,
                    query=str(row.get("query") or ""),
                    search_source=str(row.get("source") or ""),
                    relevance_score=relevance,
                    published_at=str(row.get("published_at") or ""),
                )
            )
        if result.get("missing") and not points:
            return [
                self._point("股性網路搜尋", "搜尋來源暫不可用", "; ".join(str(item) for item in result.get("missing", [])[:2]), "supply_chain_search", None, 40, profile, missing=True)
            ]
        return points

    async def _fetch_openapi_rows(
        self,
        client: httpx.AsyncClient,
        url: str,
        stock_id: str,
        profile: dict[str, Any],
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
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = " ".join(str(value) for value in row.values())
            if not self._mentions_stock(text, stock_id, profile):
                continue
            title = self._row_title(row)
            points.append(self._point(source, title, row, tier, url, credibility, profile))
        return points[:8]

    def _newsapi_queries(self, stock_id: str, profile: dict[str, Any]) -> list[str]:
        aliases = self._or_terms(profile["aliases"][:4])
        drivers = self._or_terms(profile["drivers"][:8])
        leaders = self._or_terms(profile["us_leaders"][:4])
        queries = [f"({aliases}) AND ({drivers})"]
        if leaders:
            queries.append(f"({aliases}) AND ({leaders})")
        if profile.get("role"):
            queries.append(f"({aliases}) AND ({profile['role'].split('/')[0].strip()})")
        return [query[:450] for query in queries]

    def _web_queries(self, stock_id: str, profile: dict[str, Any]) -> list[str]:
        name = profile["name"]
        drivers = " OR ".join(profile["drivers"][:5])
        risks = " OR ".join(profile["risks"][:4])
        leaders = " OR ".join(profile["us_leaders"][:4])
        queries = [
            f'"{name}" "{stock_id}" ({drivers})',
            f'"{name}" ({risks})',
        ]
        if leaders:
            queries.append(f'"{name}" ({leaders})')
        return queries

    def _or_terms(self, terms: list[str]) -> str:
        return " OR ".join(f'"{term}"' if " " in term else str(term) for term in terms if term)

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

    def _mentions_stock(self, text: str, stock_id: str, profile: dict[str, Any]) -> bool:
        haystack = text.lower()
        return stock_id.lower() in haystack or any(str(alias).lower() in haystack for alias in profile.get("aliases", []) if alias)

    def _relevance(self, text: str, profile: dict[str, Any]) -> int:
        haystack = text.lower()
        alias_hits = [term for term in profile.get("aliases", []) if str(term).lower() in haystack]
        driver_hits = [term for term in profile.get("drivers", []) if str(term).lower() in haystack]
        risk_hits = [term for term in profile.get("risks", []) if str(term).lower() in haystack]
        leader_hits = [term for term in profile.get("us_leaders", []) if str(term).lower() in haystack]
        return min(100, len(alias_hits) * 10 + len(driver_hits) * 8 + len(risk_hits) * 7 + len(leader_hits) * 6)

    def _hits(self, text: str, terms: list[str]) -> list[str]:
        haystack = text.lower()
        return [term for term in terms if str(term).lower() in haystack][:8]

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
        profile: dict[str, Any],
        missing: bool = False,
        **extra: Any,
    ) -> DataPoint:
        payload = value if isinstance(value, dict) else {"summary": value}
        text = " ".join([str(name or ""), str(payload)])
        if isinstance(payload, dict):
            payload = {
                **payload,
                "tier": tier,
                "credibility": credibility,
                "stock_role": profile.get("role"),
                "drivers_hit": self._hits(text, profile.get("drivers", [])),
                "risk_terms_hit": self._hits(text, profile.get("risks", [])),
                "us_leaders_hit": self._hits(text, profile.get("us_leaders", [])),
                "relevance_score": max(int(extra.pop("relevance_score", 0) or 0), self._relevance(text, profile)),
                **extra,
            }
        return DataPoint(source=source, name=str(name or source), value=payload, url=url, missing=missing)

    def _dedupe_and_rank(self, points: list[DataPoint]) -> list[DataPoint]:
        seen: set[tuple[str, str, str]] = set()
        unique: list[DataPoint] = []
        for point in points:
            key = (point.source, point.name, point.url or "")
            if key in seen:
                continue
            seen.add(key)
            unique.append(point)

        tier_rank = {
            "official_mops": 0,
            "exchange_alert": 1,
            "supply_chain_search": 2,
            "company_ir": 3,
            "conference_material": 4,
        }

        def rank(point: DataPoint) -> tuple[int, int, int]:
            value = point.value if isinstance(point.value, dict) else {}
            tier = str(value.get("tier") or "")
            relevance = int(value.get("relevance_score") or 0)
            credibility = int(value.get("credibility") or 0)
            return (1 if point.missing else 0, tier_rank.get(tier, 9), -(relevance + credibility))

        return sorted(unique, key=rank)

    def _stock_id(self, ticker: str) -> str:
        return str(ticker).split(".")[0].upper()
