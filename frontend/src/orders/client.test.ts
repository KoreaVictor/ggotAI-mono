import { describe, it, expect } from 'vitest';
import { getOrders, requeueOrder } from './client';
import type { DashRpc } from '../dashboard/client';

function fakeRpc(data: unknown, error: unknown = null): DashRpc {
  return (async () => ({ data, error })) as DashRpc;
}
const FILTERS = { channel: null, status: null, start: '2026-06-10T00:00:00+09:00', end: '2026-06-11T00:00:00+09:00' };
const ROW = {
  id: 1, call_history_id: 10, customer_name: '홍', customer_phone_number: '010', product_name: '장미',
  quantity: 1, price: 50000, delivery_at: '2026-06-10T10:00:00Z', delivery_place: '서울', receiver_name: '받는이',
  receiver_phone_number: '010', ribbon_sender: null, ribbon_congratulations: null, card_message: null,
  rpa_status: 'fail', created_at: '2026-06-10T00:00:00Z', channel_order: '핸드폰',
};

describe('getOrders', () => {
  it('성공이면 rows 반환', async () => {
    const r = await getOrders(fakeRpc({ ok: true, rows: [ROW] }), 7, 'tk', FILTERS);
    expect(r.ok).toBe(true);
    expect(r.rows?.[0].channel_order).toBe('핸드폰');
    expect(r.rows?.[0].price).toBe(50000);
  });
  it('rows 없으면 빈 배열', async () => {
    const r = await getOrders(fakeRpc({ ok: true }), 7, 'tk', FILTERS);
    expect(r).toEqual({ ok: true, rows: [] });
  });
  it('unauthorized 면 reason 전달', async () => {
    const r = await getOrders(fakeRpc({ ok: false, reason: 'unauthorized' }), 7, 'bad', FILTERS);
    expect(r).toEqual({ ok: false, reason: 'unauthorized' });
  });
  it('RPC 에러면 error', async () => {
    const r = await getOrders(fakeRpc(null, { message: 'boom' }), 7, 'tk', FILTERS);
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
  it('필터 인자를 RPC 인자로 매핑', async () => {
    let captured: Record<string, unknown> = {};
    const rpc: DashRpc = (async (_fn: string, args: Record<string, unknown>) => {
      captured = args; return { data: { ok: true, rows: [] }, error: null };
    }) as DashRpc;
    await getOrders(rpc, 7, 'tk', { channel: '핸드폰', status: 'fail', start: 's', end: 'e' });
    expect(captured).toEqual({ p_shop_key: 7, p_token: 'tk', p_channel: '핸드폰', p_status: 'fail', p_start: 's', p_end: 'e' });
  });
});

describe('requeueOrder', () => {
  it('성공이면 rpa_status 반환', async () => {
    const r = await requeueOrder(fakeRpc({ ok: true, rpa_status: 'ready' }), 7, 'tk', 1);
    expect(r).toEqual({ ok: true, rpa_status: 'ready' });
  });
  it('not_found 면 reason 전달', async () => {
    const r = await requeueOrder(fakeRpc({ ok: false, reason: 'not_found' }), 7, 'tk', 999);
    expect(r).toEqual({ ok: false, reason: 'not_found' });
  });
  it('RPC 에러면 error', async () => {
    const r = await requeueOrder(fakeRpc(null, { message: 'boom' }), 7, 'tk', 1);
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});
