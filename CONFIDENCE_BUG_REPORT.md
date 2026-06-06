# Confidence Bug Report

審查日期：2026-06-05  
目標：找出 high confidence + low quality data、stale data、missing data、search hallucination 的風險。

## Executive Summary

目前系統已開始降低 ETF stale、market regime low-confidence、announcement stale event 的錯誤判定，但仍存在幾類 confidence bug：

1. 搜尋推論來源數可能被高估，轉載或同源內容會被當成多來源一致。
2. coverage 與 confidence 混用，導致「有低品質推論」被算成「資料已覆蓋」。
3. P0 欄位 missing 時的扣分不夠有階層，某些 P2 新聞存在會掩蓋 P0 Freight 缺漏。
4. fill dividend probability 有數字化輸出，但資料基礎仍是 heuristic。
5. 部分中文字串亂碼會讓搜尋關鍵字、報告文字與 missing reason 失真，間接影響 confidence。

## Confidence Bugs

| ID | Module | Pattern | Evidence | Impact | Priority |
|---|---|---|---|---|---|
| C-001 | ETF Flow | `holding_change=null`、`aum_change=null`、`stale=true` 仍可能被 coverage item 視為有效。 | `analysis_service.py` coverage item 以 `confidence >= 0.4` 判斷 ETF covered。`etf_flow_engine.py` 已 cap 到 0.45，但仍可過 coverage threshold。 | 使用者可能以為 ETF 被動買盤已被確認，其實只是 search-inferred。 | P0 |
| C-002 | Freight Intelligence | `source_count` 沒有驗證來源獨立性。 | 多個搜尋結果、截圖、DOM 可能源自同一篇文章或同一資料源。 | Freight confidence 可能過高，形成假 Bullish。 | P0 |
| C-003 | Freight Intelligence | route exact rate missing 但 trend inferred，coverage 下降幅度不足以反映精確度差異。 | exact route fields 仍常為 null，但 overall trend 可達 inferred。 | 對長榮而言，分航線缺漏會影響 EPS 與填息推估。 | P0 |
| C-004 | Red Sea Intelligence | 關鍵字搜尋可提高 confidence，但未區分事件方向、日期、是否為舊聞。 | `red_sea_intelligence.py` 主要依 status 與 source_count。 | 紅海正常化或升溫若判錯，會反向影響運價判斷。 | P0 |
| C-005 | Announcement Intelligence | search fallback 事件可能被列入 events，但官方 fetch failed 時無法證明沒有公告。 | 模組有區分 fetch_failed/stale，但 confidence 仍可能由 recent/today keyword 撐高。 | 重大公告誤判會直接影響交易決策。 | P0 |
| C-006 | Market Regime | confidence low 時已有降級規則，但 regime 本身資料來源不足。 | 目前未正式抓 VIX、DXY、USD/TWD、台股與航運指數。 | 市場 risk-off 可能沒被及時反映。 | P1 |
| C-007 | Fill Dividend Probability | 有 30d/90d/1y 機率，但歷史填息資料不足時仍可能產出數字。 | component scores 存在，但 historical_fill_score 可能 null。 | 使用者可能過度相信填息機率。 | P1 |
| C-008 | News Relevance | keyword scoring 容易把泛航運、泛 ETF、泛台股新聞納入。 | relevance filter 不是語意模型或 company-entity resolver。 | sentiment score 可能被噪音新聞污染。 | P2 |
| C-009 | Data Quality | 沒有 conflict_data 類別。 | `data_quality.py` 有 exact/scraped/inferred/stale/missing，但沒有 conflict。 | 多來源方向衝突時仍可能輸出單一路徑結論。 | P0 |
| C-010 | Encoding | 多個中文字串顯示為亂碼。 | 檢視 `analysis_service.py`、`etf_flow_engine.py`、`freight_intelligence.py`、`data_quality.py` 出現亂碼。 | 搜尋關鍵字、報告、missing reason 可能錯誤，進一步污染 confidence。 | P0 |

## High Confidence + Low Quality Data Cases

### ETF bullish / inferred_bullish

風險條件：

- `holding_change` missing
- `aum_change` missing
- `stale=true`
- 只有搜尋提到 ETF 代號

允許輸出：

```json
{
  "etf_flow": "inferred_bullish",
  "confidence": 0.45,
  "coverage_credit": 0.25,
  "score_boost": "minimal"
}
```

禁止輸出：

```json
{
  "etf_flow": "bullish",
  "confidence": 0.70,
  "score_boost": "large"
}
```

### Freight trend from repeated search snippets

風險條件：

- SCFI exact missing
- route exact missing
- 多個結果其實來自同一新聞或同一航運指數
- 只看到「運價上漲」但沒有日期與航線

允許輸出：

```json
{
  "overall_trend": "up",
  "status": "search_inferred",
  "confidence": 0.55,
  "exact_rate": null
}
```

若要 confidence > 0.75，需要：

- 至少 3 個獨立來源
- 至少 1 個官方或高可信來源
- 明確日期
- 航線或 SCFI 指標名稱
- 無重大衝突來源

### Announcement fetch failed

風險條件：

- MOPS/TWSE 302/404
- Search 沒結果

正確狀態：

```json
{
  "latest_event": "fetch_failed",
  "materiality": "unknown",
  "confidence": 0.0
}
```

禁止解讀：

- 無公告
- 今日重大公告
- 重大利多
- 重大利空

### Fill Dividend Probability

若缺少 historical fill records，應輸出：

```json
{
  "historical_fill_score": null,
  "confidence": "low",
  "warning": "Probability is heuristic, not statistically calibrated."
}
```

## Recommended Confidence Rules

| Condition | Required Cap |
|---|---:|
| Search-inferred only, no exact data | confidence <= 0.55 |
| Search-inferred, 2 independent sources | confidence <= 0.65 |
| Search-inferred, 3 independent sources + one authoritative source | confidence <= 0.80 |
| Stale P0 data | confidence <= 0.45 |
| Missing exact route freight but strong trend evidence | confidence <= 0.75 unless official source confirms |
| Official fetch failed | confidence = 0 for event absence |
| Conflict between sources | confidence <= 0.50 until resolved |
| Encoding-corrupted query/report field | confidence should be invalidated for affected module |

## Confidence vs Coverage Separation

目前風險在於 confidence 被用來代表 data coverage。建議分開：

```json
{
  "direction_confidence": 0.62,
  "data_coverage_credit": 0.35,
  "provenance": "search_inferred",
  "stale": true,
  "score_boost_allowed": false
}
```

ETF stale inferred 可以有方向推論，但 coverage credit 不應等同 exact holding data。

## Required Tests

1. ETF stale + missing holding/AUM：不得輸出 bullish，不得 confidence > 0.45。
2. Announcement fetch failed：不得輸出 no event 或 material event。
3. Freight 3 duplicate articles：source_count 應等於 1 independent source。
4. Red Sea old article：不得當成 latest status。
5. Market regime confidence < 0.5：不得輸出 Strong Bullish。
6. Overall < 65：不得輸出 Bullish。
7. Timing < 50：必須顯示「方向偏多，但短線不適合追」。
8. Risk < 50：不得輸出積極買進或大幅加碼。
9. P0 missing >= 2：Truthfulness Score 必須降級。
10. 中文亂碼出現於 query/report：該模組輸出需標記 suspicious。

