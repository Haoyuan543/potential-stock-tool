# 雲端運作目標紀錄

## 目前策略決議

本工具先採用「一天一個正式盤中成交窗口」：

```text
08:30 盤前分析選股：只產生今日計畫，不成交。
09:30 盤中執行模擬交易：依盤前計畫，用當下股價 + 滑價成交，寫入帳本。
13:00 盤中風險參考：只產生參考分析，不新增成交，不寫帳本。
14:30 盤後結算今日結果：更新收盤估值、帳戶淨值與檢討，不回頭新增買進。
```

核心原則：

- 不用盤後結果倒推盤前決策。
- 同一天盤中正式買進只允許一次。
- 第二次盤中檢查只作風險參考，避免策略變成追價工具。
- 盤後只結算與檢討，不新增未在盤中成交的買進。

## 本機完成度

| 項目 | 狀態 | 備註 |
| --- | --- | --- |
| 預設半導體股票池 | Done | 可切換電子、傳產、金融或自訂。 |
| 盤前計畫 | Done | 產生 `PLAN_BUY`，不改正式帳本。 |
| 盤中正式模擬交易 | Done | `market_hours + persist=true` 會依盤前計畫成交。 |
| 盤中參考掃描 | Done | `persist=false`，只看候選股，不寫帳本。 |
| 盤後結算 | Done | 更新持股估值與淨值，不新增買進。 |
| 正式持倉延續帳本 | Done | 本機 JSONL 延續 cash、holdings、costs、strategy version。 |
| 重置案件 | Done | 舊案件保留，新案件重新追蹤。 |
| 每日狀況表 | Done | 顯示盤前、盤中、盤後三階段。 |
| 歷史回放與 benchmark | Done locally | 本機回測含手續費、稅、滑價、持倉延續、benchmark。 |
| 本機測試 | Done | `RUN_LOCAL_TESTS.bat` 通過。 |

## 雲端目標

| 階段 | 狀態 | 要完成的事 |
| --- | --- | --- |
| Cloud 1: cron-job.org 排程 | In progress | GitHub Actions schedule 已停用，改由 cron-job.org 呼叫 `/api/cron/potential-stocks`。設定方式見 `CRON_JOB_ORG_SETUP.md`。 |
| Cloud 2: Secrets | Not started | 設定 `FINMIND_TOKEN`、`NEWS_API_KEY`、`OPENAI_API_KEY`、可選 `OPENAI_MODEL`。 |
| Cloud 3: Durable storage | Not started | 將 JSONL 改成 Supabase/Postgres，避免雲端多次執行資料遺失。 |
| Cloud 4: Transaction safety | Not started | 加入交易鎖或 DB transaction，避免排程重疊寫入。 |
| Cloud 5: Artifact review | Not started | 手動跑 workflow，確認四個時段報告 artifact 正確。 |
| Cloud 6: Notification | Not started | 選 Email、Google Sheets 或 Dashboard 作每日通知。 |
| Cloud 7: Cloud acceptance | Not started | 驗證不重複成交、持倉延續、benchmark、案件保留都正常。 |

## 上雲端前必檢

- [ ] 決定資料庫：建議 Supabase/Postgres。
- [ ] 設計 reports、ledger、cases、active case schema。
- [ ] 將本機 JSONL store 抽換成雲端 store。
- [ ] 保證同一天同一階段 idempotent。
- [ ] 保證 13:00 參考分析不寫正式帳本。
- [ ] 保證 14:30 盤後結算不新增買進。
- [ ] 在 cron-job.org 建立 08:30、09:30、13:00、14:30 四個 Job。
- [ ] 手動 Run now 測試四種 session。
- [ ] 下載 artifact 檢查報告內容。
- [ ] 連續跑至少 3 個交易日，再檢查績效與 benchmark。

## 2026-06-07 US tech leading factor
- Local scope now includes a default US tech / semiconductor leading factor for pre-market Taiwan stock selection.
- Current local fallback is conservative/neutral when no US market data source is connected.
- Cloud follow-up: connect previous US session data for NVDA, AMD, AVGO, TSM, ASML, AMAT, QQQ, SMH, SOXX and convert the fallback score into a live signal.

## 2026-06-07 雲端設計目標更新

### 本機已完成後再上雲端的前提
- 本機預設資金改為 NT$3,000,000。
- 本機預設搜尋範圍改為半導體 + AI/電子股。
- 盤前不再強迫每天交易；分數達標後仍需通過資料品質、籌碼品質、基本面/籌碼一致性與價格可用性，否則只列觀察。
- 每日狀況、支線總結、買賣帳本、案件列表已移到潛力股排行前方。
- 每日狀況改成摘要表 + 每日展開明細，盤後可看持股狀況與資金狀況表。

### 雲端資料庫方向
- 首選：Supabase Postgres。
- 用途：保存 cases、reports、ledgers、branch settings、scheduled runs、strategy versions。
- 報告 Markdown/HTML 若變大，再放 Supabase Storage 或 Cloudflare R2。
- 本機 JSONL 只作開發期儲存，雲端正式運作不建議繼續用檔案。

### 雲端面板方向
- 不再看 `127.0.0.1`。
- 第一階段最簡單：FastAPI 同時服務 API 與目前前端，部署後看 `https://你的網域/`。
- 第二階段可拆成前端 Vercel/Netlify + 後端 Render/Fly/Cloud Run。
- 面板需要登入或至少保護刪除/重置/切換支線等管理動作。

### cron-job.org 排程方向
- 08:30：`pre_market`，產生盤前計畫，不成交。
- 10:00：`market_hours`，依盤前計畫與當下價格執行模擬交易。
- 14:30 或資料更新後：`post_market`，結算淨值、持股、市值、績效與隔日提醒。
- 每個 cron request 都要帶 `CRON_JOB_SECRET`。
- 後續要支援固定 `case_id` 或 branch key，讓遠端永遠追同一條主線。

### 下一批雲端實作清單
- [ ] 建立 Postgres schema 與 migration。
- [ ] 抽象 storage adapter，讓目前 JSONL store 可替換成 Postgres store。
- [ ] 新增 branch/server settings API，讓「儲存設定」不只存在瀏覽器 localStorage。
- [ ] cron endpoint 支援固定 `case_id`、固定設定快照與 idempotency key。
- [ ] 部署 API + dashboard。
- [ ] 設定 cron-job.org 三段排程並測試 run-now。
- [ ] 加最基本 dashboard auth 與 cron token 保護。
