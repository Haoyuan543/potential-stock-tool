# Architecture Review

審查日期：2026-06-05  
審查角色：Hedge Fund Quant Research Lead / Shipping Industry Analyst / Staff Software Engineer / AI System Auditor  
審查範圍：`backend/`、`frontend/`、`backend/services/`、`backend/search/`、`backend/data_fetchers/`、analysis pipeline。  
本報告只做審查，不修改程式邏輯。

## Executive Finding

目前專案已經不是靜態表單，具備 FastAPI 後端、OpenAI 分析、FinMind 資料、Playwright/Search/Freight Intelligence、ETF/Red Sea/Announcement/Prediction Tracker 等模組雛形。

但它距離可穩定支援真實投資決策仍有明顯差距。最大問題不是功能數量，而是資料可信度分層、信心分數校準、搜尋推論去重、事件時效判斷、以及回測閉環尚未成熟。若不修正，系統容易在低品質資料上輸出看似有結構的多空結論。

## Architecture Scores

| Area | Score | Weakness | Impact | Priority |
|---|---:|---|---|---|
| Data Collection | 6.5/10 | 已有 FinMind、Yahoo fallback、RSS/Search、Playwright、OCR，但 Freight/ETF/公告仍大量依賴搜尋或非結構化來源。缺少 site-specific crawler registry。 | 對 2603.TW 這種航運循環股，核心資料若只靠搜尋推論，會導致假多或假空。 | P0 |
| Data Quality | 5.0/10 | 有 exact/scraped/search-inferred/stale/missing 分類，但多數是報告層標籤，不是欄位級 provenance。缺少 conflict data 偵測。部分中文字串出現亂碼。 | 報告可能把搜尋推論與官方數字混在一起，使用者難以知道哪些是真實數據。亂碼會破壞搜尋關鍵字與解釋文字。 | P0 |
| Data Freshness | 5.5/10 | 股價日期有 freshness check，但 ETF、公告、Freight、新聞、市場環境的 as_of/stale 規則不一致。 | 會把 14 天以上事件或 ETF 舊持股誤當今日訊號。 | P0 |
| Search Layer | 6.0/10 | 有 Google News RSS、多搜尋 API fallback、DOM/network/screenshot extraction，但缺少 source independence、source ranking calibration、conflict resolution。 | 多篇轉載同一新聞可能被當成多來源一致，推高 confidence。 | P0 |
| AI Analysis | 6.5/10 | Prompt 已要求不得幻想與標記 Data Missing，但輸出仍主要是 Markdown，缺少嚴格 JSON schema 和機器可驗證欄位。長 prompt 也可能 timeout。 | AI 報告可讀性提高，但難以穩定回測與自動驗證。 | P1 |
| Decision Quality | 6.0/10 | 已有 Neutral-Bullish gate、Timing/Risk 限制，但 score 仍是 heuristic，未經歷史校準。 | 分數看起來精準，但目前不是統計上校準過的 alpha score。 | P0 |
| Personalization | 6.0/10 | 可讀 `user_profile.yaml`，有核心/機動部位與區間建議。但未完整納入稅費、除息稅負、滑價、分批成本與最大回撤偏好。 | 對使用者部位有幫助，但仍偏規則化，非完整 portfolio decision engine。 | P1 |
| Backtesting | 3.5/10 | 有 `analysis_history.jsonl`、`predictions.jsonl`、`prediction_tracker.py`、`backtest_engine.py`，但尚未形成可靠資料庫與自動驗證閉環。 | 目前無法證明 AI 判斷長期有效，也無法校準分數權重。 | P0 |

## Current Pipeline

目前 `/analyze` 大致流程：

1. FastAPI 接收 symbol、mode、model、manual supplement。
2. `AnalysisService` 平行抓取 stock、institutional、freight、news、fundamentals、announcements。
3. 建立衍生情報：News Relevance、Freight Intelligence、ETF Flow、Red Sea、Announcement Intelligence、Market Regime、Fill Dividend Probability。
4. 本機 heuristic score 先產生 raw/revised score、market state、action plan。
5. 建立 prompt 丟給 OpenAI；若失敗則 fallback report。
6. 寫入 `data/analysis_history.jsonl` 與 `data/predictions.jsonl`。

這個 pipeline 的方向正確，但 `AnalysisService` 已經承擔太多責任：資料抓取、資料融合、評分、風控 gate、個人化建議、prompt、fallback 報告、history/prediction storage 都混在同一層。這會降低可測試性與可維護性。

## Critical Missing Data

以下重新依照「對 2603.TW 長榮決策影響」排序，不沿用工程模組既有權重。

### P0：會直接改變今日多空與買賣決策

| Data | Why It Matters for 2603.TW | Current Risk |
|---|---|---|
| SCFI composite trend and weekly change | 長榮獲利彈性高度受運價方向影響，SCFI 是市場最核心訊號。 | 若只靠 OCR/Search，可能誤判趨勢或週變化。 |
| US West / US East / Europe route trend | 分航線運價比綜合 SCFI 更接近獲利彈性與市場定價。 | exact rate 常缺，Search-inferred 需嚴格標示。 |
| Freight trend source consistency | 若 SCFI、Freightos、Drewry、Reuters 方向一致，才可提高航運 bull case。 | 目前 source_count 未確認來源獨立性。 |
| Red Sea / Suez / Cape rerouting status | 紅海正常化會壓低繞航支撐，可能快速逆轉運價預期。 | Search keyword 可用，但未做事件可信度與時間序列。 |
| Price freshness and intraday/close status | 若使用前一交易日收盤，不能當即時追價或停損依據。 | 股價 freshness 有做，但報告與 action gate 應更強制。 |
| Institutional true flows | 外資、投信、自營商連買賣是短線籌碼關鍵。 | 投信連續 0 已有 suspicious，但仍需交叉 TWSE/券商資料。 |

### P1：會影響部位大小、風險與填息機率

| Data | Why It Matters for 2603.TW | Current Risk |
|---|---|---|
| ETF flow actual holdings / AUM / as_of | 被動買盤可能支撐長榮填息與股價慣性。 | 目前多為 stale/search-inferred，不能大幅加分。 |
| Market regime: TWII, shipping sector, US indices, VIX, DXY, USD/TWD | Risk-on/risk-off 決定同一個公司訊號是否能被市場放大。 | 目前 market regime 過度簡化，未真正抓完整市場資料。 |
| MOPS/TWSE/IR announcements | 股利、法說、重大訊息會直接改變估值與風險。 | API 302/404 或 search fallback 不可解讀成無公告。 |
| Dividend/ex-date and historical fill records | Personalized mode 的核心問題之一是填息與稅後報酬。 | 現在填息機率是 heuristic，歷史填息資料不足。 |
| Monthly revenue quality and YoY base | 月營收是基本面確認訊號。 | 有 FinMind，但需處理基期、船隊/運價滯後性。 |

### P2：提高解釋力，但不應主導結論

| Data | Why It Matters | Current Risk |
|---|---|---|
| General news sentiment | 可捕捉市場預期與事件，但噪音高。 | relevance filter 仍偏 keyword-based。 |
| Analyst/media expectations | 可判斷市場是否已定價。 | 易受轉載與標題黨影響。 |
| New vessel delivery / capacity cycle | 中長線供給壓力。 | 尚未結構化。 |
| Bunker fuel / FX / port congestion | 影響成本與短期運價。 | 尚未納入正式模型。 |

## GAP_HUNTER Design

`GAP_HUNTER` 不應只是補資料工具，而應是資料可信度控制器。當欄位為 missing、stale、suspicious 或 conflict 時，依序嘗試：

1. API：FinMind、TWSE OpenAPI、MOPS、官方 ETF、官方指數或可授權資料源。
2. Playwright：抓官方頁 DOM、table、network JSON。
3. RSS：Google News RSS、Yahoo 股市、MoneyDJ、鉅亨、Reuters 摘要。
4. Search：Brave/SerpAPI/Tavily，要求來源白名單與時間限制。
5. AI Extraction：只從已抓到的文本/截圖中抽取，不得生成不存在的數字。

Gap Resolution Report 應包含：

```json
{
  "gap_id": "freight.us_west.weekly_change",
  "priority": "P0",
  "before_status": "missing",
  "attempts": [
    {"layer": "api", "status": "failed", "reason": "no public endpoint"},
    {"layer": "playwright", "status": "partial", "source": "SSE page"},
    {"layer": "rss", "status": "resolved", "source": "Reuters", "as_of": "2026-06-05"}
  ],
  "resolved_status": "search_inferred",
  "value": {"trend": "up", "exact_rate": null},
  "confidence": 0.62,
  "truthfulness_warning": "Exact route rate unavailable; trend inferred from text.",
  "next_action": "Prefer paid route-rate API or confirmed official table."
}
```

## Truthfulness Engine Design

目前已有 Data Quality 類別，但缺少「這份報告到底有多少是真的」的總分。建議新增 Truthfulness Score：

| Component | Weight | Positive Evidence | Penalty |
|---|---:|---|---|
| Exact Data | 35% | 官方 API、FinMind、OHLCV、明確公告數字 | 無 |
| Scraped Data | 20% | DOM/table/network/OCR 並附來源時間 | OCR 低信心或頁面無日期 |
| Search Inferred | 15% | 多來源且獨立、一致、近 72 小時 | 轉載重複、無日期、標題推論 |
| Stale Data | -15% | as_of 過期但仍標示 | P0 stale 加倍扣分 |
| Missing Data | -20% | 欄位缺漏且影響決策 | P0 missing 加倍扣分 |
| Conflict Data | -25% | 不同來源方向衝突 | 未解決衝突不可強結論 |

輸出建議：

```json
{
  "truthfulness_score": 82,
  "data_coverage": 91,
  "exact_data_share": 0.46,
  "scraped_data_share": 0.17,
  "search_inferred_share": 0.28,
  "stale_data_share": 0.06,
  "missing_data_share": 0.09,
  "conflict_data_share": 0.00,
  "warning": "Search inferred share above 25%; avoid strong conclusion."
}
```

## Market Regime Engine Design

目前 `market_regime_engine.py` 不足以作為正式市場風險判定。應改為多資料輸入：

| Input | Role |
|---|---|
| Taiwan Weighted Index | 台股大盤 risk-on/risk-off |
| Shipping sector index | 航運類股相對強弱 |
| TAIEX volume | 風險偏好與流動性 |
| S&P 500 / Nasdaq / Dow futures | 外部風險偏好 |
| VIX | 全球避險程度 |
| DXY | 美元壓力 |
| USD/TWD | 外資與台股資金壓力 |

輸出：

```json
{
  "market_regime": "risk_on/neutral/risk_off",
  "taiwan_market": "bullish/bearish/neutral",
  "shipping_sector": "bullish/bearish/neutral",
  "confidence": 0.0,
  "sources": [],
  "as_of": "",
  "stale": false
}
```

Gate rule：`confidence < 0.5` 時，任何 Bullish 都必須降級為 `Neutral-Bullish / 中性偏多`，且禁止 `Strong Bullish`。

## Prediction Tracker Design

目前已有 prediction record，但要成為可回測系統，必須記錄「當下可觀測資訊」，避免未來資料污染。

每次分析後應寫入：

```json
{
  "prediction_id": "",
  "symbol": "2603.TW",
  "analysis_time": "",
  "price": 236.0,
  "price_data_date": "",
  "verdict": "Neutral-Bullish",
  "direction_score": 62,
  "timing_score": 45,
  "valuation_score": 70,
  "risk_score": 42,
  "coverage_score": 64,
  "truthfulness_score": 72,
  "recommendation": "不追價",
  "sell_zone": [245, 250],
  "buyback_zone": [220, 230],
  "data_snapshot_hash": ""
}
```

7/30/90 天驗證：

```json
{
  "prediction_id": "",
  "horizon": "30d",
  "actual_return": null,
  "max_drawdown": null,
  "correct": null,
  "price_adjusted_for_dividend": true,
  "validation_status": "pending/resolved/data_missing"
}
```

## Revised Conviction Score

單一總分不適合投資決策。建議分數改為：

| Score | Meaning | Decision Use |
|---|---|---|
| Direction Score | 未來方向偏多或偏空 | 決定偏多、偏空、觀望 |
| Timing Score | 現在位置是否適合追價或賣出 | 低分時不追，即使方向偏多 |
| Valuation Score | 股利、EPS、估值是否合理 | 決定是否有長線持有空間 |
| Risk Score | 下行風險是否升高 | 低分時不可積極操作 |
| Coverage Score | 資料完整度 | 低分時避免強結論 |
| Truthfulness Score | 證據真實度與衝突程度 | 低分時降級為 Insufficient Data |

總結規則：

- Direction high + Timing low：方向偏多，但短線不適合追。
- Direction high + Risk low：偏多但不可積極加碼。
- Coverage low 或 Truthfulness low：不可輸出 Strong Bullish / Strong Bearish。
- P0 missing 超過 2 項：輸出 Insufficient Data 或 Neutral。

## Decision Brief Design

每日 1 分鐘摘要不超過 10 行：

```markdown
## Decision Brief
1. 今日結論：
2. 方向：
3. 風險：
4. 今日動作：
5. 核心部位：
6. 機動部位：
7. 下一個賣點：
8. 下一個買回點：
9. 改變看法的條件：
10. 最大資料缺口：
```

Detailed Report 再放 Freight、ETF、Red Sea、Announcement、Market Regime、Fill Dividend、Data Quality、Data Missing。

## Maintenance Risks

1. 部分 Python 檔案中的中文字串已出現亂碼，會影響報告、搜尋關鍵字與 missing reason。這是 P0 維護風險。
2. `AnalysisService` 過大，建議拆成 `Pipeline Orchestrator`、`Score Engine`、`Report Composer`、`Persistence Service`。
3. Search-inferred evidence 未確認來源獨立性，會放大同一篇新聞的權重。
4. Backtest 尚未連到穩定歷史特徵資料，因此無法校準 score。
5. AI 報告仍以 Markdown 為主，建議要求 OpenAI 先輸出 strict JSON verdict，再由本機 composer 轉 Markdown。

