from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

from pydantic import BaseModel

from backend.models import PotentialStockRequest
from backend.services.email_service import send_potential_stock_report_email
from backend.services.potential_stock_service import PotentialStockService


class CronPotentialStockRequest(PotentialStockRequest):
    token: str = ""
    send_email: bool | None = None
    background: bool = True
    use_saved_settings: bool = True


class CronAcceptedResponse(BaseModel):
    ok: bool = True
    accepted: bool = True
    background: bool = True
    report_session: str


class PotentialStockCronRunner:
    def __init__(self, service: PotentialStockService, settings_provider: Callable[[], Any]) -> None:
        self.service = service
        self.settings_provider = settings_provider
        self._background_tasks: set[asyncio.Task] = set()

    def accepted_payload(self, report_session: str) -> dict[str, Any]:
        return CronAcceptedResponse(report_session=report_session).model_dump(mode="json")

    def sequence_skip_payload(self, sequence: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "accepted": False,
            "skipped": True,
            "background": False,
            "report_session": sequence.get("report_session"),
            "required_session": sequence.get("required_session"),
            "case_id": sequence.get("case_id"),
            "reason": sequence.get("reason") or "Skipped by cron sequence guard.",
        }

    async def execute(self, request: PotentialStockRequest, report_session: str, send_email: bool | None = None) -> dict[str, Any]:
        report = await self.service.run(request)
        should_send_email = self.settings_provider().send_cron_email if send_email is None else send_email
        email_result = send_potential_stock_report_email(report_session, report) if should_send_email else {"sent": False, "reason": "send_email=false"}
        markdown = getattr(report, "markdown", "") or ""
        data_limitations = list(getattr(report, "data_limitations", []) or [])
        return {
            "ok": True,
            "report_session": report_session,
            "email": email_result,
            "generated_at": getattr(report, "generated_at", None),
            "market_stance": getattr(report, "market_stance", ""),
            "analysis_count": len(getattr(report, "analyses", []) or []),
            "trade_count": len(getattr(getattr(report, "portfolio", None), "trades", []) or []),
            "total_value": getattr(getattr(report, "portfolio", None), "total_value", None),
            "data_limitation_count": len(data_limitations),
            "data_limitations_preview": data_limitations[:3],
            "markdown_bytes": len(markdown.encode("utf-8")),
            "report_saved": bool(request.persist),
            "compact": True,
        }

    def schedule(self, request: PotentialStockRequest, report_session: str, send_email: bool | None = None) -> None:
        self._start_background_thread(self._run_background(request, report_session, send_email))

    def schedule_with_sequence(self, request: PotentialStockRequest, report_session: str, send_email: bool | None = None) -> None:
        self._start_background_thread(self._run_background_with_sequence(request, report_session, send_email))

    def schedule_saved_settings(self, report_session: str, persist: bool = True, send_email: bool | None = None) -> None:
        self._start_background_thread(self._run_saved_settings_background(report_session, persist, send_email))

    def _start_background_thread(self, coroutine: Any) -> None:
        def runner() -> None:
            asyncio.run(coroutine)

        thread = threading.Thread(target=runner, name="potential-stock-cron", daemon=True)
        thread.start()

    async def _run_background(self, request: PotentialStockRequest, report_session: str, send_email: bool | None = None) -> None:
        try:
            await self.execute(request, report_session, send_email)
        except Exception as exc:  # noqa: BLE001
            print(f"Background potential-stock cron failed for {report_session}: {exc}")

    async def _run_background_with_sequence(self, request: PotentialStockRequest, report_session: str, send_email: bool | None = None) -> None:
        try:
            sequence = self.service.sequence_check(report_session, persist=request.persist)
            if not sequence["allowed"]:
                print(f"Background potential-stock cron skipped for {report_session}: {sequence.get('reason')}")
                return
            await self.execute(request, report_session, send_email)
        except Exception as exc:  # noqa: BLE001
            print(f"Background potential-stock cron failed for {report_session}: {exc}")

    async def _run_saved_settings_background(self, report_session: str, persist: bool = True, send_email: bool | None = None) -> None:
        try:
            request = self.service.request_from_saved_settings(report_session, persist=persist)
            sequence = self.service.sequence_check(report_session, persist=persist)
            if not sequence["allowed"]:
                print(f"Background potential-stock cron skipped for {report_session}: {sequence.get('reason')}")
                return
            await self.execute(request, report_session, send_email)
        except Exception as exc:  # noqa: BLE001
            print(f"Background potential-stock cron failed for {report_session}: {exc}")
