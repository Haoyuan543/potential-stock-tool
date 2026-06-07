from __future__ import annotations

from base64 import b64decode
from binascii import Error as BinasciiError
from hmac import compare_digest
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi import Header, HTTPException, Query
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import get_settings
from backend.models import BacktestRequest, MarketDataset, PotentialBacktestRequest, PotentialStockRequest, ResearchRequest
from backend.services.alpha_engine import AlphaDiscoveryEngine
from backend.services.analysis_service import AnalysisService
from backend.services.backtest_engine import BacktestEngine
from backend.services.daily_report import DailyReportService
from backend.services.email_service import send_potential_stock_report_email
from backend.services.fetchers import MarketDataFetcher
from backend.services.potential_stock_service import PotentialStockService
from backend.services.storage import set_runtime_storage_backend, storage_status


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
BACKEND_VERSION = "potential-20260607-market-hours"

app = FastAPI(title="AI Alpha Research Platform", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fetcher = MarketDataFetcher()
alpha_engine = AlphaDiscoveryEngine()
backtest_engine = BacktestEngine()
daily_reports = DailyReportService()
analysis_service = AnalysisService()
potential_stock_service = PotentialStockService()


def _valid_basic_auth(header_value: str, username: str, password: str) -> bool:
    if not header_value.lower().startswith("basic "):
        return False
    try:
        decoded = b64decode(header_value.split(" ", 1)[1]).decode("utf-8")
    except (BinasciiError, UnicodeDecodeError, IndexError):
        return False
    provided_username, separator, provided_password = decoded.partition(":")
    if not separator:
        return False
    return compare_digest(provided_username, username) and compare_digest(provided_password, password)


@app.middleware("http")
async def dashboard_basic_auth(request: Request, call_next):
    settings = get_settings()
    if (
        not settings.dashboard_password
        or request.method == "OPTIONS"
        or request.url.path == "/health"
        or request.url.path.startswith("/api/cron/")
        or ((request.client.host if request.client else "") == "testclient")
    ):
        return await call_next(request)
    if _valid_basic_auth(
        request.headers.get("authorization", ""),
        settings.dashboard_username,
        settings.dashboard_password,
    ):
        request.state.dashboard_authenticated = True
        return await call_next(request)
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Potential Stock Dashboard"'},
        content="Authentication required.",
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    message = str(exc) or exc.__class__.__name__
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"後端執行失敗：{message}",
            "error_type": exc.__class__.__name__,
            "path": request.url.path,
        },
    )


class AnalyzeRequest(BaseModel):
    symbol: str = "2603.TW"
    mode: str = "personalized"
    model: str = ""
    freight_overrides: dict = {}
    manual_context: str = ""


class PotentialStockResetCaseRequest(BaseModel):
    note: str = ""


class PotentialStockSwitchCaseRequest(BaseModel):
    case_id: str = "default"


class StorageBackendSwitchRequest(BaseModel):
    backend: Literal["local", "supabase"]
    token: str = ""


class CronPotentialStockRequest(PotentialStockRequest):
    token: str = ""
    send_email: bool | None = None


def _authorize_cron(token: str = "", header_token: str = "") -> None:
    secret = get_settings().cron_job_secret
    provided = token or header_token
    if not secret:
        raise HTTPException(status_code=503, detail="CRON_JOB_SECRET is not configured; cron endpoint is disabled.")
    if not provided or not compare_digest(provided, secret):
        raise HTTPException(status_code=401, detail="Invalid cron token.")


def _authorize_local_or_secret(request: Request, token: str = "", header_token: str = "") -> None:
    host = (request.client.host if request.client else "") or ""
    if host in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return
    if bool(getattr(request.state, "dashboard_authenticated", False)):
        return
    secret = get_settings().cron_job_secret
    provided = token or header_token
    if secret and provided and compare_digest(provided, secret):
        return
    raise HTTPException(status_code=403, detail="Delete actions are allowed only from localhost or with CRON_JOB_SECRET.")


def _cron_response(report_session: str, report: object, email_result: dict | None = None) -> dict:
    return {
        "ok": True,
        "report_session": report_session,
        "email": email_result or {"sent": False, "reason": "Email was not requested."},
        "generated_at": getattr(report, "generated_at", None),
        "market_stance": getattr(report, "market_stance", ""),
        "analysis_count": len(getattr(report, "analyses", []) or []),
        "trade_count": len(getattr(getattr(report, "portfolio", None), "trades", []) or []),
        "total_value": getattr(getattr(report, "portfolio", None), "total_value", None),
        "data_limitations": getattr(report, "data_limitations", []),
        "markdown": getattr(report, "markdown", ""),
    }


@app.get("/")
async def dashboard() -> HTMLResponse:
    return HTMLResponse((FRONTEND / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    storage = storage_status(probe=True)
    return {
        "ok": True,
        "openai_configured": bool(settings.openai_api_key),
        "finmind_configured": bool(settings.finmind_token),
        "news_configured": bool(settings.news_api_key),
        "default_model": settings.openai_model,
        "storage_backend": storage["backend"],
        "storage": storage,
        "backend_version": BACKEND_VERSION,
        "supported_report_sessions": ["pre_market", "market_hours", "post_market"],
    }


@app.get("/api/storage/status")
async def get_storage_status(probe: bool = Query(False)) -> dict:
    return storage_status(probe=probe)


@app.post("/api/storage/backend")
async def switch_storage_backend(
    request: Request,
    payload: StorageBackendSwitchRequest,
    x_cron_token: str = Header(default=""),
) -> dict:
    if not get_settings().dashboard_password:
        _authorize_local_or_secret(request, payload.token, x_cron_token)
    settings = get_settings()
    if payload.backend == "supabase" and not (settings.supabase_url and settings.supabase_service_role_key):
        raise HTTPException(status_code=400, detail="Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY first.")
    try:
        set_runtime_storage_backend(payload.backend)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return storage_status()


@app.get("/models")
async def models() -> dict:
    settings = get_settings()
    options = [
        {"value": "", "label": f"使用 .env 預設模型（{settings.openai_model}）", "speed": "default"},
        {"value": "gpt-5.5", "label": "gpt-5.5：完整分析", "speed": "balanced"},
        {"value": "gpt-5.5-pro", "label": "gpt-5.5-pro：深度分析", "speed": "deep"},
        {"value": "gpt-5", "label": "gpt-5：快速分析", "speed": "fast"},
    ]
    return {"default_model": settings.openai_model, "options": options}


@app.post("/analyze")
async def analyze(request: AnalyzeRequest) -> dict:
    return analysis_service.analyze_now(
        request.symbol,
        request.mode,
        request.freight_overrides,
        request.manual_context,
        request.model,
    )


@app.get("/analysis-history")
async def analysis_history() -> dict:
    return {"records": analysis_service.history(limit=20)}


@app.get("/api/data/{ticker}", response_model=MarketDataset)
async def collect_data(ticker: str) -> MarketDataset:
    return await fetcher.collect(ticker)


@app.post("/api/research")
async def research(request: ResearchRequest) -> dict:
    dataset = request.dataset
    if dataset is None and request.use_live_data:
        dataset = await fetcher.collect(request.ticker)
    if dataset is None:
        dataset = MarketDataset(ticker=request.ticker, limitations=["Data Missing: no dataset supplied and live fetch disabled."])
    report = await alpha_engine.run(dataset, request.manual_context)
    return report.model_dump(mode="json")


@app.post("/api/daily-report")
async def daily_report(request: ResearchRequest) -> dict:
    dataset = request.dataset or await fetcher.collect(request.ticker)
    report = await alpha_engine.run(dataset, request.manual_context)
    prediction = daily_reports.save(dataset, report)
    return {"report": report.model_dump(mode="json"), "prediction_record": prediction.model_dump(mode="json")}


@app.get("/api/daily-report")
async def list_daily_reports() -> dict:
    return {"reports": daily_reports.latest(), "predictions": daily_reports.predictions()}


@app.post("/api/backtest")
async def backtest(request: BacktestRequest) -> dict:
    report = backtest_engine.run(request)
    return report.model_dump(mode="json")


@app.post("/api/potential-stocks")
async def potential_stocks(request: PotentialStockRequest) -> dict:
    report = await potential_stock_service.run(request)
    return report.model_dump(mode="json")


@app.get("/api/potential-stocks/history")
async def potential_stock_history(limit: int = 30, case_id: str | None = None) -> dict:
    return {"records": potential_stock_service.history(limit=limit, case_id=case_id)}


@app.get("/api/potential-stocks/performance")
async def potential_stock_performance(case_id: str | None = None) -> dict:
    return potential_stock_service.performance(case_id=case_id)


@app.get("/api/potential-stocks/branch-summary")
async def potential_stock_branch_summary(case_id: str | None = None) -> dict:
    return potential_stock_service.branch_summary(case_id=case_id)


@app.get("/api/potential-stocks/ledger")
async def potential_stock_ledger(limit: int = 100, case_id: str | None = None) -> dict:
    return {"records": potential_stock_service.ledger(limit=limit, case_id=case_id)}


@app.post("/api/potential-stocks/backtest")
async def potential_stock_backtest(request: PotentialBacktestRequest) -> dict:
    report = await potential_stock_service.backtest(request)
    return report.model_dump(mode="json")


@app.get("/api/potential-stocks/daily-status")
async def potential_stock_daily_status(limit: int = 10, case_id: str | None = None) -> dict:
    return potential_stock_service.daily_status(limit=limit, case_id=case_id)


@app.get("/api/potential-stocks/cases")
async def potential_stock_cases() -> dict:
    return potential_stock_service.cases()


@app.post("/api/potential-stocks/cases/reset")
async def potential_stock_reset_case(request: PotentialStockResetCaseRequest) -> dict:
    return potential_stock_service.reset_case(note=request.note)


@app.post("/api/potential-stocks/cases/switch")
async def potential_stock_switch_case(request: PotentialStockSwitchCaseRequest) -> dict:
    result = potential_stock_service.switch_case(request.case_id)
    if not result.get("selected"):
        raise HTTPException(status_code=404, detail=result.get("error") or "Unknown case_id")
    return result


@app.delete("/api/potential-stocks/cases")
async def potential_stock_delete_all_cases(request: Request, token: str = Query(""), x_cron_token: str = Header(default="")) -> dict:
    _authorize_local_or_secret(request, token, x_cron_token)
    return potential_stock_service.delete_all_cases()


@app.delete("/api/potential-stocks/cases/{case_id}")
async def potential_stock_delete_case(case_id: str, request: Request, token: str = Query(""), x_cron_token: str = Header(default="")) -> dict:
    _authorize_local_or_secret(request, token, x_cron_token)
    return potential_stock_service.delete_case(case_id)


@app.get("/api/cron/potential-stocks")
async def cron_potential_stocks(
    session: Literal["pre_market", "market_hours", "post_market"] = Query("pre_market"),
    token: str = Query(""),
    x_cron_token: str = Header(default=""),
    persist: bool = Query(True),
    market_universe: Literal["semiconductor", "electronics", "industrial", "financial", "custom"] = Query("semiconductor"),
    symbols: str = Query(""),
    initial_capital: float = Query(1_000_000),
    max_positions: int = Query(5),
    strategy_version: str = Query("potential-v1"),
    risk_reward_profile: Literal["conservative", "balanced", "aggressive"] = Query("balanced"),
    investment_horizon: Literal["short_weeks", "mid_term_3m", "long_6m", "multi_year"] = Query("mid_term_3m"),
    use_ai_analysis: bool = Query(False),
    use_live_data: bool = Query(True),
    use_us_tech_leading: bool = Query(True),
    send_email: bool | None = Query(None),
) -> dict:
    _authorize_cron(token, x_cron_token)
    request = PotentialStockRequest(
        symbols=[item.strip() for item in symbols.replace(";", ",").split(",") if item.strip()],
        market_universe=market_universe,
        initial_capital=initial_capital,
        max_positions=max_positions,
        strategy_version=strategy_version,
        risk_reward_profile=risk_reward_profile,
        investment_horizon=investment_horizon,
        report_session=session,
        use_ai_analysis=use_ai_analysis,
        use_live_data=use_live_data,
        use_us_tech_leading=use_us_tech_leading,
        persist=persist,
    )
    report = await potential_stock_service.run(request)
    should_send_email = get_settings().send_cron_email if send_email is None else send_email
    email_result = send_potential_stock_report_email(session, report) if should_send_email else {"sent": False, "reason": "send_email=false"}
    return _cron_response(session, report, email_result)


@app.post("/api/cron/potential-stocks")
async def cron_potential_stocks_post(request: CronPotentialStockRequest, x_cron_token: str = Header(default="")) -> dict:
    _authorize_cron(request.token, x_cron_token)
    safe_request = request.model_copy(update={"token": ""})
    report = await potential_stock_service.run(safe_request)
    should_send_email = get_settings().send_cron_email if request.send_email is None else request.send_email
    email_result = send_potential_stock_report_email(safe_request.report_session, report) if should_send_email else {"sent": False, "reason": "send_email=false"}
    return _cron_response(safe_request.report_session, report, email_result)


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
