-- 2026-06-14 부팅 시 catch-up 스캔: 미처리 핸드폰/가게음성 행 식별용 컬럼.
-- 둘 다 nullable/default 이므로 ggotAIhp 기존 INSERT 무손상.
ALTER TABLE server_call_history
    ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS process_attempts INT NOT NULL DEFAULT 0;

-- 미처리 행 조회 가속(부분 인덱스: 미종결 행만).
CREATE INDEX IF NOT EXISTS idx_sch_pending
    ON server_call_history (channel_order, process_attempts)
    WHERE processed_at IS NULL;
