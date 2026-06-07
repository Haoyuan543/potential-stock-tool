# 潛力股工具使用、績效回朔與雲端部署指南

## 你到時候該怎麼用

這個工具的定位是「潛力股篩選 + 模擬操作 + 績效驗證」，不是下單工具。

建議流程：

1. 盤前打開工具。
2. 搜尋範圍預設用「半導體股」。
3. 確認模擬資金，預設 `1,000,000`。
4. `08:30` 按「盤前進行分析選股」。
5. `09:30` 按「盤中執行模擬交易」。
6. `13:00` 可按「只抓潛力股參考分析」做風險檢查，但不改帳本。
7. `14:30` 按「盤後結算今日結果」。
8. 看三個重點：
   - 潛力股排行
   - 模擬操作
   - 個股基本面、籌碼面、營運狀況、新聞與風險
9. 每週查看績效回朔，檢查過去買進訊號與實際帳戶淨值。

自動判斷規則：

- 週一到週五 `09:00` 前：盤前計畫。
- 週一到週五 `09:00-14:00`：盤中階段。
- 週一到週五 `14:00` 後：盤後結算。
- 週末：視為非交易時段，預設走盤後檢討/下次交易日前準備。
- 歷史回放回測只會在你按「執行歷史回放回測」時執行，不會每次分析都自動跑。

目前採用的每日模擬規則：

```text
08:30 盤前只產生 PLAN_BUY，不寫入正式持倉帳本。
09:30 盤中讀取同一天盤前 PLAN_BUY，用當下股價 + 滑價模擬 BUY/SELL。
13:00 盤中風險參考只產生分析，不新增成交、不寫帳本。
14:30 盤後只更新收盤估值、帳戶淨值與檢討，不回頭新增買進。
只有盤中正式 BUY/SELL 才會進入實際交易績效。
```

這樣做的原因是：避免用盤後結果倒推盤前決策，也避免一天內多次追價造成績效失真。

## 每日盤前盤中盤後怎麼記錄

每次產生報告時，工具會保存一筆快照：

- 日期
- 盤前、盤中或盤後
- 股票代號與中文名稱
- 當下價格
- 分數
- 操作建議
- 模擬交易
- 帳戶現金、持股市值、總資產

## 持股數量限制與換股候選

目前預設最多同時持有 `5` 檔。

每天工具仍會掃描整個股票池，但模擬配置時只會把分數最高、達到買進門檻的前 N 檔納入持股。

如果買進候選超過上限：

- 前 N 檔會進入本次模擬持股。
- 其餘達標股票會列為「換股候選」。
- 盤後檢討時可以觀察換股候選是否持續比既有持股強。

目前這是「本次報告配置」的持股限制。下一階段會再做「持倉延續」，讓工具能從昨天的持股出發，判斷今天是否新增、續抱、減碼或換股。

同一天如果早上跑「盤前計畫」、晚上跑「盤後檢討」，工具會把兩筆資料配在一起。

## 正式持倉延續帳本與預設標準

目前本機版會保存正式紙上交易帳本：

```text
backend/data/potential_stock_ledger.jsonl
```

每次盤前或盤後報告會從上一筆帳本延續：

- 現金
- 持股
- 成本
- 未實現損益
- 實際模擬交易
- 每日帳戶淨值
- 候選股清單
- 策略版本
- benchmark 欄位

注意：盤前報告只保存計畫快照，不更新正式持倉帳本；正式帳本在盤中正式執行模擬交易後更新。盤後只做結算與檢討。

預設標準：

```text
買進門檻 = 70
觀察門檻 = 55
賣出門檻 = 50
風險/報酬偏好 = 中風險 / 中報酬
投資週期 = 中長線（約 3 個月）
停損 = 8%
停利 = 20%
換股分差 = 10 分
最短持有天數 = 3 天
最多持股 = 5 檔
單股上限 = 20%
手續費率 = 0.1425%
交易稅率 = 0.3%
滑價 = 5 bps
Benchmark = 0050.TW
策略版本 = potential-v1
```

調整方式：

- 想找高波動飆股：改成「高風險 / 高報酬」與「短線」。
- 想找比較穩的成長股：維持「中風險 / 中報酬」與「中長線」。
- 想做半年以上波段：改成「長線」或「長期」，系統會更重視基本面與資料品質。
- 想更積極：降低買進門檻、提高最多持股、降低換股分差。
- 想更保守：提高買進門檻、降低單股上限、提高賣出門檻。
- 想降低震盪出場：放寬停損、提高最短持有天數。
- 想更快鎖定獲利：降低停利。
- 每次大幅調參，請改策略版本，例如 `potential-v2`，避免新舊規則績效混在一起。

手動查看帳本：

```text
http://127.0.0.1:8011/api/potential-stocks/ledger
```

每日狀況表會顯示：

- 早上預計買進哪些股票
- 盤中是否依計畫成交
- 盤後這些股票目前分數與狀態
- 價格是否比早上轉強或轉弱
- 哪些需要隔天繼續觀察

股票會同時顯示代號與中文名稱，例如：

```text
2330.TW 台積電
2454.TW 聯發科
2303.TW 聯電
```

## 怎麼判斷工具有沒有用

不要只看單日報告，要看一段時間後的統計。

主要觀察：

- 買進訊號勝率
- 平均報酬
- 候選股命中率
- 實際交易勝率
- 實際帳戶淨值
- 實際帳戶累積報酬
- Benchmark 報酬
- 實際帳戶超額報酬
- 最佳訊號
- 最差訊號
- 待驗證訊號
- 是否常常買太貴的股票
- 是否常常因為資金不足只剩觀察
- 是否比大盤或半導體 ETF 更穩定

目前 MVP 的績效回朔方式：

- 每次產生報告時保存候選股快照。
- 之後用新快照的價格，回頭驗證過去 `買進` 訊號。
- 如果還沒有後續價格，就列為待驗證。

這個方法適合先驗證工具方向，但還不是完整歷史回測。完整版本應再加入：

- 台股歷史資料回放
- 每日真實模擬持倉延續
- 手續費、交易稅、滑價
- 停利、停損、加碼、減碼規則
- 與加權指數、0050、00891 或半導體 ETF 比較

## 本機手動執行

雙擊：

```text
啟動AI平台.bat
```

目前新版工具使用：

```text
http://127.0.0.1:8011
```

如果看到舊介面，通常代表 `8010` 被舊專案佔用，請改開 `8011`。

## 本機驗證

PowerShell 進入專案資料夾後執行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

看到 `OK` 表示目前測試通過。

## 雲端部署建議

第一階段建議用 GitHub Actions，原因是：

- 不需要長時間開一台伺服器。
- 適合每天盤前、盤中、盤後自動跑報告。
- 可以把報告存成 artifact。
- 之後可以接 Email、Google Sheets、Supabase。

目前雲端排程目標：

```text
08:30 盤前計畫，寫入每日報告。
09:30 盤中正式模擬交易，寫入帳本。
13:00 盤中風險參考，只產生 artifact，不改帳本。
14:30 盤後結算，寫入每日報告與結算帳本。
```

第二階段如果要有 24 小時 Dashboard，再考慮：

- Render
- Railway
- Fly.io
- Google Cloud Run
- VPS

## GitHub Actions 盤前盤中盤後排程

我已新增專用 workflow：

```text
.github/workflows/potential-stock-paper-trading.yml
```

台灣時間是 UTC+8。

建議排程：

```text
盤前：08:30 Asia/Taipei = 00:30 UTC
盤中正式交易：09:30 Asia/Taipei = 01:30 UTC
盤中風險參考：13:00 Asia/Taipei = 05:00 UTC
盤後結算：14:30 Asia/Taipei = 06:30 UTC
```

GitHub Actions cron：

```yaml
- cron: "30 0 * * 1-5"
- cron: "30 1 * * 1-5"
- cron: "0 5 * * 1-5"
- cron: "30 6 * * 1-5"
```

其中 `13:00` 這次排程會設定 `POTENTIAL_NO_PERSIST=true`，只產生參考報告，不改每日紀錄與正式帳本。

## 雲端需要的 Secrets

基本資料源：

```text
FINMIND_TOKEN
NEWS_API_KEY
OPENAI_API_KEY
OPENAI_MODEL
```

Email 報告：

```text
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASSWORD
SMTP_STARTTLS
REPORT_EMAIL_FROM
REPORT_EMAIL_TO
```

長期保存與績效追蹤建議用 Supabase：

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
UPDATE_SUPABASE=true
```

Google Sheet 簡易紀錄：

```text
GOOGLE_SERVICE_ACCOUNT_JSON
GOOGLE_SHEET_ID
UPDATE_GOOGLE_SHEET=true
```

## 上雲後的理想資料流

```text
GitHub Actions 盤前執行
-> 產生潛力股報告
-> 保存候選股與模擬操作
-> 寫入 Supabase / Google Sheets
-> Email 報告

GitHub Actions 盤後執行
-> 更新價格與操作狀況
-> 回朔驗證過去買進訊號
-> 更新績效摘要
-> Email 盤後檢討
```

## 手動跑雲端 workflow

到 GitHub repository：

```text
Actions -> Potential Stock Paper Trading -> Run workflow
```

可填：

```text
market_universe = semiconductor
symbols = 留空，使用預設半導體股票池
initial_capital = 1000000
max_positions = 5
report_session = auto、pre_market、market_hours 或 post_market
use_ai_analysis = false
```

`use_ai_analysis` 預設建議先用 `false`。等本機報告穩定後，再改成 `true`，讓 OpenAI 補充盤前/盤後深度解讀。交易規則與回測仍由固定規則控制，避免績效被 AI 文字波動影響。

跑完後下載 artifact：

```text
potential-stock-paper-trading
```

裡面會有：

- 潛力股模擬操作報告 Markdown
- 潛力股模擬操作報告 JSON
- 績效回朔 Markdown
- 績效回朔 JSON

## 下一階段開發目標

- 將潛力股報告接到 GitHub Actions 排程。
- 將 `potential_stock_runs.jsonl` 改成 Supabase 表格保存。
- 新增雲端績效報告 artifact。
- 新增 benchmark 比較。
- 新增持倉延續，不只是每次重新配置。
