import { describe, it, expect, vi } from 'vitest';
import { restoreSession, type RpcLike, type TokenStore } from './rememberToken';

function fakeRpc(data: unknown, error: unknown = null): RpcLike {
  return { rpc: async () => ({ data, error }) };
}
function fakeStore(saved: { userId: number; token: string } | null) {
  return { load: vi.fn(async () => saved), clear: vi.fn(async () => {}) } as TokenStore & {
    load: ReturnType<typeof vi.fn>; clear: ReturnType<typeof vi.fn>;
  };
}

describe('restoreSession', () => {
  it('저장 토큰이 없으면 null', async () => {
    const store = fakeStore(null);
    expect(await restoreSession(fakeRpc(null), store)).toBeNull();
    expect(store.clear).not.toHaveBeenCalled();
  });

  it('검증 성공이면 세션+토큰 반환', async () => {
    const store = fakeStore({ userId: 7, token: 't' });
    const r = await restoreSession(fakeRpc({ id: 7, shop_name: '서울꽃집', username: 'seoul' }), store);
    expect(r).toEqual({ session: { shopKey: 7, shopName: '서울꽃집', username: 'seoul' }, token: 't' });
  });

  it('검증 실패(null)면 null + 로컬 토큰 정리', async () => {
    const store = fakeStore({ userId: 7, token: 't' });
    expect(await restoreSession(fakeRpc(null), store)).toBeNull();
    expect(store.clear).toHaveBeenCalled();
  });

  it('RPC 에러면 null + 로컬 토큰 정리', async () => {
    const store = fakeStore({ userId: 7, token: 't' });
    expect(await restoreSession(fakeRpc(null, { message: 'boom' }), store)).toBeNull();
    expect(store.clear).toHaveBeenCalled();
  });
});
