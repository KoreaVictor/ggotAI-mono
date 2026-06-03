"""가게전화 VoIP Webhook 수신 API.

PRD 6-1: POST /api/v1/gate-phone/upload 로 통화 종료 웹훅(Multipart)을 수신해
음성 Storage 적재 → server_call_history INSERT → pipeline.process 를 백그라운드 예약.
"""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, UploadFile

from ggotaiorder.api.repository import IngestRepository, SupabaseIngestRepository
from ggotaiorder.api.service import ingest_gate_phone
from ggotaiorder.api.storage import AudioStorage, SupabaseAudioStorage
from ggotaiorder.pipeline.engine import process

logger = logging.getLogger(__name__)


def get_ingest_repository() -> IngestRepository:
    """기본 IngestRepository 제공자(테스트에서 override)."""
    return SupabaseIngestRepository()


def get_audio_storage() -> AudioStorage:
    """기본 AudioStorage 제공자(테스트에서 override)."""
    return SupabaseAudioStorage()


def create_app() -> FastAPI:
    """FastAPI 앱을 생성하고 라우트를 등록해 반환한다."""
    app = FastAPI(title="ggotAIorder", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/gate-phone/upload")
    async def gate_phone_upload(
        background_tasks: BackgroundTasks,
        file: UploadFile,
        caller_number: str = Form(...),
        call_duration: int = Form(...),
        user_phone_number: str = Form(...),
        repo: IngestRepository = Depends(get_ingest_repository),
        storage: AudioStorage = Depends(get_audio_storage),
    ) -> dict[str, object]:
        """통화 종료 웹훅을 수신해 인입 후 AI 파이프라인을 백그라운드 예약한다."""
        data = await file.read()
        call_history_id = await ingest_gate_phone(
            file_bytes=data,
            filename=file.filename or "audio.bin",
            caller_number=caller_number,
            call_duration=call_duration,
            user_phone_number=user_phone_number,
            repo=repo,
            storage=storage,
        )
        if call_history_id is None:
            raise HTTPException(status_code=400, detail="shop not found")
        background_tasks.add_task(process, call_history_id)
        return {"status": "accepted", "call_history_id": call_history_id}

    return app
