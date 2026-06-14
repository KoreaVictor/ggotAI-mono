export interface Session {
  shopKey: number;
  shopName: string;
  username: string;
}

export interface AuthResult {
  ok: boolean;
  session?: Session;
  error?: string;
}

// authenticate 가 필요로 하는 최소 supabase 계약(verify_login RPC, 테스트 주입용)
export interface AuthClient {
  rpc(fn: string, args: Record<string, unknown>): Promise<{ data: unknown; error: unknown }>;
}

const GENERIC_ERROR = '아이디 또는 비밀번호가 올바르지 않습니다';

interface VerifyLoginRow {
  id: number;
  shop_name: string;
  username: string;
  is_approved: string;
}

export async function authenticate(
  client: AuthClient,
  username: string,
  password: string,
): Promise<AuthResult> {
  const { data, error } = await client.rpc('verify_login', {
    p_username: username,
    p_password: password,
  });

  if (error) return { ok: false, error: '로그인 중 오류가 발생했습니다' };

  const row = data as VerifyLoginRow | null;
  if (!row) return { ok: false, error: GENERIC_ERROR };
  if (row.is_approved !== 'Y') return { ok: false, error: '승인 대기 중인 계정입니다' };

  return {
    ok: true,
    session: { shopKey: row.id, shopName: row.shop_name, username: row.username },
  };
}
