-- server_call_history 중복 적재 방지용 부분 UNIQUE 인덱스
-- 배경: upload-call의 멱등성 pre-check(SELECT 후 INSERT)는 비원자적이라
--       동시 요청(재연결 일회성 워커 + 주기 워커, 다중 기기 등)에서 중복 행이 생길 수 있다.
--       DB 제약을 최종 방어선으로 두어 경쟁 상황에서도 한 통화당 1행만 허용한다.
-- 범위: 실제 업로드 통화(audio_file_name IS NOT NULL)만 대상.
--       audio가 없는 과거 시드/더미 행(id 14~23 등)은 제외하여 비파괴적으로 적용.
-- NULLS NOT DISTINCT: customer_phone_number 가 NULL 인 경우에도 중복으로 간주(PG15+).
CREATE UNIQUE INDEX IF NOT EXISTS uq_server_call_history_call
    ON public.server_call_history (shop_key, customer_phone_number, call_date, call_time)
    NULLS NOT DISTINCT
    WHERE audio_file_name IS NOT NULL;
