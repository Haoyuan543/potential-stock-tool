# 潛力股工具雲端與 Supabase 設定

## 目前完成

- 本機 JSONL 與 Supabase 雲端 DB 已共用同一套資料介面。
- 啟動後可在面板用「資料來源」選單切換本機資料或 Supabase 雲端資料，不需要每次手動改 `STORAGE_BACKEND`。
- 雲端部署可用 `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` 做基本面板保護。
- cron-job.org 可繼續呼叫 `/api/cron/potential-stocks`，並用 `CRON_JOB_SECRET` 驗證。

## 重要觀念

本機測雲端 DB 時，不需要手動把 `.env` 裡的 `STORAGE_BACKEND` 來回改成 `local` 或 `supabase`。

但 Supabase 連線資訊仍然要先設定一次，否則切到 Supabase 時後端不知道要連哪個專案：

```env
SUPABASE_URL=你的 Project URL
SUPABASE_SERVICE_ROLE_KEY=你的 service_role key
SUPABASE_RECORDS_TABLE=potential_stock_records
```

建議本機 `.env` 維持：

```env
STORAGE_BACKEND=local
```

然後在面板用「資料來源」選單切換測試。

## 1. 建立 Supabase 資料表

1. 到 Supabase 建立 project。
2. 到 `Project Settings -> API` 複製：
   - `Project URL`
   - `service_role key`
3. 到 Supabase 的 `SQL Editor`。
4. 執行 [database/potential_stock_supabase.sql](database/potential_stock_supabase.sql)。

會建立：

```text
potential_stock_records
```

這張表用 `store_name` 區分不同資料類型，`payload` 保留完整 JSON 紀錄。

## 2. 本機切換測試

1. 在本機 `.env` 填入 Supabase URL/key。
2. 啟動本機工具。
3. 打開面板。
4. 在「資料來源」選擇：
   - `本機資料`
   - `Supabase 雲端資料`
5. 按「切換資料來源」。
6. 面板會重新讀取案件、每日狀況、買賣帳本。

如果切到 Supabase 後顯示失敗，通常是：

- `SUPABASE_URL` 沒填。
- `SUPABASE_SERVICE_ROLE_KEY` 沒填。
- Supabase SQL 尚未建立資料表。
- service role key 貼錯或有空白。

## 3. 雲端部署環境變數

雲端建議預設直接使用 Supabase：

```env
STORAGE_BACKEND=supabase
SUPABASE_URL=你的 Project URL
SUPABASE_SERVICE_ROLE_KEY=你的 service_role key
SUPABASE_RECORDS_TABLE=potential_stock_records
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=請設定一組長密碼
CRON_JOB_SECRET=請設定一組長亂數
OPENAI_API_KEY=你的 OpenAI key
FINMIND_TOKEN=你的 FinMind token
NEWS_API_KEY=你的 News API key
OPENAI_MODEL=gpt-5.5
```

`DASHBOARD_PASSWORD` 一定要設，否則雲端面板沒有基本保護。

## 4. Render 部署

已加入 [render.yaml](render.yaml)，Render 可用 Blueprint 部署。

手動部署時設定：

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
Health Check Path: /health
```

如果使用 Docker 平台，也已加入 [Dockerfile](Dockerfile)。

## 5. cron-job.org 排程

建議三段：

```text
08:30 Asia/Taipei -> pre_market
10:00 Asia/Taipei -> market_hours
14:30 Asia/Taipei -> post_market
```

URL：

```text
POST https://你的雲端網址/api/cron/potential-stocks
```

Headers 可擇一：

```text
X-Cron-Token: 你的 CRON_JOB_SECRET
```

或 body 放 token：

```json
{
  "token": "你的 CRON_JOB_SECRET",
  "report_session": "pre_market",
  "market_universes": ["semiconductor", "electronics"],
  "initial_capital": 3000000,
  "max_positions": 5,
  "use_live_data": true,
  "persist": true
}
```

三個 job 分別改：

```text
pre_market
market_hours
post_market
```

## 6. 面板查看

雲端部署後直接開：

```text
https://你的雲端網址/
```

瀏覽器會跳出帳密視窗：

```text
帳號：DASHBOARD_USERNAME，預設 admin
密碼：DASHBOARD_PASSWORD
```

登入後看到的功能會和本機相同，只是資料來源預設建議用 Supabase。

## 7. 本機與雲端資料分開

- 本機資料：`backend/data/*.jsonl`
- 雲端資料：Supabase `potential_stock_records`

兩邊資料不會自動混在一起。你可以在本機面板切換資料來源，檢查雲端 DB 內容是否正常。
