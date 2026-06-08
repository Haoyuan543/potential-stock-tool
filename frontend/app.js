const apiStatus = document.querySelector("#apiStatus");
const notice = document.querySelector("#notice");
const scanButton = document.querySelector("#scanButton");
const preMarketButton = document.querySelector("#preMarketButton");
const intradayButton = document.querySelector("#intradayButton");
const postMarketButton = document.querySelector("#postMarketButton");
const branchSummaryButton = document.querySelector("#branchSummaryButton");
const resetCaseButton = document.querySelector("#resetCaseButton");
const downloadButton = document.querySelector("#downloadButton");
const copyButton = document.querySelector("#copyButton");
const loadingBox = document.querySelector("#loadingBox");
const elapsedTimer = document.querySelector("#elapsedTimer");
const rankingOutput = document.querySelector("#rankingOutput");
const tradeOutput = document.querySelector("#tradeOutput");
const replacementOutput = document.querySelector("#replacementOutput");
const reportOutput = document.querySelector("#reportOutput");
const dailyOutput = document.querySelector("#dailyOutput");
const branchSummaryOutput = document.querySelector("#branchSummaryOutput");
const ledgerOutput = document.querySelector("#ledgerOutput");
const caseOutput = document.querySelector("#caseOutput");
const marketStance = document.querySelector("#marketStance");
const totalValue = document.querySelector("#totalValue");
const cashValue = document.querySelector("#cashValue");
const investedValue = document.querySelector("#investedValue");
const universeInput = document.querySelector("#universeInput");
const universeOptions = Array.from(document.querySelectorAll(".universe-option"));
const symbolsInput = document.querySelector("#symbolsInput");
const symbolsHint = document.querySelector("#symbolsHint");
const capitalInput = document.querySelector("#capitalInput");
const capitalLockHint = document.querySelector("#capitalLockHint");
const actionStatus = document.querySelector("#actionStatus");
const universeSummary = document.querySelector("#universeSummary");
const saveSettingsButton = document.querySelector("#saveSettingsButton");
const resetSettingsButton = document.querySelector("#resetSettingsButton");
const storageBackendInput = document.querySelector("#storageBackendInput");
const switchStorageButton = document.querySelector("#switchStorageButton");
const storageStatus = document.querySelector("#storageStatus");
const APP_VERSION = "potential-20260608-dynamic-universe-stable-v1";
const SETTINGS_KEY = "potentialStockToolSettings";

const universeSymbols = {
  semiconductor: ["2330.TW", "2454.TW", "2303.TW", "2379.TW", "3034.TW", "3711.TW", "3443.TW", "3661.TW"],
  electronics: ["2317.TW", "2382.TW", "3231.TW", "2356.TW", "6669.TW", "3017.TW", "2308.TW", "4938.TW"],
  industrial: ["2603.TW", "2609.TW", "2615.TW", "2002.TW", "1301.TW", "1303.TW", "1513.TW", "2049.TW"],
  financial: ["2881.TW", "2882.TW", "2884.TW", "2885.TW", "2886.TW", "2891.TW", "2892.TW", "5876.TW"]
};

const DEFAULT_SETTINGS = {
  symbols: "",
  market_universes: ["semiconductor", "electronics"],
  initial_capital: 3000000,
  max_positions: 5,
  candidate_limit: 10,
  max_position_pct: 20,
  buy_score: 70,
  risk_reward_profile: "balanced",
  investment_horizon: "mid_term_3m",
  watch_score: 55,
  sell_score: 50,
  stop_loss_pct: 8,
  take_profit_pct: 20,
  swap_score_gap: 10,
  min_hold_days: 3,
  strategy_version: "potential-v1",
  fee_rate: 0.1425,
  tax_rate: 0.3,
  slippage_bps: 5,
  benchmark_symbol: "0050.TW",
  use_live_data: true,
  use_dynamic_universe: true,
  use_us_tech_leading: true,
  use_ai_analysis: false
};

let latestReport = "";
let timerId = null;
let startedAt = 0;
let selectedCaseId = "";
let activeCaseId = "";
let resetConfirmUntil = 0;

universeOptions.forEach((option) => option.addEventListener("change", syncUniverseSelection));
symbolsInput.addEventListener("input", () => {
  universeInput.value = "custom";
  const custom = universeOptions.find((option) => option.value === "custom");
  if (custom) custom.checked = true;
  updateUniverseSummary();
  updateSymbolsFieldState();
});

scanButton.addEventListener("click", () => runPotentialStocks("market_hours", { persist: false, referenceOnly: true }));
preMarketButton.addEventListener("click", () => runPotentialStocks("pre_market"));
intradayButton.addEventListener("click", () => runPotentialStocks("market_hours"));
postMarketButton.addEventListener("click", () => runPotentialStocks("post_market"));
branchSummaryButton.addEventListener("click", () => loadBranchSummary(selectedCaseId || activeCaseId));
resetCaseButton.addEventListener("click", resetCase);
saveSettingsButton.addEventListener("click", saveSettingsToCloudV2);
resetSettingsButton.addEventListener("click", resetSettingsToDefaultV2);
if (switchStorageButton) switchStorageButton.addEventListener("click", switchStorageBackend);
downloadButton.addEventListener("click", downloadMarkdown);
copyButton.addEventListener("click", async () => {
  if (!latestReport) return;
  await navigator.clipboard.writeText(latestReport);
  showNotice("報告已複製。", "ok");
});

caseOutput.addEventListener("click", async (event) => {
  const deleteAllButton = event.target.closest("[data-delete-all-cases]");
  if (deleteAllButton) {
    await deleteAllCases();
    return;
  }
  const trackButton = event.target.closest("[data-track-case-id]");
  if (trackButton) {
    await switchTrackedCase(trackButton.getAttribute("data-track-case-id") || "default");
    return;
  }
  const deleteButton = event.target.closest("[data-delete-case-id]");
  if (deleteButton) {
    await deleteCase(deleteButton.getAttribute("data-delete-case-id") || "");
    return;
  }
  const button = event.target.closest("[data-case-id]");
  if (!button) return;
  selectedCaseId = button.getAttribute("data-case-id") || "default";
  button.disabled = true;
  button.textContent = "載入中...";
  showActionStatus(`正在查看案件 ${selectedCaseId}...`, "partial");
  try {
    await Promise.all([loadDailyStatus(false, selectedCaseId), loadLedger(selectedCaseId), loadCases()]);
    showActionStatus(`已切換到案件 ${selectedCaseId}。`, "ok");
    ledgerOutput.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    button.disabled = false;
    button.textContent = "查看";
    showActionStatus(`查看案件失敗：${friendlyError(error.message)}`, "missing");
  }
});

applySavedSettings();
checkHealth();

async function checkHealth() {
  try {
    const response = await fetch(apiUrl("/health"));
    const json = await response.json();
    const backendVersion = json.backend_version ? ` | 後端 ${json.backend_version}` : "";
    apiStatus.textContent = json.ok ? `服務正常 | 前端 ${APP_VERSION}${backendVersion}` : `服務異常 | 前端 ${APP_VERSION}${backendVersion}`;
    apiStatus.className = json.ok ? "status-pill ok-pill" : "status-pill bad-pill";
    if (!json.finmind_configured) {
      showNotice("FinMind token 尚未設定；即時資料可能不足，盤前/盤中結果會偏向保守。", "partial");
    }
    await loadStorageStatus();
    await loadCloudSettings();
    await loadCases();
    await loadDailyStatus(false);
    await loadLedger();
  } catch (error) {
    apiStatus.textContent = `API 無法連線 | 前端 ${APP_VERSION}`;
    apiStatus.className = "status-pill bad-pill";
    showNotice(`API 連線失敗：${friendlyError(error.message)}`, "missing");
  }
}

async function loadStorageStatus() {
  if (!storageBackendInput || !storageStatus) return;
  try {
    const response = await fetch(apiUrl("/api/storage/status"));
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    storageBackendInput.value = result.backend || "local";
    const backendLabel = result.backend === "supabase" ? "Supabase 雲端資料" : "本機資料";
    const configuredText = result.supabase_configured ? "Supabase 已設定" : "Supabase 尚未設定";
    const overrideText = result.runtime_override ? "目前為啟動後手動切換" : "目前使用環境預設";
    storageStatus.textContent = `目前讀取：${backendLabel}；${configuredText}；${overrideText}`;
  } catch (error) {
    storageStatus.textContent = `資料來源狀態讀取失敗：${friendlyError(error.message)}`;
  }
}

async function switchStorageBackend() {
  if (!storageBackendInput || !switchStorageButton) return;
  const backend = storageBackendInput.value || "local";
  switchStorageButton.disabled = true;
  showActionStatus(`正在切換資料來源到 ${backend === "supabase" ? "Supabase 雲端資料" : "本機資料"}...`, "partial");
  try {
    const response = await fetch(apiUrl("/api/storage/backend"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backend })
    });
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    selectedCaseId = "";
    activeCaseId = "";
    await loadStorageStatus();
    await loadCloudSettings();
    await loadCases();
    await loadDailyStatus(false);
    await loadLedger();
    await loadBranchSummary("");
    const label = result.backend === "supabase" ? "Supabase 雲端資料" : "本機資料";
    showNotice(`已切換為 ${label}，畫面資料已重新讀取。`, "ok");
    showActionStatus(`已切換為 ${label}`, "ok");
  } catch (error) {
    showNotice(`切換資料來源失敗：${friendlyError(error.message)}`, "missing");
    showActionStatus(`切換資料來源失敗：${friendlyError(error.message)}`, "missing");
    await loadStorageStatus();
  } finally {
    switchStorageButton.disabled = false;
  }
}

async function runPotentialStocks(reportSession, options = {}) {
  const label = options.referenceOnly ? "參考掃描" : reportSession === "pre_market" ? "盤前選股" : reportSession === "market_hours" ? "盤中模擬交易" : "盤後結算";
  setLoading(true, label);
  showNotice(`${label}處理中，正在取得資料並產生分析...`, "partial");
  showActionStatus(`${label}處理中...`, "partial");
  try {
    const response = await fetch(apiUrl("/api/potential-stocks"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readInputs(reportSession, options))
    });
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    latestReport = result.markdown || "";
    renderSummary(result);
    renderRanking(result.analyses || []);
    renderTrades(result.portfolio?.trades || []);
    renderReplacements(result.portfolio?.replacement_suggestions || []);
    renderMarkdown(reportOutput, latestReport);
    downloadButton.disabled = !latestReport;
    copyButton.disabled = !latestReport;
    const immutableMessage = (result.data_limitations || []).some((item) => String(item).includes("已有不可變紀錄"));
    const message = options.referenceOnly
      ? "參考掃描完成；未寫入每日紀錄或帳本。"
      : immutableMessage
        ? "今天已有此階段紀錄，系統回傳原紀錄，未改動交易資料。"
        : reportSession === "post_market"
          ? "盤後結算完成；已更新帳戶狀態與今日結果。"
          : `${label}完成。`;
    showNotice(message, "ok");
    showActionStatus(message, "ok");
    selectedCaseId = options.referenceOnly ? activeCaseId : "";
    await loadCases();
    await loadDailyStatus(false);
    await loadLedger();
  } catch (error) {
    const message = friendlyError(error.message);
    latestReport = `# 分析失敗\n\n${message}`;
    renderMarkdown(reportOutput, latestReport);
    showNotice(`分析失敗：${message}`, "missing");
    showActionStatus(`分析失敗：${message}`, "missing");
  } finally {
    setLoading(false);
  }
}

async function loadDailyStatus(showSuccess = false, caseId = selectedCaseId) {
  try {
    const query = caseId ? `?limit=30&case_id=${encodeURIComponent(caseId)}` : "?limit=30";
    const response = await fetch(apiUrl(`/api/potential-stocks/daily-status${query}`));
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    renderDailyTable(result.days || [], result.active_case_id || caseId || "");
    if (showSuccess) showNotice("每日狀況已更新。", "ok");
  } catch (error) {
    dailyOutput.innerHTML = `<p class="empty-state">每日狀況載入失敗：${escapeHtml(friendlyError(error.message))}</p>`;
  }
}

async function loadCases() {
  try {
    const response = await fetch(apiUrl("/api/potential-stocks/cases"));
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    activeCaseId = result.active_case_id || "";
    if (!selectedCaseId) selectedCaseId = activeCaseId;
    renderCaseTable(result.cases || [], activeCaseId, selectedCaseId);
    applyCapitalLock(result.cases || [], activeCaseId);
  } catch (error) {
    caseOutput.innerHTML = `<p class="empty-state">案件列表載入失敗：${escapeHtml(friendlyError(error.message))}</p>`;
  }
}

async function loadLedger(caseId = selectedCaseId) {
  try {
    const query = caseId ? `?limit=80&case_id=${encodeURIComponent(caseId)}` : "?limit=80";
    const response = await fetch(apiUrl(`/api/potential-stocks/ledger${query}`));
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    renderLedgerTable(result.records || [], caseId || activeCaseId || "");
  } catch (error) {
    ledgerOutput.innerHTML = `<p class="empty-state">帳本載入失敗：${escapeHtml(friendlyError(error.message))}</p>`;
  }
}

async function loadBranchSummary(caseId = selectedCaseId || activeCaseId) {
  const target = caseId || activeCaseId || "";
  showActionStatus(`正在產生支線總結 ${target || "default"}...`, "partial");
  try {
    const query = target ? `?case_id=${encodeURIComponent(target)}` : "";
    const response = await fetch(apiUrl(`/api/potential-stocks/branch-summary${query}`));
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    renderBranchSummary(result);
    latestReport = result.markdown || latestReport;
    downloadButton.disabled = !latestReport;
    copyButton.disabled = !latestReport;
    showActionStatus(`支線總結已完成：${target || result.active_case_id || "default"}。`, "ok");
    branchSummaryOutput.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    branchSummaryOutput.innerHTML = `<p class="empty-state">支線總結失敗：${escapeHtml(friendlyError(error.message))}</p>`;
    showActionStatus(`支線總結失敗：${friendlyError(error.message)}`, "missing");
  }
}

function applyCapitalLock(cases, caseId) {
  const active = cases.find((item) => item.case_id === caseId || item.active);
  const locked = Boolean(active?.capital_locked);
  const initialCapital = Number(active?.initial_capital);
  if (Number.isFinite(initialCapital) && initialCapital > 0) {
    capitalInput.value = String(Math.round(initialCapital));
  }
  capitalInput.disabled = locked;
  capitalLockHint.textContent = locked
    ? "此案件已有紀錄，模擬資金已鎖定；請重置案件後再調整新資金。"
    : "新案件開始前可調整；產生盤前、盤中或盤後紀錄後會鎖定。";
}

async function resetCase() {
  const now = Date.now();
  if (now > resetConfirmUntil) {
    resetConfirmUntil = now + 8000;
    resetCaseButton.textContent = "再按一次確認重置";
    showNotice("重置會開始新案件，舊資料會保留但不再直接追蹤。8 秒內再按一次確認。", "partial");
    showActionStatus("等待第二次確認重置。", "partial");
    window.setTimeout(() => {
      if (Date.now() > resetConfirmUntil) {
        resetConfirmUntil = 0;
        resetCaseButton.textContent = "重置案件重新追蹤";
      }
    }, 8200);
    return;
  }
  resetConfirmUntil = 0;
  setLoading(true, "重置案件");
  try {
    const response = await fetch(apiUrl("/api/potential-stocks/cases/reset"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: "手動重置，開始新的模擬追蹤。" })
    });
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    selectedCaseId = result.active_case_id || "";
    activeCaseId = result.active_case_id || "";
    showNotice(`已開始新案件 ${result.active_case_id}，舊案件 ${result.archived_case_id} 已保留。`, "ok");
    showActionStatus(`已開始新案件 ${result.active_case_id}。`, "ok");
    await loadCases();
    await loadDailyStatus(false);
    await loadLedger();
  } catch (error) {
    showNotice(`重置案件失敗：${friendlyError(error.message)}`, "missing");
    showActionStatus(`重置案件失敗：${friendlyError(error.message)}`, "missing");
  } finally {
    setLoading(false);
  }
}

async function deleteCase(caseId) {
  const target = caseId || "default";
  if (!window.confirm(`確定刪除案件 ${target}？此動作會刪除該案件的每日紀錄與帳本，無法復原。`)) return;
  showActionStatus(`正在刪除案件 ${target}...`, "partial");
  try {
    const response = await fetch(apiUrl(`/api/potential-stocks/cases/${encodeURIComponent(target)}`), { method: "DELETE" });
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    selectedCaseId = result.active_case_id || "";
    activeCaseId = result.active_case_id || "";
    showActionStatus(`已刪除 ${target}：${result.deleted_reports || 0} 筆報告、${result.deleted_ledgers || 0} 筆帳本。`, "ok");
    await loadCases();
    await loadDailyStatus(false);
    await loadLedger();
  } catch (error) {
    showActionStatus(`刪除案件失敗：${friendlyError(error.message)}`, "missing");
  }
}

async function deleteAllCases() {
  if (!window.confirm("確定刪除全部潛力股資料？這會清除所有測試與正式案件的每日紀錄和帳本，無法復原。")) return;
  showActionStatus("正在刪除全部資料...", "partial");
  try {
    const response = await fetch(apiUrl("/api/potential-stocks/cases"), { method: "DELETE" });
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    selectedCaseId = result.active_case_id || "default";
    activeCaseId = result.active_case_id || "default";
    showActionStatus(`已刪除全部資料：${result.deleted_reports || 0} 筆報告、${result.deleted_ledgers || 0} 筆帳本、${result.deleted_case_records || 0} 筆案件。`, "ok");
    await loadCases();
    await loadDailyStatus(false);
    await loadLedger();
  } catch (error) {
    showActionStatus(`全部刪除失敗：${friendlyError(error.message)}`, "missing");
  }
}

async function switchTrackedCase(caseId) {
  const target = caseId || "default";
  showActionStatus(`正在切換目前追蹤支線 ${target}...`, "partial");
  try {
    const response = await fetch(apiUrl("/api/potential-stocks/cases/switch"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: target })
    });
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    activeCaseId = result.active_case_id || target;
    selectedCaseId = activeCaseId;
    showNotice(`已切換目前追蹤支線：${activeCaseId}。後續盤前、盤中、盤後會以此支線為主。`, "ok");
    showActionStatus(`目前追蹤支線已切換為 ${activeCaseId}。`, "ok");
    await loadCases();
    await loadDailyStatus(false, selectedCaseId);
    await loadLedger(selectedCaseId);
  } catch (error) {
    showActionStatus(`切換支線失敗：${friendlyError(error.message)}`, "missing");
  }
}

function applySavedSettings() {
  let settings = DEFAULT_SETTINGS;
  try {
    const saved = JSON.parse(window.localStorage.getItem(SETTINGS_KEY) || "null");
    if (saved && typeof saved === "object") {
      settings = { ...DEFAULT_SETTINGS, ...saved };
    }
  } catch {
    settings = DEFAULT_SETTINGS;
  }
  applySettings(settings, { includeCapital: !capitalInput.disabled });
}

async function saveSettingsToCloudV2() {
  try {
    updateSymbolsFieldState();
    await persistCurrentSettings();
    showNotice("設定已儲存；雲端排程會讀取這份設定。", "ok");
    showActionStatus("設定已儲存到目前資料來源。", "ok");
  } catch (error) {
    showNotice(`設定儲存失敗：${friendlyError(error.message)}`, "missing");
    showActionStatus(`設定儲存失敗：${friendlyError(error.message)}`, "missing");
  }
}

async function resetSettingsToDefaultV2() {
  try {
    window.localStorage.removeItem(SETTINGS_KEY);
  } catch {
    // localStorage may be unavailable in private or restricted browser contexts.
  }
  applySettings(DEFAULT_SETTINGS, { includeCapital: !capitalInput.disabled });
  updateSymbolsFieldState();
  try {
    await persistCurrentSettings();
    showNotice(capitalInput.disabled ? "已回到預設設定；資金欄位因目前案件已鎖定，需建立新支線後才能調整。" : "已回到預設設定並儲存。", "ok");
    showActionStatus("預設設定已儲存到目前資料來源。", "ok");
  } catch (error) {
    showNotice(`回到預設值失敗：${friendlyError(error.message)}`, "missing");
    showActionStatus(`回到預設值失敗：${friendlyError(error.message)}`, "missing");
  }
}

async function persistCurrentSettings() {
  const settings = collectSettings();
  try {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // localStorage may be unavailable in private or restricted browser contexts.
  }
  const response = await fetch(apiUrl("/api/potential-stocks/settings"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(readInputs("pre_market", { persist: true }))
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

async function loadCloudSettings() {
  try {
    const response = await fetch(apiUrl("/api/potential-stocks/settings"));
    if (!response.ok) throw new Error(await readApiError(response));
    const result = await response.json();
    const settings = apiSettingsToUi(result.settings || {});
    try {
      window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch {
      // localStorage may be unavailable in private or restricted browser contexts.
    }
    applySettings({ ...DEFAULT_SETTINGS, ...settings }, { includeCapital: !capitalInput.disabled });
  } catch (error) {
    showActionStatus(`雲端設定讀取失敗，先使用本機設定：${friendlyError(error.message)}`, "partial");
  }
}

function apiUrl(path) {
  return `${window.location.protocol}//${window.location.host}${path}`;
}

async function readApiError(response) {
  const text = await response.text();
  const status = response?.status ? `HTTP ${response.status}` : "API";
  return `${status}：${friendlyError(text)}`;
}

async function saveSettingsToCloud() {
  const settings = collectSettings();
  try {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    const response = await fetch(apiUrl("/api/potential-stocks/settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readInputs("pre_market", { persist: true }))
    });
    if (!response.ok) throw new Error(await readApiError(response));
    showNotice("設定已儲存；雲端排程會讀取這份設定。", "ok");
    showActionStatus("設定已儲存到目前資料來源。", "ok");
  } catch (error) {
    showNotice(`設定儲存失敗：${friendlyError(error.message)}`, "missing");
    showActionStatus(`設定儲存失敗：${friendlyError(error.message)}`, "missing");
  }
}

function saveSettings() {
  const settings = collectSettings();
  try {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    showNotice("設定已儲存在此瀏覽器。", "ok");
    showActionStatus("設定已儲存；下次開啟會自動套用。", "ok");
  } catch (error) {
    showNotice(`設定儲存失敗：${friendlyError(error.message)}`, "missing");
    showActionStatus(`設定儲存失敗：${friendlyError(error.message)}`, "missing");
  }
}

function resetSettingsToDefault() {
  try {
    window.localStorage.removeItem(SETTINGS_KEY);
  } catch {
    // localStorage may be unavailable in private or restricted browser contexts.
  }
  applySettings(DEFAULT_SETTINGS, { includeCapital: !capitalInput.disabled });
  showNotice(capitalInput.disabled ? "已回到預設設定；模擬資金因目前案件已有紀錄而維持鎖定。" : "已回到預設設定。", "ok");
  showActionStatus("欄位已回到預設值。", "ok");
}

function collectSettings() {
  const selectedUniverses = selectedUniverseValues();
  const useCustomSymbols = selectedUniverses.includes("custom");
  return {
    symbols: useCustomSymbols ? symbolsInput.value : "",
    market_universes: selectedUniverses,
    initial_capital: numberValue("#capitalInput", DEFAULT_SETTINGS.initial_capital),
    max_positions: numberValue("#maxPositionsInput", DEFAULT_SETTINGS.max_positions),
    candidate_limit: numberValue("#candidateLimitInput", DEFAULT_SETTINGS.candidate_limit),
    max_position_pct: numberValue("#positionCapInput", DEFAULT_SETTINGS.max_position_pct),
    buy_score: numberValue("#buyScoreInput", DEFAULT_SETTINGS.buy_score),
    risk_reward_profile: document.querySelector("#riskRewardInput").value,
    investment_horizon: document.querySelector("#horizonInput").value,
    watch_score: numberValue("#watchScoreInput", DEFAULT_SETTINGS.watch_score),
    sell_score: numberValue("#sellScoreInput", DEFAULT_SETTINGS.sell_score),
    stop_loss_pct: numberValue("#stopLossInput", DEFAULT_SETTINGS.stop_loss_pct),
    take_profit_pct: numberValue("#takeProfitInput", DEFAULT_SETTINGS.take_profit_pct),
    swap_score_gap: numberValue("#swapGapInput", DEFAULT_SETTINGS.swap_score_gap),
    min_hold_days: numberValue("#minHoldDaysInput", DEFAULT_SETTINGS.min_hold_days),
    strategy_version: document.querySelector("#strategyVersionInput").value.trim() || DEFAULT_SETTINGS.strategy_version,
    fee_rate: numberValue("#feeRateInput", DEFAULT_SETTINGS.fee_rate),
    tax_rate: numberValue("#taxRateInput", DEFAULT_SETTINGS.tax_rate),
    slippage_bps: numberValue("#slippageInput", DEFAULT_SETTINGS.slippage_bps),
    benchmark_symbol: document.querySelector("#benchmarkInput").value.trim() || DEFAULT_SETTINGS.benchmark_symbol,
    use_live_data: document.querySelector("#liveDataInput").checked,
    use_dynamic_universe: true,
    use_us_tech_leading: document.querySelector("#usTechLeadingInput")?.checked !== false,
    use_ai_analysis: document.querySelector("#aiAnalysisInput").checked
  };
}

function applySettings(settings, options = {}) {
  const includeCapital = options.includeCapital !== false;
  if (includeCapital) capitalInput.value = String(settings.initial_capital || DEFAULT_SETTINGS.initial_capital);
  setValue("#maxPositionsInput", settings.max_positions);
  setValue("#candidateLimitInput", settings.candidate_limit);
  setValue("#positionCapInput", settings.max_position_pct);
  setValue("#buyScoreInput", settings.buy_score);
  setValue("#riskRewardInput", settings.risk_reward_profile);
  setValue("#horizonInput", settings.investment_horizon);
  setValue("#watchScoreInput", settings.watch_score);
  setValue("#sellScoreInput", settings.sell_score);
  setValue("#stopLossInput", settings.stop_loss_pct);
  setValue("#takeProfitInput", settings.take_profit_pct);
  setValue("#swapGapInput", settings.swap_score_gap);
  setValue("#minHoldDaysInput", settings.min_hold_days);
  setValue("#strategyVersionInput", settings.strategy_version);
  setValue("#feeRateInput", settings.fee_rate);
  setValue("#taxRateInput", settings.tax_rate);
  setValue("#slippageInput", settings.slippage_bps);
  setValue("#benchmarkInput", settings.benchmark_symbol);
  setChecked("#liveDataInput", settings.use_live_data);
  setChecked("#usTechLeadingInput", settings.use_us_tech_leading);
  setChecked("#aiAnalysisInput", settings.use_ai_analysis);
  const universes = Array.isArray(settings.market_universes) && settings.market_universes.length ? settings.market_universes : DEFAULT_SETTINGS.market_universes;
  universeOptions.forEach((option) => {
    option.checked = universes.includes(option.value);
  });
  universeInput.value = universes[0] || "semiconductor";
  updateUniverseSummary();
  if (universes.includes("custom")) {
    const explicitSymbols = settings.symbols || "";
    symbolsInput.value = Array.isArray(explicitSymbols) ? explicitSymbols.join(", ") : String(explicitSymbols);
  } else {
    symbolsInput.value = "";
  }
  updateSymbolsFieldState();
}

function apiSettingsToUi(settings) {
  const merged = { ...DEFAULT_SETTINGS, ...(settings || {}) };
  return {
    ...merged,
    symbols: Array.isArray(merged.symbols) ? merged.symbols.join(", ") : String(merged.symbols || ""),
    max_position_pct: percentFromApi(merged.max_position_pct, DEFAULT_SETTINGS.max_position_pct),
    stop_loss_pct: percentFromApi(merged.stop_loss_pct, DEFAULT_SETTINGS.stop_loss_pct),
    take_profit_pct: percentFromApi(merged.take_profit_pct, DEFAULT_SETTINGS.take_profit_pct),
    fee_rate: percentFromApi(merged.fee_rate, DEFAULT_SETTINGS.fee_rate),
    tax_rate: percentFromApi(merged.tax_rate, DEFAULT_SETTINGS.tax_rate)
  };
}

function percentFromApi(value, fallback) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return number <= 1 ? Number((number * 100).toFixed(4)) : number;
}

function setValue(selector, value) {
  const element = document.querySelector(selector);
  if (element && value !== undefined && value !== null) element.value = String(value);
}

function setChecked(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.checked = Boolean(value);
}

function readInputs(reportSession, options = {}) {
  const selectedUniverses = selectedUniverseValues();
  const useCustomSymbols = selectedUniverses.includes("custom");
  const symbols = useCustomSymbols ? symbolsInput.value.split(/[,\n\s]+/).map((item) => item.trim()).filter(Boolean) : [];
  return {
    symbols,
    market_universe: selectedUniverses[0] || "semiconductor",
    market_universes: selectedUniverses,
    initial_capital: numberValue("#capitalInput", DEFAULT_SETTINGS.initial_capital),
    max_positions: numberValue("#maxPositionsInput", 5),
    candidate_limit: numberValue("#candidateLimitInput", 10),
    max_position_pct: numberValue("#positionCapInput", 20) / 100,
    buy_score: numberValue("#buyScoreInput", 70),
    risk_reward_profile: document.querySelector("#riskRewardInput").value,
    investment_horizon: document.querySelector("#horizonInput").value,
    watch_score: numberValue("#watchScoreInput", 55),
    sell_score: numberValue("#sellScoreInput", 50),
    stop_loss_pct: numberValue("#stopLossInput", 8) / 100,
    take_profit_pct: numberValue("#takeProfitInput", 20) / 100,
    swap_score_gap: numberValue("#swapGapInput", 10),
    min_hold_days: numberValue("#minHoldDaysInput", 3),
    fee_rate: numberValue("#feeRateInput", 0.1425) / 100,
    tax_rate: numberValue("#taxRateInput", 0.3) / 100,
    slippage_bps: numberValue("#slippageInput", 5),
    benchmark_symbol: document.querySelector("#benchmarkInput").value.trim() || "0050.TW",
    strategy_version: document.querySelector("#strategyVersionInput").value.trim() || "potential-v1",
    report_session: reportSession,
    use_live_data: document.querySelector("#liveDataInput").checked,
    use_dynamic_universe: true,
    use_us_tech_leading: document.querySelector("#usTechLeadingInput")?.checked !== false,
    use_ai_analysis: document.querySelector("#aiAnalysisInput").checked,
    persist: options.persist !== undefined ? Boolean(options.persist) : true
  };
}

function selectedUniverseValues() {
  const values = universeOptions.filter((option) => option.checked).map((option) => option.value);
  return values.length ? values : ["semiconductor"];
}

function syncSymbolsFromUniverseSelection() {
  updateSymbolsFieldState();
}

function syncUniverseSelection(event) {
  const changed = event?.target;
  if (changed?.value === "custom" && changed.checked) {
    universeInput.value = "custom";
    updateUniverseSummary();
    return;
  }
  const selected = selectedUniverseValues();
  universeInput.value = selected[0] || "semiconductor";
  updateUniverseSummary();
  updateSymbolsFieldState();
}

function updateUniverseSummary() {
  const labels = {
    semiconductor: "半導體",
    electronics: "AI / 電子股",
    industrial: "傳產 / 航運",
    financial: "金融股",
    custom: "自訂股票池"
  };
  const selected = selectedUniverseValues().map((value) => labels[value] || value);
  universeSummary.textContent = selected.length <= 2 ? selected.join("、") : `${selected.slice(0, 2).join("、")} +${selected.length - 2}`;
}

function updateSymbolsFieldState() {
  const useCustomSymbols = selectedUniverseValues().includes("custom");
  symbolsInput.disabled = !useCustomSymbols;
  symbolsInput.classList.toggle("muted-input", !useCustomSymbols);
  if (!useCustomSymbols) {
    symbolsInput.value = "";
    symbolsInput.placeholder = "目前使用 TWSE / TPEx 動態市場 universe，不會被固定股票池限制。";
    if (symbolsHint) symbolsHint.textContent = "目前使用動態市場 universe；盤前會從勾選類別產生候選，再選出前 10 檔。";
    return;
  }
  symbolsInput.placeholder = "例如：2330.TW, 2454.TW, 2303.TW";
  if (symbolsHint) symbolsHint.textContent = "已啟用自訂股票池；系統只會把這裡的代號加入分析範圍。";
}

function renderSummary(result) {
  const portfolio = result.portfolio || {};
  marketStance.textContent = result.market_stance || "--";
  totalValue.textContent = money(portfolio.total_value);
  cashValue.textContent = money(portfolio.cash);
  investedValue.textContent = money(portfolio.invested_value);
}

function renderRanking(analyses) {
  if (!analyses.length) {
    rankingOutput.className = "ranking-list empty-state";
    rankingOutput.textContent = "尚未產生排行。";
    return;
  }
  rankingOutput.className = "ranking-list";
  rankingOutput.innerHTML = analyses.map((item, index) => `
    <article class="rank-row">
      <div class="rank-number">${index + 1}</div>
      <div>
        <div class="rank-title">
          <strong>${escapeHtml(stockLabel(item))}</strong>
          <span class="action ${escapeAttr((item.action || "").toLowerCase())}">${escapeHtml(actionLabel(item.action))}</span>
        </div>
        <p>${escapeHtml(item.thesis || "")}</p>
        ${analysisQuickFacts(item)}
        <div class="score-bar" aria-label="score"><span style="width:${Math.max(0, Math.min(100, item.score || 0))}%"></span></div>
        <dl class="component-grid">
          ${Object.entries(item.component_scores || {}).map(([key, value]) => `
            <div><dt>${escapeHtml(componentLabel(key))}</dt><dd>${escapeHtml(value)}</dd></div>
          `).join("")}
        </dl>
        <details class="analysis-detail">
          <summary>查看技術面、基本面、籌碼面與評分理由</summary>
          <div class="reason-box">
            <strong>評分理由</strong>
            <p>${escapeHtml(item.thesis || "尚無完整投資論點。")}</p>
          </div>
          <div class="detail-grid">
            ${detailBlock("技術面", item.technical_summary)}
            ${detailBlock("美股科技領先", item.us_market_summary)}
            ${detailBlock("基本面", item.fundamental_summary)}
            ${detailBlock("籌碼面", item.institutional_summary)}
            ${detailBlock("營運面", item.operating_summary)}
            ${detailBlock("近期優勢", item.advantages)}
            ${detailBlock("分數拆解", item.score_explanation)}
            ${detailBlock("相關新聞", item.related_news)}
            ${detailBlock("新聞/事件衝擊", item.news_impact_summary)}
            ${evidenceLinksBlock(item.evidence_links)}
            ${detailBlock("風險", item.risks)}
            ${detailBlock("資料限制", item.data_limitations)}
          </div>
        </details>
      </div>
    </article>
  `).join("");
}

function analysisQuickFacts(item) {
  const strengths = [
    ...(item.technical_summary || []),
    ...(item.us_market_summary || []),
    ...(item.advantages || []),
  ].filter(Boolean).slice(0, 3);
  const risks = [
    ...(item.risks || []),
    ...(item.data_limitations || []),
  ].filter(Boolean).slice(0, 2);
  return `
    <div class="analysis-quick-facts">
      <span><strong>建議資金</strong>${money(item.suggested_capital || 0)}</span>
      <span><strong>股數</strong>${escapeHtml(item.suggested_shares || 0)}</span>
      <span><strong>最新價</strong>${escapeHtml(item.latest_price || "--")}</span>
      <span><strong>重點</strong>${escapeHtml(strengths.join("；") || "尚無明確優勢")}</span>
      <span><strong>風險</strong>${escapeHtml(risks.join("；") || "尚無明確風險")}</span>
    </div>
  `;
}

function detailBlock(title, values) {
  const items = Array.isArray(values) && values.length ? values : ["尚無資料"];
  return `
    <section class="detail-block">
      <h3>${escapeHtml(title)}</h3>
      <ul>${items.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul>
    </section>
  `;
}

function evidenceLinksBlock(links) {
  const items = Array.isArray(links) ? links.filter((item) => item && item.url).slice(0, 5) : [];
  if (!items.length) return detailBlock("資料來源連結", ["尚無可追溯連結"]);
  return `
    <section class="detail-block evidence-links">
      <h3>資料來源連結</h3>
      <ul>
        ${items.map((item) => `
          <li>
            <a href="${escapeAttr(item.url)}" target="_blank" rel="noopener noreferrer">
              ${escapeHtml(item.tier_label || item.source || "來源")}｜${escapeHtml(item.title || item.url)}
            </a>
            <small>${escapeHtml(item.source || "")} · 可信度 ${escapeHtml(item.credibility || "--")}</small>
          </li>
        `).join("")}
      </ul>
    </section>
  `;
}

function renderTrades(trades) {
  if (!trades.length) {
    tradeOutput.className = "trade-list empty-state";
    tradeOutput.textContent = "尚未產生操作記錄。";
    return;
  }
  tradeOutput.className = "trade-list";
  tradeOutput.innerHTML = trades.map((trade) => `
    <article class="trade-row">
      <div>
        <strong>${escapeHtml(stockLabel(trade))}</strong>
        <span class="action ${escapeAttr((trade.action || "").toLowerCase())}">${escapeHtml(actionLabel(trade.action))}</span>
      </div>
      <p>${escapeHtml(trade.reason || "")}</p>
      <small>${escapeHtml(tradeDetailLabel(trade))}</small>
    </article>
  `).join("");
}

function renderReplacements(items) {
  if (!items.length) {
    replacementOutput.className = "trade-list empty-state";
    replacementOutput.textContent = "沒有換股候選。";
    return;
  }
  replacementOutput.className = "trade-list";
  replacementOutput.innerHTML = items.map((item) => `
    <article class="trade-row">
      <div>
        <strong>${escapeHtml(stockLabel(item))}</strong>
        <span class="action watch">候選</span>
      </div>
      <p>${escapeHtml(item.reason || "")}</p>
      <small>分數 ${escapeHtml(item.score || "--")} / 價格 ${escapeHtml(item.price || "--")}</small>
    </article>
  `).join("");
}

renderDailyTable = function(days, caseId = "") {
  if (!days.length) {
    dailyOutput.innerHTML = `<p class="empty-state">${escapeHtml(caseId || "目前案件")} 尚未有每日資料；請先執行盤前、盤中或盤後流程。</p>`;
    return;
  }
  dailyOutput.innerHTML = `
    <p class="case-context">目前查看：${escapeHtml(caseId || "--")}</p>
    <table class="daily-table">
      <thead>
        <tr>
          <th>日期</th>
          <th>盤前</th>
          <th>盤前預計</th>
          <th>盤中</th>
          <th>盤中操作</th>
          <th>盤後</th>
          <th>盤後結算</th>
          <th>帳戶淨值</th>
        </tr>
      </thead>
      <tbody>${days.map((day) => dailyRow(day)).join("")}</tbody>
    </table>
  `;
};

function dailyRow(day) {
  const pre = day.pre_market;
  const intraday = day.market_hours;
  const post = day.post_market;
  const preTrades = plannedTrades(pre);
  const intradayTrades = executedTrades(intraday);
  const postTrades = executedTrades(post);
  const total = post?.portfolio?.total_value ?? intraday?.portfolio?.total_value ?? pre?.portfolio?.total_value;
  return `
    <tr>
      <td>${escapeHtml(day.date || "--")}</td>
      <td>${pre ? "已完成" : "未完成"}</td>
      <td>${escapeHtml(preTrades || "--")}</td>
      <td>${intraday ? "已完成" : "未完成"}</td>
      <td>${escapeHtml(intradayTrades || "--")}</td>
      <td>${post ? "已完成" : "未完成"}</td>
      <td>${escapeHtml(postTrades || "--")}</td>
      <td>${money(total)}</td>
    </tr>
  `;
}

renderLedgerTable = function(records, caseId = "") {
  if (!records.length) {
    ledgerOutput.innerHTML = `<p class="empty-state">${escapeHtml(caseId || "目前案件")} 尚未有正式帳本；盤中模擬交易或盤後結算後才會出現。</p>`;
    return;
  }
  const rows = [...records].reverse().flatMap((record) => {
    const trades = record.trades || [];
    if (!trades.length) {
      return [{
        generated_at: record.generated_at,
        trading_date: record.trading_date,
        report_session: record.report_session,
        action: "SNAPSHOT",
        symbol: "--",
        company_name: "",
        shares: 0,
        price: null,
        amount: 0,
        total_value: record.total_value,
        reason: "盤後帳戶快照"
      }];
    }
    return trades.map((trade) => ({
      ...trade,
      generated_at: record.generated_at,
      trading_date: record.trading_date,
      report_session: record.report_session,
      total_value: record.total_value
    }));
  }).slice(0, 120);

  ledgerOutput.innerHTML = `
    <p class="case-context">目前查看：${escapeHtml(caseId || "--")}</p>
    <table class="daily-table">
      <thead>
        <tr>
          <th>日期</th>
          <th>階段</th>
          <th>動作</th>
          <th>股票</th>
          <th>股數</th>
          <th>價格</th>
          <th>金額</th>
          <th>帳戶淨值</th>
          <th>原因</th>
        </tr>
      </thead>
      <tbody>${rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.trading_date || String(row.generated_at || "").slice(0, 10) || "--")}</td>
          <td>${escapeHtml(sessionLabel(row.report_session))}</td>
          <td>${escapeHtml(actionLabel(row.action))}</td>
          <td>${escapeHtml(stockLabel(row))}</td>
          <td>${escapeHtml(row.shares || 0)}</td>
          <td>${row.price === null || row.price === undefined ? "--" : escapeHtml(Number(row.price).toFixed(2))}</td>
          <td>${money(row.amount)}</td>
          <td>${money(row.total_value)}</td>
          <td>${escapeHtml(row.reason || "--")}</td>
        </tr>
      `).join("")}</tbody>
    </table>
  `;
};

friendlyError = function(message) {
  const text = String(message || "").trim();
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) return parsed.detail.map((item) => item.msg || JSON.stringify(item)).join("；");
    if (typeof parsed.message === "string") return parsed.message;
  } catch (_) {
    // Keep the original text fallback below.
  }
  const plain = text
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const sample = plain || text;
  if (/502|bad gateway/i.test(sample)) {
    return "雲端服務暫時回傳 502 Bad Gateway，通常是 Render 正在重啟、部署或請求超時。請稍後重新整理，或到 Render Logs 查看錯誤。";
  }
  if (/504|gateway timeout|timeout/i.test(sample)) {
    return "雲端請求逾時，可能是資料抓取太久或 Render 冷啟動。請稍後重試，或改用 background=true 背景排程。";
  }
  if (text.includes("Supabase") && text.includes("failed")) return text;
  if (text.includes("Internal Server Error")) return "後端執行失敗，請重新整理後查看 /health 與 Render Logs 找詳細錯誤。";
  if (text.includes("report_session") && text.includes("market_hours")) {
    return "後端尚未接受盤中參數 market_hours，請確認雲端已部署最新版。";
  }
  return sample ? (sample.length > 220 ? `${sample.slice(0, 220)}...` : sample) : "未知錯誤";
};

renderCaseTable = function(cases, active, current = "") {
  if (!cases.length) {
    caseOutput.innerHTML = '<p class="empty-state">尚無案件資料。</p>';
    return;
  }
  caseOutput.innerHTML = `
    <div class="table-toolbar">
      <span>目前查看：${escapeHtml(current || active || "default")}</span>
      <button type="button" class="danger-button small-button" data-delete-all-cases="true">全部刪除測試資料</button>
    </div>
    <table class="daily-table">
      <thead>
        <tr>
          <th>狀態</th>
          <th>案件</th>
          <th>查看</th>
          <th>刪除</th>
          <th>建立時間</th>
          <th>記錄數</th>
          <th>追蹤日期</th>
          <th>最新淨值</th>
        </tr>
      </thead>
      <tbody>
        ${cases.map((item) => `
          <tr class="${item.case_id === current ? "selected-case-row" : ""}">
            <td>${item.case_id === active || item.active ? "目前追蹤" : "已保留"}</td>
            <td>${escapeHtml(item.case_name || item.case_id || "--")}<br><small>${escapeHtml(item.case_id || "--")}</small>${item.case_id === current ? "<br><small>每日表目前顯示此案件</small>" : ""}</td>
            <td>
              <div class="row-actions">
                <button type="button" class="small-button" data-case-id="${escapeAttr(item.case_id || "")}">${item.case_id === current ? "查看中" : "查看"}</button>
                <button type="button" class="small-button" data-track-case-id="${escapeAttr(item.case_id || "default")}">${item.case_id === active || item.active ? "追蹤中" : "切換追蹤"}</button>
              </div>
            </td>
            <td><button type="button" class="small-button danger-button" data-delete-case-id="${escapeAttr(item.case_id || "default")}">刪除</button></td>
            <td>${escapeHtml(item.created_at || "--")}</td>
            <td>${escapeHtml(item.report_count || 0)} 筆報告 / ${escapeHtml(item.ledger_count || 0)} 筆帳本</td>
            <td>${escapeHtml(dateRange(item))}</td>
            <td>${money(item.latest_account_value)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
};

function plannedTrades(record) {
  return ((record?.portfolio?.trades || [])
    .filter((trade) => trade.action === "PLAN_BUY")
    .map((trade) => tradeDetailLabel(trade)))
    .join("；");
}

function executedTrades(record) {
  return ((record?.portfolio?.trades || [])
    .filter((trade) => ["BUY", "SELL", "HOLD"].includes(trade.action))
    .slice(0, 8)
    .map((trade) => `${actionLabel(trade.action)} ${tradeDetailLabel(trade)}`))
    .join("；");
}

function tradeDetailLabel(trade) {
  const shares = Number(trade?.shares || 0);
  const lots = shares ? shares / 1000 : 0;
  const lotText = shares ? `${Number.isInteger(lots) ? lots : lots.toFixed(2)} 張 / ${shares} 股` : "未配置股數";
  const price = trade?.price === null || trade?.price === undefined ? "價格未定" : `價格 ${Number(trade.price).toFixed(2)}`;
  const amount = Number(trade?.amount || 0) > 0 ? `金額 ${money(trade.amount)}` : "金額未定";
  return `${stockLabel(trade)}，${lotText}，${price}，${amount}`;
}

function renderMarkdown(target, markdown) {
  target.innerHTML = markdownToHtml(markdown);
}

function markdownToHtml(markdown) {
  const lines = String(markdown || "").split("\n");
  let html = "";
  let inList = false;
  for (const line of lines) {
    if (line.startsWith("### ")) {
      if (inList) html += "</ul>";
      inList = false;
      html += `<h3>${formatInline(line.slice(4))}</h3>`;
    } else if (line.startsWith("## ")) {
      if (inList) html += "</ul>";
      inList = false;
      html += `<h2>${formatInline(line.slice(3))}</h2>`;
    } else if (line.startsWith("# ")) {
      if (inList) html += "</ul>";
      inList = false;
      html += `<h1>${formatInline(line.slice(2))}</h1>`;
    } else if (line.startsWith("- ") || /^\s+- /.test(line)) {
      if (!inList) html += "<ul>";
      inList = true;
      html += `<li>${formatInline(line.replace(/^\s*-\s/, ""))}</li>`;
    } else if (!line.trim()) {
      if (inList) html += "</ul>";
      inList = false;
    } else {
      if (inList) html += "</ul>";
      inList = false;
      html += `<p>${formatInline(line)}</p>`;
    }
  }
  if (inList) html += "</ul>";
  return html || '<p class="empty-state">尚無報告。</p>';
}

function setLoading(isLoading, label = "處理") {
  scanButton.disabled = isLoading;
  preMarketButton.disabled = isLoading;
  intradayButton.disabled = isLoading;
  postMarketButton.disabled = isLoading;
  branchSummaryButton.disabled = isLoading;
  resetCaseButton.disabled = isLoading;
  scanButton.textContent = isLoading ? `${label}中...` : "只抓潛力股參考分析";
  preMarketButton.textContent = isLoading ? `${label}中...` : "盤前進行分析選股";
  intradayButton.textContent = isLoading ? `${label}中...` : "盤中執行模擬交易";
  postMarketButton.textContent = isLoading ? `${label}中...` : "盤後結算今日結果";
  branchSummaryButton.textContent = isLoading ? `${label}中...` : "產生支線總結";
  resetCaseButton.textContent = isLoading ? `${label}中...` : "建立全新支線";
  loadingBox.classList.toggle("hidden", !isLoading);
  if (isLoading) {
    startedAt = performance.now();
    elapsedTimer.textContent = "0.0";
    timerId = window.setInterval(() => {
      elapsedTimer.textContent = ((performance.now() - startedAt) / 1000).toFixed(1);
    }, 100);
  } else if (timerId) {
    window.clearInterval(timerId);
    timerId = null;
  }
}

function downloadMarkdown() {
  if (!latestReport) return;
  const stamp = new Date().toISOString().replaceAll(":", "-").slice(0, 19);
  const blob = new Blob([latestReport], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `潛力股模擬報告-${stamp}.md`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function showNotice(text, tone = "") {
  notice.textContent = text;
  notice.className = `notice ${tone}`;
  notice.classList.remove("hidden");
}

function showActionStatus(text, tone = "") {
  actionStatus.textContent = text;
  actionStatus.className = `action-status ${tone}`;
  actionStatus.classList.remove("hidden");
}

function friendlyError(message) {
  const text = String(message || "").trim();
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) return parsed.detail.map((item) => item.msg || JSON.stringify(item)).join("；");
    if (typeof parsed.message === "string") return parsed.message;
  } catch (_) {
    // Keep the original text fallback below.
  }
  const plain = text
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const sample = plain || text;
  if (/502|bad gateway/i.test(sample)) {
    return "雲端服務暫時回傳 502 Bad Gateway，通常是 Render 正在重啟、部署或請求超時。請稍後重新整理，或到 Render Logs 查看錯誤。";
  }
  if (/504|gateway timeout|timeout/i.test(sample)) {
    return "雲端請求逾時，可能是資料抓取太久或 Render 冷啟動。請稍後重試，或改用 background=true 背景排程。";
  }
  if (text.includes("report_session") && text.includes("market_hours")) {
    return "後端要求盤中代碼必須是 market_hours；請重新整理頁面後再試。";
  }
  if (text.includes("Internal Server Error")) return "後端執行失敗，請重新整理後查看 /health 與 Render Logs 找詳細錯誤。";
  return sample ? (sample.length > 220 ? `${sample.slice(0, 220)}...` : sample) : "未知錯誤";
}

function numberValue(selector, fallback) {
  const element = document.querySelector(selector);
  const value = Number(element?.value);
  return Number.isFinite(value) ? value : fallback;
}

function money(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "--";
  return `NT$${new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 0 }).format(Number(value))}`;
}

function stockLabel(item) {
  return item?.company_name ? `${item.symbol} ${item.company_name}` : item?.symbol || "--";
}

function dateRange(item) {
  if (item.first_trading_date && item.last_trading_date) {
    return item.first_trading_date === item.last_trading_date ? item.first_trading_date : `${item.first_trading_date} ~ ${item.last_trading_date}`;
  }
  return "--";
}

function actionLabel(action) {
  return { PLAN_BUY: "預計買進", BUY: "買進", HOLD: "續抱", WATCH: "觀察", AVOID: "避開", SELL: "賣出", SNAPSHOT: "快照" }[action] || action || "--";
}

function sessionLabel(session) {
  return { pre_market: "盤前", market_hours: "盤中", post_market: "盤後" }[session] || session || "--";
}

function componentLabel(key) {
  return { technical: "技術面", fundamental: "基本面", institutional: "籌碼面", smart_money_quality: "籌碼品質", news: "新聞面", event_intel: "事件情報", us_tech_leading: "美股領先", data_quality: "資料品質" }[key] || key;
}

function formatInline(value) {
  return escapeHtml(value).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

document.addEventListener("click", async (event) => {
  const closeButton = event.target.closest("[data-close-case-view]");
  if (!closeButton) return;
  selectedCaseId = activeCaseId || "";
  if (branchSummaryOutput) {
    branchSummaryOutput.innerHTML = '<p class="empty-state">已關閉支線總結。選取支線後可重新產生。</p>';
  }
  showActionStatus("已關閉目前查看內容，回到目前追蹤案件。", "ok");
  await Promise.all([loadDailyStatus(false, selectedCaseId), loadLedger(selectedCaseId), loadCases()]);
});

function caseViewToolbar(caseId, countText = "") {
  const isArchivedView = caseId && caseId !== activeCaseId;
  return `
    <div class="table-toolbar case-view-toolbar">
      <span>目前查看：${escapeHtml(caseId || activeCaseId || "default")}${countText ? `　${escapeHtml(countText)}` : ""}</span>
      ${isArchivedView ? '<button type="button" class="small-button" data-close-case-view="true">關閉目前查看</button>' : ""}
    </div>
  `;
}

function renderDailyTable(days, caseId = "") {
  if (!days.length) {
    dailyOutput.innerHTML = `
      ${caseViewToolbar(caseId)}
      <p class="empty-state">${escapeHtml(caseId || "目前案件")} 尚未有每日資料；請先執行盤前、盤中或盤後流程。</p>
    `;
    return;
  }
  dailyOutput.innerHTML = `
    ${caseViewToolbar(caseId, `共 ${days.length} 天`)}
    <details class="classified-section" open>
      <summary>每日盤前 / 盤中 / 盤後狀況</summary>
      <table class="daily-table">
        <thead>
          <tr>
            <th>日期</th>
            <th>盤前</th>
            <th>盤前預計</th>
            <th>盤中</th>
            <th>盤中操作</th>
            <th>盤後</th>
            <th>盤後結算</th>
            <th>帳戶淨值</th>
          </tr>
        </thead>
        <tbody>${days.map((day) => dailyRow(day)).join("")}</tbody>
      </table>
    </details>
  `;
}

function renderLedgerTable(records, caseId = "") {
  if (!records.length) {
    ledgerOutput.innerHTML = `
      ${caseViewToolbar(caseId)}
      <p class="empty-state">${escapeHtml(caseId || "目前案件")} 尚未有正式帳本；盤中模擬交易或盤後結算後才會出現。</p>
    `;
    return;
  }
  const rows = [...records].reverse().flatMap((record) => {
    const trades = record.trades || [];
    if (!trades.length) {
      return [{
        generated_at: record.generated_at,
        trading_date: record.trading_date,
        report_session: record.report_session,
        action: "SNAPSHOT",
        symbol: "--",
        company_name: "",
        shares: 0,
        price: null,
        amount: 0,
        total_value: record.total_value,
        reason: "盤後帳戶快照"
      }];
    }
    return trades.map((trade) => ({
      ...trade,
      generated_at: record.generated_at,
      trading_date: record.trading_date,
      report_session: record.report_session,
      total_value: record.total_value
    }));
  }).slice(0, 160);

  const groups = [
    ["market_hours", "盤中模擬交易"],
    ["post_market", "盤後結算 / 快照"],
    ["pre_market", "盤前計畫"],
    ["other", "其他紀錄"]
  ].map(([key, label]) => {
    const items = rows.filter((row) => key === "other" ? !["market_hours", "post_market", "pre_market"].includes(row.report_session) : row.report_session === key);
    return { key, label, items };
  }).filter((group) => group.items.length);

  ledgerOutput.innerHTML = `
    ${caseViewToolbar(caseId, `共 ${rows.length} 筆`)}
    <div class="classified-list">
      ${groups.map((group, index) => `
        <details class="classified-section" ${index === 0 ? "open" : ""}>
          <summary>${escapeHtml(group.label)}（${group.items.length} 筆）</summary>
          <table class="daily-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>階段</th>
                <th>動作</th>
                <th>股票</th>
                <th>股數</th>
                <th>價格</th>
                <th>金額</th>
                <th>帳戶淨值</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>${group.items.map((row) => ledgerRow(row)).join("")}</tbody>
          </table>
        </details>
      `).join("")}
    </div>
  `;
}

function ledgerRow(row) {
  return `
    <tr>
      <td>${escapeHtml(row.trading_date || String(row.generated_at || "").slice(0, 10) || "--")}</td>
      <td>${escapeHtml(sessionLabel(row.report_session))}</td>
      <td>${escapeHtml(actionLabel(row.action))}</td>
      <td>${escapeHtml(stockLabel(row))}</td>
      <td>${escapeHtml(row.shares || 0)}</td>
      <td>${row.price === null || row.price === undefined ? "--" : escapeHtml(Number(row.price).toFixed(2))}</td>
      <td>${money(row.amount)}</td>
      <td>${money(row.total_value)}</td>
      <td>${escapeHtml(row.reason || "--")}</td>
    </tr>
  `;
}

function renderCaseTable(cases, active, current = "") {
  if (!cases.length) {
    caseOutput.innerHTML = '<p class="empty-state">尚無案件資料。</p>';
    return;
  }
  const activeCases = cases.filter((item) => item.case_id === active || item.active);
  const archivedCases = cases.filter((item) => !(item.case_id === active || item.active));
  caseOutput.innerHTML = `
    <div class="table-toolbar">
      <span>目前查看：${escapeHtml(current || active || "default")}</span>
      <div class="toolbar-actions">
        ${current && current !== active ? '<button type="button" class="small-button" data-close-case-view="true">關閉目前查看</button>' : ""}
        <button type="button" class="danger-button small-button" data-delete-all-cases="true">全部刪除測試資料</button>
      </div>
    </div>
    <div class="classified-list">
      ${caseGroupTable("目前追蹤案件", activeCases, active, current, true)}
      ${caseGroupTable("已保留案件", archivedCases, active, current, false)}
    </div>
  `;
}

function caseGroupTable(title, cases, active, current, open) {
  return `
    <details class="classified-section" ${open ? "open" : ""}>
      <summary>${escapeHtml(title)}（${cases.length} 筆）</summary>
      ${cases.length ? `
        <table class="daily-table">
          <thead>
            <tr>
              <th>狀態</th>
              <th>案件</th>
              <th>查看</th>
              <th>刪除</th>
              <th>建立時間</th>
              <th>記錄數</th>
              <th>追蹤日期</th>
              <th>最新淨值</th>
            </tr>
          </thead>
          <tbody>${cases.map((item) => caseRow(item, active, current)).join("")}</tbody>
        </table>
      ` : '<p class="empty-state compact-empty">此分類目前沒有案件。</p>'}
    </details>
  `;
}

function caseRow(item, active, current) {
  const isActive = item.case_id === active || item.active;
  const isCurrent = item.case_id === current;
  return `
    <tr class="${isCurrent ? "selected-case-row" : ""}">
      <td>${isActive ? "目前追蹤" : "已保留"}</td>
      <td>${escapeHtml(item.case_name || item.case_id || "--")}<br><small>${escapeHtml(item.case_id || "--")}</small>${isCurrent ? "<br><small>每日表目前顯示此案件</small>" : ""}</td>
      <td>
        <div class="row-actions">
          <button type="button" class="small-button" data-case-id="${escapeAttr(item.case_id || "")}">${isCurrent ? "查看中" : "查看"}</button>
          <button type="button" class="small-button" data-track-case-id="${escapeAttr(item.case_id || "default")}">${isActive ? "追蹤中" : "切換追蹤"}</button>
        </div>
      </td>
      <td><button type="button" class="small-button danger-button" data-delete-case-id="${escapeAttr(item.case_id || "default")}">刪除</button></td>
      <td>${escapeHtml(item.created_at || "--")}</td>
      <td>${escapeHtml(item.report_count || 0)} 筆報告 / ${escapeHtml(item.ledger_count || 0)} 筆帳本</td>
      <td>${escapeHtml(dateRange(item))}</td>
      <td>${money(item.latest_account_value)}</td>
    </tr>
  `;
}

function renderBranchSummary(result) {
  const metrics = result.metrics || {};
  const review = result.review || {};
  const tables = result.tables || {};
  branchSummaryOutput.innerHTML = `
    <div class="table-toolbar">
      <span>支線：${escapeHtml(result.active_case_id || metrics.case_id || "--")}　結論：${escapeHtml(review.conclusion || "--")}</span>
      <button type="button" class="small-button" data-close-case-view="true">關閉目前查看</button>
    </div>
    <div class="classified-list">
      <details class="classified-section" open>
        <summary>量化統計</summary>
        ${simpleTable(["指標", "數值"], (tables.metrics || []).map((row) => [row.name, row.value]))}
      </details>
      <details class="classified-section" open>
        <summary>流程紀錄統計</summary>
        ${simpleTable(["階段", "次數"], (tables.sessions || []).map((row) => [row.name, row.count]))}
      </details>
      <details class="classified-section" open>
        <summary>交易統計</summary>
        ${simpleTable(["項目", "次數"], (tables.trades || []).map((row) => [row.name, row.count]))}
      </details>
      <details class="classified-section" open>
        <summary>策略自我審查</summary>
        <div class="review-grid">
          ${reviewBlock("目前優勢", review.strengths)}
          ${reviewBlock("發現問題", review.issues)}
          ${reviewBlock("修正建議", review.fixes)}
        </div>
      </details>
    </div>
  `;
}

function simpleTable(headers, rows) {
  if (!rows.length) return '<p class="empty-state compact-empty">尚無資料。</p>';
  return `
    <table class="daily-table">
      <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.map((row) => `<tr>${row.map((value) => `<td>${escapeHtml(value ?? "--")}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
}

function reviewBlock(title, values) {
  const items = Array.isArray(values) && values.length ? values : ["尚無資料"];
  return `
    <section class="detail-block">
      <h3>${escapeHtml(title)}</h3>
      <ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>
  `;
}

function statusText(done) {
  return done ? "已完成" : "未完成";
}

function statusClass(done) {
  return done ? "status-chip done" : "status-chip pending";
}

function pctText(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "--";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function sharesText(value) {
  const shares = Number(value || 0);
  if (!shares) return "0";
  if (shares >= 1000 && shares % 1000 === 0) return `${shares / 1000} 張 / ${shares} 股`;
  return `${shares} 股`;
}

function portfolioFromDay(day) {
  return day?.portfolio_snapshot || day?.post_market?.portfolio || day?.market_hours?.portfolio || day?.pre_market?.portfolio || {};
}

function tradesFromRecord(record, actions = []) {
  const wanted = new Set(actions);
  return ((record || {}).portfolio || {}).trades?.filter((trade) => !actions.length || wanted.has(trade.action)) || [];
}

function compactTradeSummary(record, actions = []) {
  const trades = tradesFromRecord(record, actions);
  if (!trades.length) return "--";
  return trades.slice(0, 4).map((trade) => {
    const amount = trade.amount === undefined || trade.amount === null ? "" : `，${money(trade.amount)}`;
    return `${actionLabel(trade.action)} ${stockLabel(trade)} ${sharesText(trade.shares)}，${trade.price ? Number(trade.price).toFixed(2) : "--"}${amount}`;
  }).join("；");
}

function dailyStatusSummaryTable(day) {
  const portfolio = portfolioFromDay(day);
  return `
    <table class="daily-table compact-table">
      <thead>
        <tr>
          <th>日期</th>
          <th>盤前</th>
          <th>盤中</th>
          <th>盤後</th>
          <th>帳戶淨值</th>
          <th>現金</th>
          <th>持股市值</th>
          <th>持倉數</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>${escapeHtml(day.date || "--")}</td>
          <td><span class="${statusClass(day.has_pre_market)}">${statusText(day.has_pre_market)}</span></td>
          <td><span class="${statusClass(day.has_market_hours)}">${statusText(day.has_market_hours)}</span></td>
          <td><span class="${statusClass(day.has_post_market)}">${statusText(day.has_post_market)}</span></td>
          <td>${money(portfolio.total_value)}</td>
          <td>${money(portfolio.cash)}</td>
          <td>${money(portfolio.invested_value)}</td>
          <td>${escapeHtml((portfolio.holdings || []).length)}</td>
        </tr>
      </tbody>
    </table>
  `;
}

function tradeDecisionTable(title, record, actions = []) {
  const trades = tradesFromRecord(record, actions);
  if (!trades.length) return `<section class="daily-subsection"><h3>${escapeHtml(title)}</h3><p class="empty-state compact-empty">沒有操作。</p></section>`;
  return `
    <section class="daily-subsection">
      <h3>${escapeHtml(title)}</h3>
      <table class="daily-table compact-table">
        <thead>
          <tr>
            <th>股票</th>
            <th>動作</th>
            <th>股數</th>
            <th>價格</th>
            <th>金額</th>
            <th>決策變化</th>
            <th>理由</th>
          </tr>
        </thead>
        <tbody>
          ${trades.map((trade) => `
            <tr>
              <td>${escapeHtml(stockLabel(trade))}</td>
              <td>${escapeHtml(actionLabel(trade.action))}</td>
              <td>${escapeHtml(sharesText(trade.shares))}</td>
              <td>${trade.price === undefined || trade.price === null ? "--" : escapeHtml(Number(trade.price).toFixed(2))}</td>
              <td>${money(trade.amount)}</td>
              <td>${escapeHtml(decisionChangeLabel(trade.decision_change))}</td>
              <td>${escapeHtml(trade.reason || "--")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </section>
  `;
}

function decisionChangeLabel(value) {
  return {
    follow_premarket_plan: "照盤前計畫",
    intraday_new_buy: "盤中新增買進",
    cancel_premarket_buy: "盤中取消買進",
    intraday_watch: "盤中改觀察",
    intraday_decision: "盤中決策",
  }[value] || "--";
}

function decisionReviewTable(day) {
  const rows = day.decision_reviews || [];
  if (!rows.length) return "";
  return `
    <section class="daily-subsection decision-review-section">
      <h3>盤中決策回顧</h3>
      <table class="daily-table compact-table">
        <thead>
          <tr>
            <th>股票</th>
            <th>盤前</th>
            <th>盤中</th>
            <th>盤後</th>
            <th>決策變化</th>
            <th>盤後檢討</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(stockLabel(row))}</td>
              <td>${escapeHtml(row.premarket_score ?? "--")} 分</td>
              <td>${escapeHtml(row.intraday_score ?? "--")} 分</td>
              <td>${escapeHtml(row.post_score ?? "--")} 分</td>
              <td>${escapeHtml(decisionChangeLabel(row.decision_change))}</td>
              <td>${escapeHtml(row.review || row.decision_basis || "--")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </section>
  `;
}

function holdingsStatusTable(portfolio) {
  const holdings = portfolio?.holdings || [];
  if (!holdings.length) return '<section class="daily-subsection"><h3>目前持股</h3><p class="empty-state compact-empty">目前沒有持股。</p></section>';
  return `
    <section class="daily-subsection">
      <h3>目前持股</h3>
      <table class="daily-table compact-table">
        <thead>
          <tr>
            <th>股票</th>
            <th>股數</th>
            <th>成本價</th>
            <th>市價</th>
            <th>市值</th>
            <th>未實現損益</th>
            <th>分數</th>
          </tr>
        </thead>
        <tbody>
          ${holdings.map((holding) => `
            <tr>
              <td>${escapeHtml(stockLabel(holding))}</td>
              <td>${escapeHtml(sharesText(holding.shares))}</td>
              <td>${holding.entry_price === undefined || holding.entry_price === null ? "--" : escapeHtml(Number(holding.entry_price).toFixed(2))}</td>
              <td>${holding.market_price === undefined || holding.market_price === null ? "--" : escapeHtml(Number(holding.market_price).toFixed(2))}</td>
              <td>${money(holding.market_value)}</td>
              <td>${money(holding.unrealized_pl)}</td>
              <td>${escapeHtml(holding.score ?? "--")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </section>
  `;
}

function fundStatusTable(portfolio) {
  const rows = [
    ["現金", money(portfolio?.cash)],
    ["持股市值", money(portfolio?.invested_value)],
    ["帳戶淨值", money(portfolio?.total_value)],
    ["未實現損益", money(portfolio?.unrealized_pl)],
    ["已實現損益", money(portfolio?.realized_pl)],
    ["交易成本", money(portfolio?.costs)],
    ["帳戶報酬率", pctText(portfolio?.return_pct)],
  ];
  return `
    <section class="daily-subsection">
      <h3>資金狀況</h3>
      <table class="daily-table compact-table fund-table">
        <tbody>${rows.map(([name, value]) => `<tr><th>${escapeHtml(name)}</th><td>${escapeHtml(value)}</td></tr>`).join("")}</tbody>
      </table>
    </section>
  `;
}

function profitLossStatusTable(portfolio) {
  const initialCapital = Number(portfolio?.initial_capital || 0);
  const totalValue = Number(portfolio?.total_value || 0);
  const totalPl = initialCapital && totalValue ? totalValue - initialCapital : null;
  const rows = [
    ["累計損益", money(totalPl)],
    ["累計報酬率", pctText(portfolio?.return_pct)],
    ["未實現損益", money(portfolio?.unrealized_pl)],
    ["已實現損益", money(portfolio?.realized_pl)],
    ["交易成本", money(portfolio?.costs)],
    ["帳戶淨值", money(portfolio?.total_value)],
  ];
  return `
    <section class="daily-subsection profit-loss-section">
      <h3>損益狀況</h3>
      <table class="daily-table compact-table fund-table">
        <tbody>${rows.map(([name, value]) => `<tr><th>${escapeHtml(name)}</th><td>${escapeHtml(value)}</td></tr>`).join("")}</tbody>
      </table>
    </section>
  `;
}

function dailyDetailSection(day) {
  const portfolio = portfolioFromDay(day);
  return `
    <details class="classified-section daily-day" open>
      <summary>${escapeHtml(day.date || "--")}：${escapeHtml(day.summary || "")}</summary>
      ${dailyStatusSummaryTable(day)}
      <div class="daily-detail-grid">
        ${tradeDecisionTable("盤前預計", day.pre_market, ["PLAN_BUY", "WATCH", "AVOID"])}
        ${tradeDecisionTable("盤中操作", day.market_hours, ["BUY", "SELL", "WATCH", "HOLD"])}
        ${tradeDecisionTable("盤後結算", day.post_market, ["HOLD", "WATCH", "SELL"])}
        ${decisionReviewTable(day)}
        ${profitLossStatusTable(portfolio)}
        ${holdingsStatusTable(portfolio)}
        ${fundStatusTable(portfolio)}
      </div>
    </details>
  `;
}

renderDailyTable = function(days, caseId = "") {
  if (!days.length) {
    dailyOutput.innerHTML = `
      ${caseViewToolbar(caseId)}
      <p class="empty-state">${escapeHtml(caseId || "目前案件")} 尚未有每日資料，請先執行盤前、盤中或盤後流程。</p>
    `;
    return;
  }
  dailyOutput.innerHTML = `
    ${caseViewToolbar(caseId, `共 ${days.length} 天`)}
    <table class="daily-table daily-overview-table">
      <thead>
        <tr>
          <th>日期</th>
          <th>盤前狀態</th>
          <th>盤前預計</th>
          <th>盤中狀態</th>
          <th>盤中操作</th>
          <th>盤後狀態</th>
          <th>損益狀況</th>
          <th>帳戶淨值</th>
        </tr>
      </thead>
      <tbody>
        ${days.map((day) => {
          const portfolio = portfolioFromDay(day);
          return `
            <tr>
              <td>${escapeHtml(day.date || "--")}</td>
              <td><span class="${statusClass(day.has_pre_market)}">${statusText(day.has_pre_market)}</span></td>
              <td>${escapeHtml(compactTradeSummary(day.pre_market, ["PLAN_BUY"]))}</td>
              <td><span class="${statusClass(day.has_market_hours)}">${statusText(day.has_market_hours)}</span></td>
              <td>${escapeHtml(compactTradeSummary(day.market_hours, ["BUY", "SELL"]))}</td>
              <td><span class="${statusClass(day.has_post_market)}">${statusText(day.has_post_market)}</span></td>
              <td>${money((Number(portfolio.total_value || 0) && Number(portfolio.initial_capital || 0)) ? Number(portfolio.total_value) - Number(portfolio.initial_capital) : null)} / ${escapeHtml(pctText(portfolio.return_pct))}</td>
              <td>${money(portfolio.total_value)}</td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
    <div class="classified-list">
      ${days.map((day) => dailyDetailSection(day)).join("")}
    </div>
  `;
};

// Final ledger renderer: group all sessions from the same date and strategy version together.
function ledgerFinalVersionKey(record) {
  return record.strategy_version || "未標示策略版本";
}

function ledgerFinalDateKey(record) {
  return record.trading_date || String(record.generated_at || "").slice(0, 10) || "--";
}

function groupLedgerRecordsByDateVersionFinal(records) {
  const groups = new Map();
  for (const record of records) {
    const key = `${ledgerFinalDateKey(record)}|${ledgerFinalVersionKey(record)}`;
    if (!groups.has(key)) {
      groups.set(key, {
        date: ledgerFinalDateKey(record),
        strategy_version: ledgerFinalVersionKey(record),
        records: [],
      });
    }
    groups.get(key).records.push(record);
  }
  return [...groups.values()];
}

function ledgerFinalDateVersionSummary(group) {
  const rows = group.records.flatMap((record) => ledgerRowsForRecord(record));
  const buyCount = rows.filter((row) => row.action === "BUY").length;
  const sellCount = rows.filter((row) => row.action === "SELL").length;
  const watchCount = rows.filter((row) => ["WATCH", "HOLD", "SNAPSHOT"].includes(row.action)).length;
  const latest = group.records[0] || {};
  return `${group.records.length} 次紀錄，${rows.length} 筆，買進 ${buyCount}，賣出 ${sellCount}，觀察/續抱 ${watchCount}，最新淨值 ${money(latest.total_value)}`;
}

function ledgerFinalSessionSortValue(record) {
  return { pre_market: 0, market_hours: 1, post_market: 2 }[record.report_session] ?? 9;
}

function ledgerFinalSessionBlocks(records) {
  return [...records]
    .sort((a, b) => ledgerFinalSessionSortValue(a) - ledgerFinalSessionSortValue(b))
    .map((record) => ledgerSessionBlock(record))
    .join("");
}

renderLedgerTable = function(records, caseId = "") {
  if (!records.length) {
    ledgerOutput.innerHTML = `
      ${caseViewToolbar(caseId)}
      <p class="empty-state">${escapeHtml(caseId || "目前案件")} 尚未有正式帳本；盤中模擬交易或盤後結算後才會出現。</p>
    `;
    return;
  }

  const sortedRecords = [...records].reverse().slice(0, 80);
  const groups = groupLedgerRecordsByDateVersionFinal(sortedRecords);
  const totalRows = sortedRecords.reduce((count, record) => count + ledgerRowsForRecord(record).length, 0);
  ledgerOutput.innerHTML = `
    ${caseViewToolbar(caseId, `共 ${groups.length} 組 / ${sortedRecords.length} 次紀錄 / ${totalRows} 筆明細`)}
    <div class="classified-list ledger-collapse-list">
      ${groups.map((group) => `
        <details class="classified-section ledger-record ledger-date-record">
          <summary>${escapeHtml(group.date)}｜${escapeHtml(group.strategy_version)}：${escapeHtml(ledgerFinalDateVersionSummary(group))}</summary>
          ${ledgerFinalSessionBlocks(group.records)}
        </details>
      `).join("")}
    </div>
  `;
};

function ledgerVersionKey(record) {
  return record.strategy_version || "未標示策略版本";
}

function ledgerDateVersionKey(record) {
  return `${ledgerDateKey(record)}|${ledgerVersionKey(record)}`;
}

function groupLedgerRecordsByDateVersion(records) {
  const groups = new Map();
  for (const record of records) {
    const key = ledgerDateVersionKey(record);
    if (!groups.has(key)) {
      groups.set(key, {
        date: ledgerDateKey(record),
        strategy_version: ledgerVersionKey(record),
        records: [],
      });
    }
    groups.get(key).records.push(record);
  }
  return [...groups.values()];
}

function ledgerDateVersionSummary(group) {
  const rows = group.records.flatMap((record) => ledgerRowsForRecord(record));
  const buyCount = rows.filter((row) => row.action === "BUY").length;
  const sellCount = rows.filter((row) => row.action === "SELL").length;
  const watchCount = rows.filter((row) => ["WATCH", "HOLD", "SNAPSHOT"].includes(row.action)).length;
  const latest = group.records[0] || {};
  return `${group.records.length} 次紀錄，${rows.length} 筆，買進 ${buyCount}，賣出 ${sellCount}，觀察/續抱 ${watchCount}，最新淨值 ${money(latest.total_value)}`;
}

function ledgerSessionSortValue(record) {
  return { market_hours: 1, post_market: 2, pre_market: 0 }[record.report_session] ?? 9;
}

function ledgerSessionBlocksForGroup(records) {
  return [...records]
    .sort((a, b) => ledgerSessionSortValue(a) - ledgerSessionSortValue(b))
    .map((record) => ledgerSessionBlock(record))
    .join("");
}

renderLedgerTable = function(records, caseId = "") {
  if (!records.length) {
    ledgerOutput.innerHTML = `
      ${caseViewToolbar(caseId)}
      <p class="empty-state">${escapeHtml(caseId || "目前案件")} 尚未有正式帳本；盤中模擬交易或盤後結算後才會出現。</p>
    `;
    return;
  }

  const sortedRecords = [...records].reverse().slice(0, 80);
  const groups = groupLedgerRecordsByDateVersion(sortedRecords);
  const totalRows = sortedRecords.reduce((count, record) => count + ledgerRowsForRecord(record).length, 0);
  ledgerOutput.innerHTML = `
    ${caseViewToolbar(caseId, `共 ${groups.length} 組 / ${sortedRecords.length} 次紀錄 / ${totalRows} 筆明細`)}
    <div class="classified-list ledger-collapse-list">
      ${groups.map((group) => `
        <details class="classified-section ledger-record ledger-date-record">
          <summary>${escapeHtml(group.date)}｜${escapeHtml(group.strategy_version)}：${escapeHtml(ledgerDateVersionSummary(group))}</summary>
          ${ledgerSessionBlocksForGroup(group.records)}
        </details>
      `).join("")}
    </div>
  `;
};

function ledgerDateKey(record) {
  return record.trading_date || String(record.generated_at || "").slice(0, 10) || "--";
}

function groupLedgerRecordsByDate(records) {
  const groups = new Map();
  for (const record of records) {
    const date = ledgerDateKey(record);
    if (!groups.has(date)) groups.set(date, []);
    groups.get(date).push(record);
  }
  return [...groups.entries()].map(([date, items]) => ({ date, records: items }));
}

function ledgerDateSummary(records) {
  const rows = records.flatMap((record) => ledgerRowsForRecord(record));
  const buyCount = rows.filter((row) => row.action === "BUY").length;
  const sellCount = rows.filter((row) => row.action === "SELL").length;
  const watchCount = rows.filter((row) => ["WATCH", "HOLD", "SNAPSHOT"].includes(row.action)).length;
  const latest = records[0] || {};
  return `${records.length} 次紀錄，${rows.length} 筆，買進 ${buyCount}，賣出 ${sellCount}，觀察/續抱 ${watchCount}，最新淨值 ${money(latest.total_value)}`;
}

function ledgerSessionBlock(record) {
  const rows = ledgerRowsForRecord(record);
  return `
    <details class="daily-stage ledger-session-stage">
      <summary>${escapeHtml(sessionLabel(record.report_session))}：${escapeHtml(ledgerGroupSummary(rows, record))}</summary>
      <div class="ledger-record-meta">
        <span>產生時間：${escapeHtml(record.generated_at || "--")}</span>
        <span>策略版本：${escapeHtml(record.strategy_version || "--")}</span>
        <span>現金：${money(record.cash)}</span>
        <span>持股市值：${money(record.invested_value)}</span>
      </div>
      ${ledgerActionSections(rows)}
    </details>
  `;
}

renderLedgerTable = function(records, caseId = "") {
  if (!records.length) {
    ledgerOutput.innerHTML = `
      ${caseViewToolbar(caseId)}
      <p class="empty-state">${escapeHtml(caseId || "目前案件")} 尚未有正式帳本；盤中模擬交易或盤後結算後才會出現。</p>
    `;
    return;
  }

  const sortedRecords = [...records].reverse().slice(0, 80);
  const groups = groupLedgerRecordsByDate(sortedRecords);
  const totalRows = sortedRecords.reduce((count, record) => count + ledgerRowsForRecord(record).length, 0);
  ledgerOutput.innerHTML = `
    ${caseViewToolbar(caseId, `共 ${groups.length} 天 / ${sortedRecords.length} 次紀錄 / ${totalRows} 筆明細`)}
    <div class="classified-list ledger-collapse-list">
      ${groups.map((group) => `
        <details class="classified-section ledger-record ledger-date-record">
          <summary>${escapeHtml(group.date)}：${escapeHtml(ledgerDateSummary(group.records))}</summary>
          ${group.records.map((record) => ledgerSessionBlock(record)).join("")}
        </details>
      `).join("")}
    </div>
  `;
};

function ledgerRowsForRecord(record) {
  const trades = record.trades || [];
  if (!trades.length) {
    return [{
      generated_at: record.generated_at,
      trading_date: record.trading_date,
      report_session: record.report_session,
      action: "SNAPSHOT",
      symbol: "--",
      company_name: "",
      shares: 0,
      price: null,
      amount: 0,
      total_value: record.total_value,
      reason: "帳戶快照，沒有新增買賣。"
    }];
  }
  return trades.map((trade) => ({
    ...trade,
    generated_at: record.generated_at,
    trading_date: record.trading_date,
    report_session: record.report_session,
    total_value: record.total_value
  }));
}

function ledgerGroupSummary(rows, record) {
  const buyCount = rows.filter((row) => row.action === "BUY").length;
  const sellCount = rows.filter((row) => row.action === "SELL").length;
  const watchCount = rows.filter((row) => ["WATCH", "HOLD", "SNAPSHOT"].includes(row.action)).length;
  return `${rows.length} 筆，買進 ${buyCount}，賣出 ${sellCount}，觀察/續抱 ${watchCount}，淨值 ${money(record.total_value)}`;
}

function ledgerActionSections(rows) {
  const sections = [
    ["BUY", "買進"],
    ["SELL", "賣出"],
    ["HOLD", "續抱"],
    ["WATCH", "觀察"],
    ["SNAPSHOT", "快照"],
  ].map(([action, label]) => ({ action, label, rows: rows.filter((row) => row.action === action) }))
    .filter((section) => section.rows.length);

  return sections.map((section) => `
    <details class="daily-stage ledger-action-stage">
      <summary>${escapeHtml(section.label)}：${section.rows.length} 筆</summary>
      <div class="table-scroll">
        <table class="daily-table compact-table">
          <thead>
            <tr>
              <th>股票</th>
              <th>動作</th>
              <th>股數</th>
              <th>價格</th>
              <th>金額</th>
              <th>帳戶淨值</th>
              <th>決策變化</th>
              <th>原因</th>
            </tr>
          </thead>
          <tbody>${section.rows.map((row) => ledgerRow(row)).join("")}</tbody>
        </table>
      </div>
    </details>
  `).join("");
}

ledgerRow = function(row) {
  return `
    <tr>
      <td>${escapeHtml(stockLabel(row))}</td>
      <td>${escapeHtml(actionLabel(row.action))}</td>
      <td>${escapeHtml(sharesText(row.shares))}</td>
      <td>${row.price === null || row.price === undefined ? "--" : escapeHtml(Number(row.price).toFixed(2))}</td>
      <td>${money(row.amount)}</td>
      <td>${money(row.total_value)}</td>
      <td>${escapeHtml(decisionChangeLabel(row.decision_change))}</td>
      <td>${escapeHtml(row.reason || "--")}</td>
    </tr>
  `;
};

renderLedgerTable = function(records, caseId = "") {
  if (!records.length) {
    ledgerOutput.innerHTML = `
      ${caseViewToolbar(caseId)}
      <p class="empty-state">${escapeHtml(caseId || "目前案件")} 尚未有正式帳本；盤中模擬交易或盤後結算後才會出現。</p>
    `;
    return;
  }

  const sortedRecords = [...records].reverse().slice(0, 80);
  const totalRows = sortedRecords.reduce((count, record) => count + ledgerRowsForRecord(record).length, 0);
  ledgerOutput.innerHTML = `
    ${caseViewToolbar(caseId, `共 ${sortedRecords.length} 次紀錄 / ${totalRows} 筆明細`)}
    <div class="classified-list ledger-collapse-list">
      ${sortedRecords.map((record) => {
        const rows = ledgerRowsForRecord(record);
        const date = record.trading_date || String(record.generated_at || "").slice(0, 10) || "--";
        const title = `${date} ${sessionLabel(record.report_session)}`;
        return `
          <details class="classified-section ledger-record">
            <summary>${escapeHtml(title)}：${escapeHtml(ledgerGroupSummary(rows, record))}</summary>
            <div class="ledger-record-meta">
              <span>產生時間：${escapeHtml(record.generated_at || "--")}</span>
              <span>策略版本：${escapeHtml(record.strategy_version || "--")}</span>
              <span>現金：${money(record.cash)}</span>
              <span>持股市值：${money(record.invested_value)}</span>
            </div>
            ${ledgerActionSections(rows)}
          </details>
        `;
      }).join("")}
    </div>
  `;
};

holdingsStatusTable = function(portfolio) {
  const holdings = portfolio?.holdings || [];
  if (!holdings.length) return '<section class="daily-subsection"><h3>目前持股</h3><p class="empty-state compact-empty">目前沒有持股。</p></section>';
  return `
    <section class="daily-subsection account-holdings">
      <h3>目前持股</h3>
      <div class="table-scroll">
        <table class="daily-table compact-table">
          <thead>
            <tr>
              <th>股票</th>
              <th>股數</th>
              <th>成本價</th>
              <th>市價</th>
              <th>市值</th>
              <th>未實現損益</th>
              <th>損益率</th>
              <th>分數</th>
            </tr>
          </thead>
          <tbody>
            ${holdings.map((holding) => {
              const entry = Number(holding.entry_price || 0);
              const market = Number(holding.market_price || 0);
              const holdingReturn = entry && market ? (market - entry) / entry : null;
              return `
                <tr>
                  <td>${escapeHtml(stockLabel(holding))}</td>
                  <td>${escapeHtml(sharesText(holding.shares))}</td>
                  <td>${holding.entry_price === undefined || holding.entry_price === null ? "--" : escapeHtml(Number(holding.entry_price).toFixed(2))}</td>
                  <td>${holding.market_price === undefined || holding.market_price === null ? "--" : escapeHtml(Number(holding.market_price).toFixed(2))}</td>
                  <td>${money(holding.market_value)}</td>
                  <td>${money(holding.unrealized_pl)}</td>
                  <td>${escapeHtml(pctText(holdingReturn))}</td>
                  <td>${escapeHtml(holding.score ?? "--")}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;
};

tradeDecisionTable = function(title, record, actions = []) {
  const trades = tradesFromRecord(record, actions);
  if (!trades.length) return `<section class="daily-subsection"><h3>${escapeHtml(title)}</h3><p class="empty-state compact-empty">沒有操作。</p></section>`;
  return `
    <section class="daily-subsection">
      <h3>${escapeHtml(title)}</h3>
      <div class="table-scroll">
        <table class="daily-table compact-table">
          <thead>
            <tr>
              <th>股票</th>
              <th>動作</th>
              <th>股數</th>
              <th>價格</th>
              <th>金額</th>
              <th>理由</th>
            </tr>
          </thead>
          <tbody>
            ${trades.map((trade) => `
              <tr>
                <td>${escapeHtml(stockLabel(trade))}</td>
                <td>${escapeHtml(actionLabel(trade.action))}</td>
                <td>${escapeHtml(sharesText(trade.shares))}</td>
                <td>${trade.price === undefined || trade.price === null ? "--" : escapeHtml(Number(trade.price).toFixed(2))}</td>
                <td>${money(trade.amount)}</td>
                <td>${escapeHtml(trade.reason || "--")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;
};

dailyDetailSection = function(day) {
  return `
    <details class="classified-section daily-day">
      <summary>${escapeHtml(day.date || "--")}：${escapeHtml(day.summary || "")}</summary>
      ${dailyStatusSummaryTable(day)}
      <div class="daily-detail-grid">
        <details class="daily-stage" open>
          <summary>盤前預計</summary>
          ${tradeDecisionTable("盤前預計", day.pre_market, ["PLAN_BUY", "WATCH", "AVOID"])}
        </details>
        <details class="daily-stage">
          <summary>盤中操作</summary>
          ${tradeDecisionTable("盤中操作", day.market_hours, ["BUY", "SELL", "WATCH", "HOLD"])}
        </details>
        <details class="daily-stage">
          <summary>盤後結算</summary>
          ${tradeDecisionTable("盤後結算", day.post_market, ["HOLD", "WATCH", "SELL"])}
        </details>
      </div>
    </details>
  `;
};

function latestPortfolioForDays(days) {
  for (const day of [...days].reverse()) {
    const portfolio = portfolioFromDay(day);
    if (portfolio && Object.keys(portfolio).length) return portfolio;
  }
  return {};
}

function accountSummarySection(days) {
  const portfolio = latestPortfolioForDays(days);
  return `
    <section class="account-summary-grid">
      ${holdingsStatusTable(portfolio)}
      <div class="account-summary-side">
        ${profitLossStatusTable(portfolio)}
        ${fundStatusTable(portfolio)}
      </div>
    </section>
  `;
}

renderDailyTable = function(days, caseId = "") {
  if (!days.length) {
    dailyOutput.innerHTML = `
      ${caseViewToolbar(caseId)}
      <p class="empty-state">${escapeHtml(caseId || "目前案件")} 尚未有每日資料，請先執行盤前、盤中或盤後流程。</p>
    `;
    return;
  }
  dailyOutput.innerHTML = `
    ${caseViewToolbar(caseId, `共 ${days.length} 天`)}
    ${accountSummarySection(days)}
    <div class="table-scroll daily-overview-scroll">
      <table class="daily-table daily-overview-table">
        <thead>
          <tr>
            <th>日期</th>
            <th>盤前狀態</th>
            <th>盤前預計</th>
            <th>盤中狀態</th>
            <th>盤中操作</th>
            <th>盤後狀態</th>
            <th>損益狀況</th>
            <th>帳戶淨值</th>
          </tr>
        </thead>
        <tbody>
          ${days.map((day) => {
            const portfolio = portfolioFromDay(day);
            const totalPl = (Number(portfolio.total_value || 0) && Number(portfolio.initial_capital || 0)) ? Number(portfolio.total_value) - Number(portfolio.initial_capital) : null;
            return `
              <tr>
                <td>${escapeHtml(day.date || "--")}</td>
                <td><span class="${statusClass(day.has_pre_market)}">${statusText(day.has_pre_market)}</span></td>
                <td>${escapeHtml(compactTradeSummary(day.pre_market, ["PLAN_BUY"]))}</td>
                <td><span class="${statusClass(day.has_market_hours)}">${statusText(day.has_market_hours)}</span></td>
                <td>${escapeHtml(compactTradeSummary(day.market_hours, ["BUY", "SELL"]))}</td>
                <td><span class="${statusClass(day.has_post_market)}">${statusText(day.has_post_market)}</span></td>
                <td>${money(totalPl)} / ${escapeHtml(pctText(portfolio.return_pct))}</td>
                <td>${money(portfolio.total_value)}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
    <div class="classified-list">
      ${days.map((day) => dailyDetailSection(day)).join("")}
    </div>
  `;
};

renderLedgerTable = function(records, caseId = "") {
  if (!records.length) {
    ledgerOutput.innerHTML = `
      ${caseViewToolbar(caseId)}
      <p class="empty-state">${escapeHtml(caseId || "目前案件")} 尚未有正式帳本；盤中模擬交易或盤後結算後才會出現。</p>
    `;
    return;
  }

  const sortedRecords = [...records].reverse().slice(0, 80);
  const groups = groupLedgerRecordsByDateVersionFinal(sortedRecords);
  const totalRows = sortedRecords.reduce((count, record) => count + ledgerRowsForRecord(record).length, 0);
  ledgerOutput.innerHTML = `
    ${caseViewToolbar(caseId, `共 ${groups.length} 組 / ${sortedRecords.length} 次紀錄 / ${totalRows} 筆明細`)}
    <div class="classified-list ledger-collapse-list">
      ${groups.map((group) => `
        <details class="classified-section ledger-record ledger-date-record">
          <summary>${escapeHtml(group.date)}｜${escapeHtml(group.strategy_version)}：${escapeHtml(ledgerFinalDateVersionSummary(group))}</summary>
          ${ledgerFinalSessionBlocks(group.records)}
        </details>
      `).join("")}
    </div>
  `;
};
