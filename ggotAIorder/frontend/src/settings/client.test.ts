import { describe, it, expect } from 'vitest';
import { getSettings, saveSettings, type SettingsData } from './client';
import type { DashRpc } from '../dashboard/client';

function fakeRpc(data: unknown, error: unknown = null): DashRpc {
  return (async () => ({ data, error })) as DashRpc;
}
const SET: SettingsData = {
  use_notification: 'Y', notification_phone_number: null,
  rpa_success_message: 's', rpa_manual_message: 'm', rpa_fail_message: 'f',
  order_hp_1: '010-1', order_hp_2: null, order_landline_1: null, order_landline_2: null,
  shopping_mall_url: 'https://m', shopping_mall_id: 'mid', intranet_url: null, intranet_id: null,
  shopping_mall_check_interval: 15, intranet_check_interval: 40,
  has_shopping_mall_password: true, has_intranet_password: false,
  rpa_program_type: '', rpa_program_url: null, rpa_login_id: null,
  rpa_enabled: 'N', rpa_auto_submit: 'Y', has_rpa_login_password: false,
};

describe('getSettings', () => {
  it('성공이면 settings 반환', async () => {
    const r = await getSettings(fakeRpc({ ok: true, settings: SET }), 7, 'tk');
    expect(r.ok).toBe(true);
    expect(r.settings?.order_hp_1).toBe('010-1');
    expect(r.settings?.has_shopping_mall_password).toBe(true);
  });
  it('행 없으면 settings null', async () => {
    const r = await getSettings(fakeRpc({ ok: true, settings: null }), 7, 'tk');
    expect(r).toEqual({ ok: true, settings: null });
  });
  it('unauthorized 면 reason 전달', async () => {
    const r = await getSettings(fakeRpc({ ok: false, reason: 'unauthorized' }), 7, 'bad');
    expect(r).toEqual({ ok: false, reason: 'unauthorized' });
  });
  it('RPC 에러면 error', async () => {
    const r = await getSettings(fakeRpc(null, { message: 'boom' }), 7, 'tk');
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});

describe('saveSettings', () => {
  it('성공이면 ok', async () => {
    const r = await saveSettings(fakeRpc({ ok: true }), 7, 'tk', SET, 'cipher', null, null);
    expect(r).toEqual({ ok: true });
  });
  it('order_hp_1_required 면 reason 전달', async () => {
    const r = await saveSettings(fakeRpc({ ok: false, reason: 'order_hp_1_required' }), 7, 'tk', SET, null, null, null);
    expect(r).toEqual({ ok: false, reason: 'order_hp_1_required' });
  });
  it('RPC 에러면 error', async () => {
    const r = await saveSettings(fakeRpc(null, { message: 'boom' }), 7, 'tk', SET, null, null, null);
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
  it('인자를 RPC 인자로 매핑(비번 null 포함)', async () => {
    let captured: Record<string, unknown> = {};
    const rpc: DashRpc = (async (_fn: string, args: Record<string, unknown>) => {
      captured = args; return { data: { ok: true }, error: null };
    }) as DashRpc;
    await saveSettings(rpc, 7, 'tk', SET, 'smc', null, null);
    expect(captured.p_shop_key).toBe(7);
    expect(captured.p_token).toBe('tk');
    expect(captured.p_shopping_mall_password).toBe('smc');
    expect(captured.p_intranet_password).toBe(null);
    expect(captured.p_rpa_login_password).toBe(null);
    expect((captured.p_settings as SettingsData).order_hp_1).toBe('010-1');
  });
  it('p_rpa_login_password 를 RPC 인자로 전달', async () => {
    let captured: Record<string, unknown> = {};
    const rpc: DashRpc = (async (_fn: string, args: Record<string, unknown>) => {
      captured = args; return { data: { ok: true }, error: null };
    }) as DashRpc;
    await saveSettings(rpc, 7, 'tk', SET, null, null, 'rpa-cipher');
    expect(captured.p_rpa_login_password).toBe('rpa-cipher');
  });
});
