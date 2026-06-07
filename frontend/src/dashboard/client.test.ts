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
};

describe('getDashboard', () => {
  it('성공이면 data 반환', async () => {
    const r = await getDashboard(fakeRpc(DATA), 7, 'tk');
    expect(r.ok).toBe(true);
    expect(r.data?.stats.today_total).toBe(3);
    expect(r.data?.channels[0].channel_order).toBe('핸드폰');
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
