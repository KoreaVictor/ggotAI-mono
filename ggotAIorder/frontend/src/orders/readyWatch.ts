/**
 * 재전송·보완저장 뒤 결과를 화면에 반영하기 위한 감시 정책.
 *
 * 재전송을 누르면 화면은 '대기중'으로 바뀌지만, 이 화면에는 폴링도 실시간 구독도 없어
 * 백엔드가 입력을 끝내도 화면은 계속 '대기중'이었다(2026-07-22 실사용에서 확인).
 * 사장님은 조회를 다시 누르기 전까지 성공했는지 실패했는지 알 수 없다 —
 * "곧 입력을 시작합니다"라고 안내해놓고 결과를 안 보여주는 셈이었다.
 */

/** 다시 조회하는 주기. 관측된 RPA 소요는 약 15초였다. */
export const WATCH_INTERVAL_MS = 3000;

/**
 * 감시를 포기하는 시점. RPA 가 느리거나 백엔드가 멈춘 경우 무한히 조회하지 않는다 —
 * 그때는 사장님이 직접 조회를 누르는 편이 맞다.
 */
export const WATCH_TIMEOUT_MS = 120_000;

/** 감시 대상 상태. 이 상태에서만 결과가 바뀌기를 기다린다. */
const PENDING_STATUS = 'ready';

/**
 * 아직 결과를 기다릴 값이 있는지.
 *
 * @param rows 현재 화면에 있는 주문들
 * @param elapsedMs 감시를 시작한 뒤 흐른 시간
 */
export function shouldWatch(
  rows: readonly { rpa_status: string }[],
  elapsedMs: number,
  timeoutMs: number = WATCH_TIMEOUT_MS,
): boolean {
  if (elapsedMs >= timeoutMs) return false;
  return rows.some((row) => row.rpa_status === PENDING_STATUS);
}
