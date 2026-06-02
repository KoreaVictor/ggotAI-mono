"""가게전화 VoIP Webhook 수신 API (스텁).

PRD 6-1: POST /api/v1/gate-phone/upload 로 통화 종료 웹훅(Multipart)을 수신.
수신 → 음성파일 Storage 임시적재 → server_call_history INSERT(channel_order='가게전화')
→ pipeline.process(call_history_id) 비동기 호출.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Form, UploadFile

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """FastAPI 앱을 생성하고 라우트를 등록해 반환한다."""
    app = FastAPI(title="ggotAIorder", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/gate-phone/upload")
    async def gate_phone_upload(
        file: UploadFile,
        caller_number: str = Form(...),
        call_duration: int = Form(...),
        user_phone_number: str = Form(...),
    ) -> dict[str, str]:
        """[스텁] 통화 종료 웹훅 수신 진입점.

        TODO(후속): Storage 적재 → server_call_history INSERT
        → pipeline.process(call_history_id) 호출.
        """
        logger.warning(
            "[STUB] gate-phone upload 수신: caller=%s duration=%s file=%s",
            caller_number, call_duration, file.filename,
        )
        return {"status": "accepted"}

    return app
