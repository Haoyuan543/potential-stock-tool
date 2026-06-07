# Potential Stock Paper Trading Tool Goals

## Product Goal

Build this tool into a potential-stock discovery, paper-trading, and performance validation system.

The purpose is not to place real orders. The purpose is to repeatedly select promising stocks, simulate trades with configurable virtual capital, generate pre-market and post-market reports, and evaluate whether the tool's strategy performs well over time.

## Default Assumptions

- Default virtual capital: TWD 1,000,000.
- Market focus: Taiwan stocks first.
- Default stock universe: semiconductor stocks.
- The user can switch to AI/electronics, industrial/shipping, financial, or custom stock pools.
- Reports should be generated for weekdays before market, during market, and after market.
- Every recommendation must include reasons, risks, and data limitations.
- Every simulated trade must record the action reason for later review.

## MVP Scope

- [x] Requirement document and completion tracking.
- [x] Backend API for potential-stock screening and paper trading simulation.
- [x] Configurable initial virtual capital.
- [x] Configurable candidate stock list.
- [x] Potential score with basic component scores.
- [x] Paper portfolio output with cash, holdings, and account value.
- [x] Pre-market, intraday, and post-market markdown reports.
- [x] Per-stock basic, institutional, technical, operating, advantage, risk, and news summaries.
- [x] Frontend screen for running the MVP.
- [x] Show stock ticker with Chinese company name.
- [x] Configurable maximum holdings, default 5.
- [x] Replacement candidates when buy signals exceed holding limit.
- [x] Local snapshot persistence for potential-stock reports.
- [x] Daily pre-market/intraday/post-market operation tracking.
- [x] First performance lookback summary from saved snapshots.
- [x] Historical replay backtest for the potential-stock strategy.
- [x] Transaction fee, transaction tax, and slippage assumptions.
- [x] Carried positions inside historical replay.
- [x] Benchmark comparison inside historical replay.
- [x] Usage and cloud deployment guide.
- [x] Local acceptance checklist and test runner.
- [ ] Cloud deployment acceptance.
- [ ] Persist daily reports and simulated trades to Supabase.
- [x] Track ongoing local paper-trading performance across days with carried positions.
- [ ] Add scheduled weekday pre-market report.
- [ ] Add scheduled weekday intraday execution report.
- [ ] Add scheduled weekday intraday risk-reference report.
- [ ] Add scheduled weekday post-market settlement report.
- [x] Add strategy settings UI for stop-loss, take-profit, and max position size.
- [x] Add benchmark comparison against selected ETF in backtest and daily ledger summary.
- [x] Add backtest mode for the potential-stock strategy.

## Core Features

### 1. Potential Stock Discovery

The tool should screen candidate stocks and rank them by potential.

Signals to include:

- Revenue growth and operating improvement.
- EPS, margin, ROE, PER, PBR, dividend yield when available.
- Foreign, investment trust, and dealer flow.
- Price trend, moving averages, momentum, volume expansion, and breakout behavior.
- Industry theme or company-specific catalyst.
- Recent positive and negative news.
- Data quality and missing-data warnings.

### 2. Watchlist

For each selected stock, show:

- Ticker and company name when available.
- Potential score and rank.
- Entry reason.
- Suggested action: BUY, HOLD, WATCH, REDUCE, or AVOID.
- Risk level.
- Key triggers that would improve or invalidate the thesis.

### 3. Paper Trading

The tool should simulate trades with virtual capital.

Required fields:

- Initial capital.
- Cash.
- Holdings.
- Position market value.
- Total account value.
- Realized and unrealized P/L.
- Trade log.
- Action reason for every trade.

Default risk rules:

- Maximum one stock position: 20% of total capital.
- Buy only when potential score is high enough.
- Keep cash when no candidate is strong enough.
- Stop-loss and take-profit rules should be configurable in a later version.

### 4. Reports

Pre-market report should include:

- Market stance.
- Candidate ranking.
- Suggested watchlist.
- Planned buy, hold, or avoid actions.
- Key news and upcoming catalysts.
- Risk controls for the day.

Intraday report should include:

- Simulated trades based only on the same day's pre-market plan.
- Current-price plus slippage execution.
- Stop-loss, take-profit, hold, and replacement checks.
- Current holdings, cash, and total account value.
- One immutable executable intraday record per day.

Post-market report should include:

- Settlement and review only.
- Current holdings.
- Cash and total account value.
- What changed during the day.
- Stocks to continue watching tomorrow.
- Thesis changes and invalidation signals.
- No new buy trades that were not already executed intraday.

### 5. Per-Stock Analysis

Each candidate should include:

- Basic/fundamental view.
- Institutional/chip view.
- Technical view.
- Operating status.
- Recent advantages.
- Related news.
- Risks.
- Data limitations.

## Extra Items Worth Adding

- Strategy versioning so performance can be compared across strategy changes.
- Weekly and monthly review reports.
- Benchmark comparison.
- Drawdown monitoring.
- Win-rate and average holding-period metrics.
- Sector concentration limits.
- Transaction cost, tax, and slippage assumptions.
- Data source citations.
- Confidence score based on data quality.
- "Do nothing" recommendation when the data is weak.
- Export reports to Markdown, HTML, CSV, or Google Sheets.

## Completion Tracking

| Area | Status | Notes |
| --- | --- | --- |
| Requirements | Done | This document is the first tracking source. |
| Backend MVP | Done | `/api/potential-stocks` added. |
| Frontend MVP | Done | Main screen can run paper-trading simulation. |
| Local Persistence | Done | Potential-stock snapshots are saved locally. |
| Holding Limit | Done | Current simulation limits holdings to `max_positions`, default 5. |
| Replacement Candidates | Done | Extra buy-qualified stocks are listed as replacement candidates. |
| Daily Tracking | Done | Pre-market plans and post-market reviews can be paired by trading date. |
| Performance Lookback | Done | First version validates past buy signals against later snapshots. |
| Daily 3-Stage Flow | Done locally | 08:30 pre-market plan, 09:30 intraday execution, 13:00 reference-only risk check, 14:30 post-market settlement. |
| Local Acceptance | Done locally | See `LOCAL_ACCEPTANCE_CHECKLIST.md`; `RUN_LOCAL_TESTS.bat` passes locally. |
| Cloud Guide | Prepared | See `POTENTIAL_STOCK_USAGE_AND_CLOUD.md`; cloud acceptance deferred. |
| Supabase Persistence | Not started | Needed for durable cloud performance tracking. |
| Carried Portfolio | Done locally | Local JSONL ledger carries positions, cash, costs, holdings, strategy version, and initial capital by case. |
| Scheduling | Prepared | `.github/workflows/potential-stock-paper-trading.yml` now targets 08:30, 09:30, 13:00 reference-only, and 14:30 Taiwan time. Cloud acceptance is deferred. |
| Backtest | Done locally | `/api/potential-stocks/backtest` replays historical prices with costs and holdings. |
| Benchmark | Done locally | Backtest compares strategy return with the configured benchmark symbol. |
| Notifications | Not started | Optional after reports are stable. |

## Cloud Operation Target Record

Current local operating strategy:

```text
08:30 Asia/Taipei: Pre-market plan. Persist report only, no ledger trade.
09:30 Asia/Taipei: Intraday execution. Persist report and ledger. This is the only planned buy execution window.
13:00 Asia/Taipei: Intraday risk reference. Generate report artifact only, no ledger write.
14:30 Asia/Taipei: Post-market settlement. Persist report and settlement ledger, no new buy trades.
```

Cloud phase goals:

- [x] Prepare GitHub Actions workflow with four weekday Taiwan-time schedules.
- [x] Make the 13:00 scheduled run reference-only through `POTENTIAL_NO_PERSIST`.
- [ ] Decide durable storage: Supabase/Postgres first choice, SQLite acceptable for single-machine server only.
- [ ] Move JSONL reports, ledgers, cases, and active case state to durable cloud storage.
- [ ] Add file/database locking or transactional writes before running multiple schedules.
- [ ] Add cloud secrets: `FINMIND_TOKEN`, `NEWS_API_KEY`, `OPENAI_API_KEY`, optional `OPENAI_MODEL`.
- [ ] Run GitHub Actions manually for each session and inspect artifacts.
- [ ] Add notification target after reports are stable: email, Google Sheets, or dashboard.
- [ ] Add cloud acceptance checklist: no duplicate daily execution, ledger continuity, benchmark continuity, and old cases visible.
