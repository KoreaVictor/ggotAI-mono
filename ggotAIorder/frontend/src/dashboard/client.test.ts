import { describe, it, expect } from 'vitest';
import { getDashboard, type DashRpc } from './client';

function fakeRpc(data: unknown, error: unknown = null): DashRpc {
  return (async () => ({ data, error })) as DashRpc;
}
const DATA = {
  ok: true,
  stats: { today_total: 3, rpa_success: 1, rpa_fail: 0, rpa_ready: 2 },
  channels: [{ channel_order: '핸드폰', total: 2, success: 0 }],
  config: { garjeon: false, hp1: true, hp2: false, voice: true, mall: true, intranet: false },
  feed: [{ id: 1, channel_order: '핸드폰', customer_name: '홍', stt_text: null, is_order: null, rpa_status: null, created_at: '2026-06-07T00:00:00Z' }],
  engine_alive: true,
};

describe('getDashboard', () => {
  it('성공이면 data 반환', async () => {
    const r = await getDashboard(fakeRpc(DATA), 7, 'tk');
    expect(r.ok).toBe(true);
    expect(r.data?.stats.today_total).toBe(3);
    expect(r.data?.channels[0].channel_order).toBe('핸드폰');
    expect(r.data?.engineAlive).toBe(true);
  });
  it('engine_alive 누락 시 false 로 처리', async () => {
    const { engine_alive: _omit, ...noAlive } = DATA;
    const r = await getDashboard(fakeRpc(noAlive), 7, 'tk');
    expect(r.data?.engineAlive).toBe(false);
  });
  it('unauthorized 면 reason 전달', async () => {
    const r = await getDashboard(fakeRpc({ ok: false, reason: 'unauthorized' }), 7, 'bad');
    expect(r).toEqual({ ok: false, reason: 'unauthorized' });
  });
  it('RPC 에러면 error', async () => {
    const r = await getDashboard(fakeRpc(null, { message: 'boom' }), 7, 'tk');
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});

describe('보류(hold) 통계', () => {
  it('rpa_hold 를 stats 로 전달한다', async () => {
    const stats = { today_total: 5, rpa_success: 2, rpa_fail: 1, rpa_ready: 1, rpa_hold: 3 };
    const rpc = (async () => ({
      data: { ok: true, stats, channels: [], config: {}, feed: [], engine_alive: true },
      error: null,
    })) as DashRpc;

    const r = await getDashboard(rpc, 7, 'tk');

    expect(r.data?.stats.rpa_hold).toBe(3);
  });

  it('서버가 rpa_hold 를 안 주면 0 으로 본다', async () => {
    // 마이그레이션 적용 전 서버와 섞여도 화면이 NaN 을 그리지 않아야 한다.
    const stats = { today_total: 5, rpa_success: 2, rpa_fail: 1, rpa_ready: 1 };
    const rpc = (async () => ({
      data: { ok: true, stats, channels: [], config: {}, feed: [], engine_alive: true },
      error: null,
    })) as DashRpc;

    const r = await getDashboard(rpc, 7, 'tk');

    expect(r.data?.stats.rpa_hold).toBe(0);
  });
});
