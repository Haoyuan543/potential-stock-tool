# ROADMAP

排序原則：按照「對 2603.TW 長榮投資決策提升幅度」排序，不按照工程難度排序。

## P0：最能降低錯誤決策與假訊號

### 1. 修復中文編碼與搜尋關鍵字完整性

目前多個後端檔案中出現中文亂碼，這會污染：

- 搜尋關鍵字
- missing reason
- 報告文字
- ETF/Announcement/Freight 關鍵字判定

這是 P0，因為資料抓取與報告可信度都依賴文字。

### 2. 建立 Truthfulness Engine

新增報告級真實度分數：

- Exact Data
- Scraped Data
- Search Inferred
- Stale Data
- Missing Data
- Conflict Data

Gate：

- Truthfulness < 60：Insufficient Data
- Truthfulness 60~75：最多 Neutral-Bullish / Neutral-Bearish
- Search Inferred > 35%：禁止 Strong verdict
- P0 Conflict：禁止方向結論

### 3. 建立 Gap Hunter

當 P0/P1 欄位 missing、stale、suspicious、conflict 時，自動跑 resolution chain：

1. API
2. Playwright
3. RSS
4. Search
5. AI Extraction

輸出 Gap Resolution Report，並明確標記：

- resolved_exact
- resolved_scraped
- resolved_search_inferred
- unresolved_missing
- unresolved_conflict

### 4. Freight Source Independence

Freight Intelligence 需要辨識來源是否真的獨立：

- SCFI 官方
- Freightos
- Drewry
- Reuters
- Lloyd's List
- MoneyDJ/鉅亨/Google News

同一篇新聞被多站轉載，只能算一個 independent source。若 route exact missing，trend 可用，但 confidence cap 需要更嚴格。

### 5. Official / High-Quality Freight Data Path

對長榮而言，Freight 是 P0。優先補：

- SCFI 綜合指數 weekly change
- US West route trend
- US East route trend
- Europe route trend
- weeks up/down
- as_of

若 exact rate 無法取得，至少要有多來源趨勢和來源獨立性。

### 6. Verdict Gate Hardening

正式規則：

- Overall Score < 65：不得 Bullish，只能 Neutral-Bullish。
- Timing Score < 50：必須標示「方向偏多，但短線不適合追」。
- Risk Score < 50：不可積極買進或大幅加碼。
- Market Regime confidence < 0.5：不得 Strong Bullish。
- P0 missing >= 2：Neutral 或 Insufficient Data。
- ETF stale inferred 不得大幅加分。

### 7. Prediction Tracker v2

每次分析後保存完整可回測 snapshot：

- price
- price_data_date
- Direction/Timing/Valuation/Risk/Coverage/Truthfulness
- verdict
- recommendation
- sell zone
- buyback zone
- P0 missing list
- source hash

驗證：

- 7d return
- 30d return
- 90d return
- max drawdown
- dividend-adjusted price
- whether verdict was correct

## P1：提升部位管理與中期勝率

### 1. Market Regime Engine v2

正式抓取：

- 台股加權指數
- 航運類股指數
- 台股成交量
- S&P 500 / Nasdaq / Dow
- VIX
- DXY
- USD/TWD

輸出：

- Risk On
- Neutral
- Risk Off

並影響：

- Timing Score
- Risk Score
- Final Verdict

### 2. ETF Flow Engine v2

目標不是搜尋 ETF 代號，而是取得：

- ETF holdings
- 2603.TW weight
- AUM change
- as_of
- stale flag

若只能搜尋推論：

- `etf_flow = inferred_bullish/inferred_bearish`
- confidence capped
- score boost minimal

### 3. Announcement Intelligence v2

明確分成：

- today_material_event
- recent_event_within_7_days
- stale_event_over_14_days
- fetch_failed

官方抓取失敗不可被解讀成無公告。

### 4. Fill Dividend Probability v2

補齊：

- 現金股利
- 除息日
- 除息前股價
- 歷史填息天數
- SCFI/Freight trend
- 法人籌碼
- ETF flow
- Market regime

若歷史資料不足，機率可為 null，不硬估。

### 5. Personalized Decision Engine

Personalized Mode 應把使用者看到的決策壓縮成：

- 今日動作
- 核心部位
- 機動部位
- 下一個賣點
- 下一個買回點
- 改變看法的條件

並納入：

- 稅率
- 手續費
- 證交稅
- 除息稅負
- 滑價
- 最大可接受回撤

## P2：提高解釋力與長期研究品質

### 1. News Relevance v2

用 entity + topic + source quality：

- 長榮 / Evergreen Marine
- SCFI
- Freight rate
- Red Sea
- Dividend
- MOPS announcement
- ETF holdings
- Institutional flows

`relevance_score < 0.6` 不進主分析。

### 2. Supply Cycle Data

補：

- 新船交付
- 拆船
- idle capacity
- 港口壅塞
- bunker fuel
- FX

這些更偏中長線，不應主導今日動作。

### 3. Structured AI Output

OpenAI 回傳先用 strict JSON：

```json
{
  "decision_brief": {},
  "verdict": "",
  "scores": {},
  "evidence": [],
  "warnings": [],
  "data_missing": []
}
```

再由本機 report composer 轉 Markdown。這樣才方便回測、比較與單元測試。

### 4. Historical Feature Store

建立 SQLite 或 DuckDB：

- prices
- institutional_flows
- freight_signals
- red_sea_events
- market_regime
- ETF holdings
- announcements
- reports
- predictions
- validations

JSONL 可保留，但不適合長期研究查詢。

## Target Decision Architecture

```text
Data Fetchers
  -> Gap Hunter
  -> Data Quality + Truthfulness Engine
  -> Feature Store
  -> Score Engine
  -> Verdict Gate
  -> Personalized Decision Engine
  -> AI Explanation
  -> Prediction Tracker
  -> Backtest / Calibration
```

## Success Criteria

P0 完成後，系統應做到：

1. 不再把 stale ETF/search inference 當成 confirmed bullish。
2. 不再把公告抓取失敗當成無公告或重大公告。
3. 不再因為一般新聞或技術面偏多就輸出 Bullish。
4. 每次報告都有 Truthfulness Score。
5. 每個 P0 missing 都會觸發 Gap Resolution Report。
6. 每次分析都能在未來 7/30/90 天驗證。
7. 使用者每天 1 分鐘可以看懂今日動作與下一個條件。

