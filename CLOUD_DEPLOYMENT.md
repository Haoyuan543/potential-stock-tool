# 雲端排程與寄信部署指南

這份專案可以拆成兩種雲端使用方式：

1. **每日自動分析並寄 Email**：建議先用 GitHub Actions。成本低，不需要自己的電腦開著。
2. **長時間在線 Dashboard**：之後再部署到 Render、Railway、Fly.io、Google Cloud Run 或 VPS。

目前已先完成第 1 種：GitHub Actions 每天固定時間執行分析，產生 Markdown / HTML / JSON 報告，並可寄到你的信箱。

## 已新增的檔案

- `.github/workflows/daily-analysis.yml`
- `backend/jobs/daily_analysis_email.py`

## GitHub Actions 的運作方式

流程如下：

1. GitHub 到指定時間自動啟動一台臨時雲端機器。
2. 安裝 Python 套件與 Playwright Chromium。
3. 執行 `python -m backend.jobs.daily_analysis_email`。
4. 即時抓股價、法人、SCFI、新聞、公告、國際事件。
5. 呼叫 OpenAI 產生報告。
6. 儲存報告為 Markdown、HTML、JSON。
7. 如果 SMTP 設定完整，就寄 Email 給你。
8. 報告也會上傳成 GitHub Actions artifact，可在 GitHub 頁面下載。

## 預設排程時間

目前設定為：

```text
台灣時間 16:40，週一到週五
```

對應 GitHub Actions 的 UTC cron：

```text
40 8 * * 1-5
```

如果你想改成台灣時間早上 08:30：

```text
30 0 * * 1-5
```

如果你想改成台灣時間晚上 20:00：

```text
0 12 * * 1-5
```

## 你需要在 GitHub 設定的 Secrets

到 GitHub repository：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

至少需要：

```text
OPENAI_API_KEY
FINMIND_TOKEN
NEWS_API_KEY
```

建議也設定：

```text
OPENAI_MODEL=gpt-5
SERPAPI_API_KEY
BRAVE_SEARCH_API_KEY
TAVILY_API_KEY
```

搜尋 API 不是全部都必須，但至少有一個會比只靠 RSS 穩定。

## Email 寄送設定

如果使用 Gmail，請使用「應用程式密碼」，不要使用你的 Gmail 登入密碼。

GitHub Secrets 範例：

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=你的 Gmail
SMTP_PASSWORD=你的 Gmail 應用程式密碼
SMTP_STARTTLS=true
REPORT_EMAIL_FROM=你的 Gmail
REPORT_EMAIL_TO=收報告的信箱
```

如果你不用 Gmail，也可以用 SendGrid、Mailgun、Amazon SES、Outlook SMTP。

## 手動測試

推上 GitHub 後：

1. 打開 repository 的 `Actions`
2. 選 `Daily AI Investment Analysis`
3. 按 `Run workflow`
4. symbol 填 `2603.TW`
5. mode 選 `personalized`
6. send_email 填 `true`

跑完後可以在 workflow 頁面下載 `scheduled-analysis-report`。

## 本機測試排程腳本

不寄信，只產生報告：

```bash
SEND_EMAIL=false python -m backend.jobs.daily_analysis_email
```

寄信：

```bash
python -m backend.jobs.daily_analysis_email --send-email
```

Windows PowerShell 範例：

```powershell
$env:SEND_EMAIL="false"
.\.venv\Scripts\python.exe -m backend.jobs.daily_analysis_email
```

## 是否一定要 GitHub？

不一定。

最推薦順序：

1. **GitHub Actions**：最適合每日固定時間跑分析和寄信。
2. **Render / Railway / Fly.io**：適合讓 Dashboard 24 小時在線。
3. **Google Cloud Run + Cloud Scheduler**：正式產品化比較穩，但設定較多。
4. **VPS**：彈性最大，但需要自己維護系統。

## GitHub Actions 的限制

- 它不是長時間在線伺服器。
- 它適合「到時間跑一次、寄報告、結束」。
- 免費額度和使用限制會依 GitHub 帳號方案變動。
- 歷史紀錄若只存在 runner 機器，下一次不會自動保留；目前會用 artifact 保留每次輸出。

## 下一步建議

最實用的下一步是把每日報告同步到雲端儲存：

- Google Drive
- Dropbox
- S3 / Cloudflare R2
- GitHub Pages
- Supabase / PostgreSQL

這樣才能做長期績效追蹤、7/30/90 天預測驗證、回測統計。
