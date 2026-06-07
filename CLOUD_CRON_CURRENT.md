# 雲端排程目前設定

更新日：2026-06-07

## 使用方式

1. 到雲端面板設定股票池、模擬資金、風險偏好、持股上限等欄位。
2. 按「儲存設定」。
3. cron-job.org 的排程網址預設會讀目前資料來源裡最後儲存的設定。雲端使用 Supabase 時，就會讀 Supabase 的設定資料。

## 正式排程 URL

```text
https://YOUR_DOMAIN/api/cron/potential-stocks?session=pre_market&background=true&token=YOUR_SECRET
https://YOUR_DOMAIN/api/cron/potential-stocks?session=market_hours&background=true&token=YOUR_SECRET
https://YOUR_DOMAIN/api/cron/potential-stocks?session=post_market&background=true&token=YOUR_SECRET
```

`YOUR_SECRET` 換成 Render 裡的 `CRON_JOB_SECRET`。

## 執行順序

- `pre_market` 可以先執行。
- `market_hours` 必須同一天已完成 `pre_market`，否則回傳 `skipped=true`，不會亂做盤中交易。
- `post_market` 必須同一天已完成 `market_hours`，否則回傳 `skipped=true`，不會跳過盤中直接結算。

## 參數覆蓋

排程預設使用資料庫儲存設定，也就是：

```text
use_saved_settings=true
```

如果臨時要完全改用 URL 參數，才加：

```text
use_saved_settings=false
```

正式使用時建議不要把股票池、資金、持股上限塞在 URL，直接用面板「儲存設定」管理即可。
## Research Collector 先行資料排程

新版建議先讓 non-AI collector 抓資料，再讓分析流程讀取已整理好的資料包。這樣比較省 OpenAI token，也比較不會在盤前分析時才遇到資料來源 timeout。

建議 cron-job.org 順序：

```text
08:05  https://YOUR_DOMAIN/api/cron/research-collector?background=true&token=YOUR_SECRET
08:30  https://YOUR_DOMAIN/api/cron/potential-stocks?session=pre_market&background=true&token=YOUR_SECRET
10:00  https://YOUR_DOMAIN/api/cron/research-collector?background=true&token=YOUR_SECRET
10:05  https://YOUR_DOMAIN/api/cron/potential-stocks?session=market_hours&background=true&token=YOUR_SECRET
20:00  https://YOUR_DOMAIN/api/cron/research-collector?background=true&token=YOUR_SECRET
20:10  https://YOUR_DOMAIN/api/cron/potential-stocks?session=post_market&background=true&token=YOUR_SECRET
```

Collector 預設會讀取面板儲存的股票池與設定，所以 URL 通常不用再帶 symbols。要檢查資料倉儲狀態可看：

```text
https://YOUR_DOMAIN/api/research-collector/status
```

目前 collector 不使用 OpenAI API；它只負責抓資料、標準化、存進本機或 Supabase，分析工具再讀取這些資料包。
