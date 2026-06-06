# Verdict Audit

審查日期：2026-06-05  
目標：審查 Bullish / Bearish 判定是否在資料不足時過度自信，並定義降級規則。

## Executive Summary

目前程式已有幾個正確方向：

- `overall_score < 65` 不應輸出 Bullish。
- `timing_score < 50` 或 `risk_score < 50` 應降級。
- `market_regime.confidence < 0.5` 禁止 Strong Bullish。
- ETF stale + missing holding/AUM 已從 bullish 降為 inferred_bullish。
- Announcement stale/fetch_failed 已開始區分。

但 verdict 仍需更嚴格，尤其是 2603.TW 的核心 P0 資料缺漏時。長榮的多空判斷不應被一般新聞、ETF 搜尋、技術面短線突破單獨主導。

## Current Verdict Risk

| Risk | Why It Matters | Required Downgrade |
|---|---|---|
| Freight Intelligence up but exact route rates missing | 運價方向可能對，但 EPS 敏感度與填息推估仍不足。 | Bullish -> Neutral-Bullish unless confidence high and sources independent. |
| ETF inferred_bullish with stale data | 被動買盤未被確認。 | Bullish boost minimal; no aggressive action. |
| Announcement stale event over 14 days | 舊事件不可當今日重大事件。 | Ignore for today verdict; keep as context only. |
| Market regime confidence < 0.5 | 大盤風險不明。 | Strong Bullish forbidden; Bullish -> Neutral-Bullish. |
| Timing score < 50 | 即使方向偏多，也可能短線過熱。 | 必須顯示「方向偏多，但短線不適合追」。 |
| Risk score < 50 | 下行風險高。 | 不可給積極買進或大幅加碼。 |
| Price data not today | 無法支援即時決策。 | Any trading action must be conditional. |
| P0 data missing >= 2 | 核心判斷資料不足。 | Neutral-Bullish -> Neutral or Insufficient Data. |

## Downgrade Matrix

| Starting Verdict | Condition | Final Verdict |
|---|---|---|
| Strong Bullish | Any P0 missing, market regime confidence < 0.5, truthfulness < 85, timing < 60, risk < 60 | Bullish or Neutral-Bullish |
| Bullish | Overall < 65 | Neutral-Bullish |
| Bullish | Timing < 50 | Neutral-Bullish with no chase warning |
| Bullish | Risk < 50 | Neutral-Bullish or Neutral |
| Bullish | Freight confidence < 0.55 for 2603.TW | Neutral |
| Bullish | ETF only bullish evidence but stale/missing holdings | Neutral-Bullish at most |
| Neutral-Bullish | P0 missing >= 2 | Neutral or Insufficient Data |
| Bearish | Freight/Red Sea missing and bearish evidence is only technical RSI/MACD | Neutral-Bearish or Neutral |
| Strong Bearish | No confirmed negative P0 evidence | Bearish or Neutral-Bearish |

## Bullish Verdict Should Require

2603.TW 若要輸出 Bullish，至少需要：

1. Overall Score >= 65。
2. Timing Score >= 50。
3. Risk Score >= 50。
4. Freight Intelligence confidence >= 0.65，且來源具獨立性。
5. Market Regime confidence >= 0.5，或明確標示大盤不明但航運獨立強勢。
6. Price data fresh enough for the decision horizon。
7. Truthfulness Score >= 75。

若要輸出 Strong Bullish，還需要：

1. Freight trend strong with exact or authoritative evidence。
2. Route-level US West / US East / Europe 至少兩項有 exact 或高可信 trend。
3. Red Sea status supports freight or at least not normalizing。
4. Institutional flows not clearly deteriorating。
5. No stale P0 events。
6. Truthfulness Score >= 88。

## Bearish Verdict Should Require

2603.TW 若要輸出 Bearish，應至少有以下組合：

1. Freight trend down or Red Sea normalizing with confidence >= 0.65。
2. 外資連賣且投信/ETF 無接手跡象。
3. 股價跌破 20MA/60MA 且量能或籌碼轉弱。
4. Market regime risk_off。
5. Fundamental or revenue trend deteriorating。

若只有 RSI 過熱、短線漲多，應是 Timing Warning，不是 Bearish。

## Insufficient Data Conditions

以下任一情況應輸出 `Insufficient Data` 或 `Neutral`，不得輸出強方向：

- SCFI trend missing + route trend missing。
- Red Sea status unknown + Freight confidence < 0.55。
- Price data date missing or stale beyond previous trading day。
- MOPS/TWSE fetch failed and search fallback empty,但 report 需要判斷公告風險。
- Truthfulness Score < 60。
- Search Inferred share > 35% 且 P0 exact data insufficient。
- Conflict Data 存在且未解決。

## Decision Brief Verdict Rules

Decision Brief 不應重複 detailed report，也不應使用模糊語氣。建議格式：

```markdown
## Decision Brief
1. 今日結論：Neutral-Bullish / 中性偏多
2. 方向：運價方向偏多，但核心資料仍有推論成分
3. 風險：短線位置偏高，Timing Score 低
4. 今日動作：不追價；Personalized Mode 可只處理機動部位
5. 核心部位：不因短線波動全出
6. 機動部位：245~250 才考慮 2~3 張
7. 下一個賣點：245~250 / 255~260
8. 下一個買回點：220~230
9. 改變看法的條件：SCFI 轉弱 + 外資/投信同步賣 + 跌破 20MA
10. 最大資料缺口：分航線運價與 ETF 實際持股
```

## Verdict Unit Tests

| Test | Input | Expected |
|---|---|---|
| V-001 | overall=62, timing=45, risk=42 | Neutral-Bullish / 中性偏多 |
| V-002 | ETF inferred_bullish, stale=true, holding/AUM missing | No Bullish upgrade |
| V-003 | market regime confidence=0.25 | Strong Bullish forbidden |
| V-004 | announcement stale_event_over_14_days only | No today material event |
| V-005 | Freight exact route missing but trend up confidence=0.62 | Neutral-Bullish, not Strong Bullish |
| V-006 | Price data not today | Warning and conditional action only |
| V-007 | SCFI missing + Red Sea unknown + ETF stale | Insufficient Data |
| V-008 | Technical overheat only | Timing warning, not Bearish |

