import type { DashRpc } from '../dashboard/client';

export interface SettingsData {
  use_notification: string;
  notification_phone_number: string | null;
  rpa_success_message: string;
  rpa_manual_message: string;
  rpa_fail_message: string;
  order_hp_1: string;
  order_hp_2: string | null;
  order_landline_1: string | null;
  order_landline_2: string | null;
  shopping_mall_url: string | null;
  shopping_mall_id: string | null;
  intranet_url: string | null;
  intranet_id: string | null;
  shopping_mall_check_interval: number;
  intranet_check_interval: number;
  has_shopping_mall_password: boolean;
  has_intranet_password: boolean;
  rpa_program_type: string;
  rpa_program_url: string | null;
  rpa_login_id: string | null;
  rpa_enabled: string;
  rpa_auto_submit: string;
  has_rpa_login_password: boolean;
}

export async function getSettings(
  rpc: DashRpc, shopKey: number, token: string,
): Promise<{ ok: boolean; settings?: SettingsData | null; reason?: string }> {
  const { data, error } = await rpc('get_settings', { p_shop_key: shopKey, p_token: token });
  if (error) return { ok: false, reason: 'error' };
  const d = data as { ok?: boolean; settings?: SettingsData | null; reason?: string } | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true, settings: d.settings ?? null };
}

export async function saveSettings(
  rpc: DashRpc, shopKey: number, token: string,
  settings: SettingsData,
  shoppingMallPassword: string | null,
  intranetPassword: string | null,
  rpaLoginPassword: string | null,
): Promise<{ ok: boolean; reason?: string }> {
  const { data, error } = await rpc('save_settings', {
    p_shop_key: shopKey, p_token: token, p_settings: settings,
    p_shopping_mall_password: shoppingMallPassword,
    p_intranet_password: intranetPassword,
    p_rpa_login_password: rpaLoginPassword,
  });
  if (error) return { ok: false, reason: 'error' };
  const d = data as { ok?: boolean; reason?: string } | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true };
}
