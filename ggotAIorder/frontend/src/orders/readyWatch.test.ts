import { describe, it, expect } from 'vitest';
import { shouldWatch, WATCH_INTERVAL_MS, WATCH_TIMEOUT_MS } from './readyWatch';

describe('readyWatch', () => {
  it('대기중 주문이 있으면 계속 지켜본다', () => {
    expect(shouldWatch([{ rpa_status: 'ready' }], 0)).toBe(true);
    expect(shouldWatch([{ rpa_status: 'success' }, { rpa_status: 'ready' }], 5000)).toBe(true);
  });

  it('대기중 주문이 없으면 그만둔다', () => {
    // 결과가 나왔으니 더 볼 이유가 없다.
    expect(shouldWatch([{ rpa_status: 'success' }, { rpa_status: 'fail' }], 0)).toBe(false);
    expect(shouldWatch([], 0)).toBe(false);
  });

  it('확인필요(hold)는 감시 대상이 아니다', () => {
    // hold 는 사장님이 직접 채워야 바뀐다 — 기다린다고 변하지 않는다.
    expect(shouldWatch([{ rpa_status: 'hold' }], 0)).toBe(false);
  });

  it('제한 시간이 지나면 대기중이 남아 있어도 그만둔다', () => {
    // RPA 가 느리거나 백엔드가 멈춘 경우 무한히 조회하지 않는다.
    expect(shouldWatch([{ rpa_status: 'ready' }], WATCH_TIMEOUT_MS)).toBe(false);
    expect(shouldWatch([{ rpa_status: 'ready' }], WATCH_TIMEOUT_MS + 1)).toBe(false);
    expect(shouldWatch([{ rpa_status: 'ready' }], WATCH_TIMEOUT_MS - 1)).toBe(true);
  });

  it('제한 시간은 주입할 수 있다', () => {
    expect(shouldWatch([{ rpa_status: 'ready' }], 5000, 10000)).toBe(true);
    expect(shouldWatch([{ rpa_status: 'ready' }], 5000, 5000)).toBe(false);
  });

  it('감시 주기는 관측된 RPA 소요(약 15초)보다 짧다', () => {
    expect(WATCH_INTERVAL_MS).toBeLessThan(15000);
    expect(WATCH_INTERVAL_MS).toBeGreaterThan(0);
  });
});
