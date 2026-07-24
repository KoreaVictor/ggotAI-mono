-- 2026-07-21 보완 저장·재입력 주문을 백엔드가 즉시 집어가게 한다.
--
-- 배경: rpa_status='ready' 는 지금까지 쓰기만 하고 아무도 읽지 않았다.
-- 주문 생성 시점의 engine.enqueue() 만이 RPA 실행 경로였기 때문에,
-- complete_hold_order(보완 저장)·requeue_order(재입력)로 ready 가 되어도
-- 그 주문은 영원히 '대기중'으로 남았다(실기기에서 확인).
--
-- 폴링 스캐너를 되살리는 대신 Realtime UPDATE 구독으로 처리한다.
-- 사장님이 버튼을 누른 순간에만 발동하므로, 2026-07-10 에 재시도 주기를 껐던 이유
-- (업무 중 FlowerNT 주문폼 반복 조작)가 재발하지 않는다.

alter publication supabase_realtime add table public.order_details;
