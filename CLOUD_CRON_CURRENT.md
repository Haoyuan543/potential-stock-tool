# 雲端排程目前設定

更新日期：2026-06-07

## 目前策略

分析端點已會自動呼叫 Research Collector 補資料。也就是說，cron-job.org 不需要再另外排 08:05、10:00、20:00 三條資料蒐集工作；只要打三個主要分析流程即可。

Research Collector 仍保留為獨立端點，用途是手動預熱、除錯、或未來想額外建立資料倉儲時使用。

## 建議 cron-job.org 排程

```text
08:30  https://YOUR_DOMAIN/api/cron/potential-stocks?session=pre_market&background=true&token=YOUR_SECRET
10:05  https://YOUR_DOMAIN/api/cron/potential-stocks?session=market_hours&background=true&token=YOUR_SECRET
20:10  https://YOUR_DOMAIN/api/cron/potential-stocks?session=post_market&background=true&token=YOUR_SECRET
```

`YOUR_SECRET` 請填 Render 環境變數 `CRON_JOB_SECRET` 的值。不要把 token 貼到公開文件或 GitHub。

## 執行順序保護

- `pre_market`：產生盤前計畫與候選股排序。
- `market_hours`：必須同一天已經有 `pre_market`，才會執行盤中模擬交易。
- `post_market`：必須同一天已經有 `market_hours`，才會執行盤後結算。

如果順序不符合，API 會回傳 `skipped=true`，不會硬寫錯誤資料。

## 資料蒐集邏輯

每次執行主要分析端點時，後端會先檢查 Supabase 或本機 research bundle：

1. 股票資料 4 小時內有效。
2. 美股科技/半導體領先資料 12 小時內有效。
3. 如果快取缺漏或過期，分析流程會先呼叫 non-AI collector 補資料。
4. collector 仍抓不到時，才退回直接即時抓取或保守估算。

這樣可以減少 cron-job.org 定時器數量，也能避免每次分析都從零開始抓資料。

## 可選手動端點

手動刷新資料：

```text
https://YOUR_DOMAIN/api/cron/research-collector?background=true&token=YOUR_SECRET
```

查看資料包狀態：

```text
https://YOUR_DOMAIN/api/research-collector/status
```

## cron-job.org 注意事項

- Method 用 `GET` 即可。
- Request body 留空。
- Timeout 建議 30 秒。
- `background=true` 必須保留，避免 cron-job.org 因輸出太大或執行太久判定失敗。
- 建議打開 job history，但不要開啟 save full response，避免保存過長回應。
