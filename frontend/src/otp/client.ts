export type Purpose = 'signup' | 'find_id' | 'find_pw';

// 테스트 주입용 최소 계약 (supabase.rpc / supabase.functions 와 호환)
export type OtpRpc = (fn: string, args: Record<string, unknown>) => Promise<{ data: unknown; error: unknown }>;
export interface FunctionsClient {
  invoke(name: string, opts: { body: unknown }): Promise<{ data: unknown; error: unknown }>;
}

export function normalizePhone(phone: string): string {
  return phone.replace(/\D/g, '');
}

export async function sendOtp(
  fns: FunctionsClient, phone: string, purpose: Purpose,
): Promise<{ ok: boolean; reason?: string }> {
  const { data, error } = await fns.invoke('send-otp', { body: { phone: normalizePhone(phone), purpose } });
  if (error) return { ok: false, reason: 'send_failed' };
  const d = data as { success?: boolean; reason?: string } | null;
  if (!d?.success) return { ok: false, reason: d?.reason ?? 'send_failed' };
  return { ok: true };
}

export async function verifyOtp(
  rpc: OtpRpc, phone: string, purpose: Purpose, code: string,
): Promise<{ ok: boolean; token?: string; reason?: string }> {
  const { data, error } = await rpc('verify_otp', { p_phone: normalizePhone(phone), p_purpose: purpose, p_code: code });
  if (error) return { ok: false, reason: 'error' };
  return (data as { ok: boolean; token?: string; reason?: string } | null) ?? { ok: false, reason: 'error' };
}

export async function findUsername(
  rpc: OtpRpc, phone: string, shopName: string, token: string,
): Promise<{ ok: boolean; username?: string; reason?: string }> {
  const { data, error } = await rpc('find_username', { p_phone: normalizePhone(phone), p_shop_name: shopName, p_token: token });
  if (error) return { ok: false, reason: 'error' };
  return (data as { ok: boolean; username?: string; reason?: string } | null) ?? { ok: false, reason: 'error' };
}

export async function resetPassword(
  rpc: OtpRpc, phone: string, username: string, newPassword: string, token: string,
): Promise<{ ok: boolean; reason?: string }> {
  const { data, error } = await rpc('reset_password', {
    p_phone: normalizePhone(phone), p_username: username, p_new_password: newPassword, p_token: token,
  });
  if (error) return { ok: false, reason: 'error' };
  return (data as { ok: boolean; reason?: string } | null) ?? { ok: false, reason: 'error' };
}
