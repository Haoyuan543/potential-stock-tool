# cron-job.org 排程設定

GitHub Actions 的 `schedule` 可能延遲。本工具改用 cron-job.org 準時呼叫雲端 API。

## 前置條件

1. 將此專案部署成常駐 Web API，例如 Render、Railway、Fly.io、VPS 或其他可公開存取的服務。
2. 在雲端環境變數設定：
   - `CRON_JOB_SECRET`: 一組長隨機密碼，用來保護排程端點。
   - `FINMIND_TOKEN`
   - `NEWS_API_KEY`
   - `OPENAI_API_KEY`，若要用 AI 深度解讀。
3. 確認雲端網址的 `/health` 正常回應。

## cron-job.org Job

cron-job.org 建議建立 4 個 Job，HTTP Method 用 `GET`。

請把下方的 `https://YOUR_DOMAIN` 換成你的雲端網址，`YOUR_SECRET` 換成 `CRON_JOB_SECRET`。

| 台灣時間 | 用途 | URL |
| --- | --- | --- |
| 08:30 週一至週五 | 盤前分析選股，只建立計畫 | `https://YOUR_DOMAIN/api/cron/potential-stocks?session=pre_market&token=YOUR_SECRET` |
| 09:30 週一至週五 | 盤中執行模擬交易，寫入帳本 | `https://YOUR_DOMAIN/api/cron/potential-stocks?session=market_hours&token=YOUR_SECRET` |
| 13:00 週一至週五 | 只抓潛力股參考分析，不寫資料 | `https://YOUR_DOMAIN/api/cron/potential-stocks?session=market_hours&persist=false&token=YOUR_SECRET` |
| 14:30 週一至週五 | 盤後結算今日結果 | `https://YOUR_DOMAIN/api/cron/potential-stocks?session=post_market&token=YOUR_SECRET` |

## 建議設定

- Timezone: `Asia/Taipei`
- Schedule: 週一至週五
- Timeout: 至少 120 秒；若使用 AI 深度解讀，建議 300 秒以上。
- Failure notification: 開啟 Email 通知。
- Retry: 可開啟 1 次，但正式交易階段已做同日同階段不可變紀錄，重跑不應改掉已產生的資料。

## 可選參數

可直接加在 URL query string：

- `market_universe=semiconductor`
- `symbols=2330.TW,2454.TW`
- `initial_capital=1000000`
- `max_positions=5`
- `strategy_version=potential-v1`
- `risk_reward_profile=balanced`
- `investment_horizon=mid_term_3m`
- `use_ai_analysis=true`

## 驗證方式

先手動在 cron-job.org 按 Run now，或用瀏覽器打：

```text
https://YOUR_DOMAIN/api/cron/potential-stocks?session=market_hours&persist=false&use_live_data=false&token=YOUR_SECRET
```

成功時會回傳：

```json
{
  "ok": true,
  "report_session": "market_hours",
  "analysis_count": 8,
  "trade_count": 0
}
```

## 注意

- 不要把 `CRON_JOB_SECRET` 貼到公開文件或 GitHub。
- GitHub Actions 自動 schedule 已停用，只保留手動 workflow_dispatch。
- cron-job.org 只負責準時呼叫 API；資料持久化仍建議後續改到 Supabase/Postgres。
