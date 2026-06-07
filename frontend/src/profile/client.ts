// supabase.rpc 와 호환되는 최소 계약(테스트 주입용)
export type ProfileRpc = (fn: string, args: Record<string, unknown>) => Promise<{ data: unknown; error: unknown }>;

export interface Profile {
  username: string;
  shop_name: string;
  representative_name: string;
  landline_number: string | null;
  mobile_number: string | null;
  email: string | null;
  address: string | null;
  address_detail: string | null;
  is_approved: string;
}

export interface UpdatePayload {
  username: string;
  authToken: string;
  shopName: string;
  representativeName: string;
  landline: string;
  email: string;
  address: string;
  addressDetail: string;
  newMobile?: string;
  newPhoneToken?: string;
  currentPassword?: string;
  newPassword?: string;
}

type Result = { ok: boolean; profile?: Profile; reason?: string };

export async function getProfile(rpc: ProfileRpc, username: string): Promise<Result> {
  const { data, error } = await rpc('get_profile', { p_username: username });
  if (error) return { ok: false, reason: 'error' };
  return (data as Result | null) ?? { ok: false, reason: 'error' };
}

export async function updateAccount(rpc: ProfileRpc, p: UpdatePayload): Promise<Result> {
  const { data, error } = await rpc('update_account', {
    p_username: p.username,
    p_auth_token: p.authToken,
    p_shop_name: p.shopName,
    p_representative_name: p.representativeName,
    p_landline: p.landline,
    p_email: p.email,
    p_address: p.address,
    p_address_detail: p.addressDetail,
    p_new_mobile: p.newMobile ?? null,
    p_new_phone_token: p.newPhoneToken ?? null,
    p_current_password: p.currentPassword ?? null,
    p_new_password: p.newPassword ?? null,
  });
  if (error) return { ok: false, reason: 'error' };
  return (data as Result | null) ?? { ok: false, reason: 'error' };
}

export function profileMessage(reason: string | undefined): string {
  switch (reason) {
    case 'invalid_token':        return '인증이 만료되었습니다. 다시 인증해주세요';
    case 'bad_password':         return '현재 비밀번호가 올바르지 않습니다';
    case 'new_phone_unverified': return '새 핸드폰 인증을 완료해주세요';
    case 'not_found':            return '회원 정보를 찾을 수 없습니다';
    default:                     return '저장 중 오류가 발생했습니다. 다시 시도해주세요';
  }
}
