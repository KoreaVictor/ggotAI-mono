-- 2026-06-14 부팅 시 catch-up 스캔: 미처리 핸드폰/가게음성 행 식별용 컬럼.
-- 둘 다 nullable/default 이므로 ggotAIhp 기존 INSERT 무손상.
ALTER TABLE server_call_history
    ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS process_attempts INT NOT NULL DEFAULT 0;

-- 미처리 행 조회 가속(부분 인덱스: 미종결 행만).
CREATE INDEX IF NOT EXISTS idx_sch_pending
    ON server_call_history (channel_order, process_attempts)
    WHERE processed_at IS NULL;

-- 백필: 마이그레이션 이전에 이미 처리된 행을 종결 표시한다.
-- (그러지 않으면 모든 기존 행의 processed_at=NULL 이라 첫 부팅 스캔이 재처리→order_details 중복/가짜주문)
-- "이미 처리됨" = order_details가 있거나(주문 생성됨) stt_text가 이미 채워짐(파이프라인 STT 수행 or 비-realtime 채널).
-- 꺼진 동안 들어온 미처리 핸드폰 행은 오디오만 있어(stt_text NULL·order_details 없음) NULL로 남아 스캔 대상이 된다.
UPDATE server_call_history sch
SET processed_at = NOW()
WHERE sch.processed_at IS NULL
  AND (
    sch.stt_text IS NOT NULL
    OR EXISTS (
        SELECT 1 FROM order_details od WHERE od.call_history_id = sch.id
    )
  );
