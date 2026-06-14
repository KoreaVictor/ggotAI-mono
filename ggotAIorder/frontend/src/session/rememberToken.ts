import type { Session } from './authenticate';

export interface RpcLike {
  rpc(fn: string, args: Record<string, unknown>): Promise<{ data: unknown; error: unknown }>;
}

export interface TokenStore {
  load(): Promise<{ userId: number; token: string } | null>;
  clear(): Promise<void>;
}

interface RememberRow {
  id: number;
  shop_name: string;
  username: string;
}

/**
 * 로컬 저장 토큰으로 세션을 복원한다. 토큰 없으면 null,
 * 검증 실패/에러면 로컬 토큰을 정리하고 null.
 */
export async function restoreSession(
  rpc: RpcLike, store: TokenStore,
): Promise<{ session: Session; token: string } | null> {
  const saved = await store.load();
  if (!saved) return null;

  const { data, error } = await rpc.rpc('verify_remember_token', {
    p_user_id: saved.userId,
    p_token: saved.token,
  });

  if (error || !data) {
    await store.clear();
    return null;
  }
  const row = data as RememberRow;
  return {
    session: { shopKey: row.id, shopName: row.shop_name, username: row.username },
    token: saved.token,
  };
}
