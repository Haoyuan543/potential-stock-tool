from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app


def main() -> None:
    client = TestClient(app)

    home = client.get("/")
    assert home.status_code == 200
    for marker in [
        "scanButton",
        "preMarketButton",
        "intradayButton",
        "postMarketButton",
        "branchSummaryButton",
        "resetCaseButton",
        "branchSummaryOutput",
        "saveSettingsButton",
        "resetSettingsButton",
        "universeSummary",
        "maxPositionsInput",
        "ledgerOutput",
        "capitalLockHint",
        "actionStatus",
        "universe-option",
        "usageHelp",
        "usTechLeadingInput",
        "storageBackendInput",
        "switchStorageButton",
        "storageStatus",
        "納入前一晚美股科技/半導體領先因子",
        "potential-20260607-cloud-switch-auth",
    ]:
        assert marker in home.text

    app_js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    bad_text_markers = ["撠", "鞈", "銝", "蝘", "璅", "摰", "閮", "餈", "瘥", "嚗", "", "�"]
    for marker in bad_text_markers:
        assert marker not in home.text
        assert marker not in app_js
    for marker in [
        "潛力股模擬操作工具",
        "只抓潛力股參考分析",
        "盤前進行分析選股",
        "盤中執行模擬交易",
        "盤後結算今日結果",
        "產生支線總結",
        "建立全新支線",
        "儲存設定",
        "回到預設值",
    ]:
        assert marker in home.text
    assert home.text.index('id="dailyOutput"') < home.text.index('id="rankingOutput"')
    for marker in [
        'APP_VERSION = "potential-20260607-cloud-switch-auth"',
        'scanButton.addEventListener("click"',
        'intradayButton.addEventListener("click"',
        'resetCaseButton.addEventListener("click"',
        'saveSettingsButton.addEventListener("click"',
        'resetSettingsButton.addEventListener("click"',
        "localStorage",
        "updateUniverseSummary",
        "use_us_tech_leading",
        "美股科技領先",
        "美股領先",
        "籌碼品質",
        "tradeDetailLabel",
        "componentLabel",
        "data-delete-all-cases",
        "data-delete-case-id",
        'fetch("/api/potential-stocks/cases"',
        'method: "DELETE"',
        "Promise.all",
        "scrollIntoView",
        "ledgerOutput.scrollIntoView",
        "selected-case-row",
        "data-close-case-view",
        "data-track-case-id",
        "loadBranchSummary",
        "loadStorageStatus",
        "switchStorageBackend",
        "/api/storage/status",
        "/api/storage/backend",
        "Supabase 雲端資料",
        "本機資料",
        "switchTrackedCase",
        "renderBranchSummary",
        "classified-section",
        "caseGroupTable",
        "關閉目前查看",
        "ledgerRowsForRecord",
        "groupLedgerRecordsByDate",
        "groupLedgerRecordsByDateVersion",
        "ledgerDateVersionSummary",
        "ledgerSessionBlocksForGroup",
        "ledgerDateSummary",
        "ledgerSessionBlock",
        "ledgerGroupSummary",
        "ledgerActionSections",
        "ledger-collapse-list",
        "dailyStatusSummaryTable",
        "holdingsStatusTable",
        "fundStatusTable",
        "profitLossStatusTable",
        "accountSummarySection",
        "目前持股",
        "資金狀況",
        "損益狀況",
        "損益率",
        "累計損益",
        "未實現損益",
        "已實現損益",
    ]:
        assert marker in app_js

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["backend_version"] == "potential-20260607-market-hours"
    assert health.json()["storage"]["backend"] in {"local", "supabase"}

    storage_status = client.get("/api/storage/status")
    assert storage_status.status_code == 200
    assert storage_status.json()["backend"] in {"local", "supabase"}

    switch_storage = client.post("/api/storage/backend", json={"backend": "local"})
    assert switch_storage.status_code == 200
    assert switch_storage.json()["backend"] == "local"

    main_py = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    assert "Delete actions are allowed only from localhost or with CRON_JOB_SECRET" in main_py
    assert "dashboard_basic_auth" in main_py
    assert "/api/storage/backend" in main_py
    storage_py = (ROOT / "backend" / "services" / "storage.py").read_text(encoding="utf-8")
    assert "SupabaseJsonStore" in storage_py
    assert "StoreProxy" in storage_py
    assert "set_runtime_storage_backend" in storage_py
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "STORAGE_BACKEND" in env_example
    assert "DASHBOARD_PASSWORD" in env_example
    assert "potential_stock_supabase.sql" in (ROOT / "CLOUD_SUPABASE_STEPS.md").read_text(encoding="utf-8")
    assert (ROOT / "Dockerfile").exists()
    assert (ROOT / "render.yaml").exists()
    assert (ROOT / "database" / "potential_stock_supabase.sql").exists()
    service_py = (ROOT / "backend" / "services" / "potential_stock_service.py").read_text(encoding="utf-8")
    assert "今日不交易" in service_py
    assert "_should_plan_trade_today" in service_py

    scan = client.post(
        "/api/potential-stocks",
        json={
            "market_universe": "semiconductor",
            "market_universes": ["semiconductor", "financial"],
            "initial_capital": 1_000_000,
            "max_positions": 5,
            "report_session": "market_hours",
            "use_live_data": False,
            "persist": False,
        },
    )
    payload = scan.json()
    assert scan.status_code == 200
    assert payload["report_session"] == "market_hours"
    assert payload["analyses"][0]["company_name"]
    for field in [
        "component_scores",
        "technical_summary",
        "fundamental_summary",
        "institutional_summary",
        "operating_summary",
        "us_market_summary",
        "advantages",
        "risks",
        "related_news",
        "thesis",
    ]:
        assert field in payload["analyses"][0]
    assert "us_tech_leading" in payload["analyses"][0]["component_scores"]
    assert "smart_money_quality" in payload["analyses"][0]["component_scores"]
    assert payload["portfolio"]["holdings"] == []
    assert "replacement_suggestions" in payload["portfolio"]

    daily_status = client.get("/api/potential-stocks/daily-status")
    assert daily_status.status_code == 200
    assert "每日盤前盤中盤後追蹤" in daily_status.json()["markdown"]

    cases = client.get("/api/potential-stocks/cases")
    assert cases.status_code == 200
    assert "active_case_id" in cases.json()

    performance = client.get("/api/potential-stocks/performance")
    assert performance.status_code == 200

    branch_summary = client.get("/api/potential-stocks/branch-summary")
    assert branch_summary.status_code == 200
    assert "metrics" in branch_summary.json()
    assert "review" in branch_summary.json()

    print("LOCAL SMOKE OK")


if __name__ == "__main__":
    main()
