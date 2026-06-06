import { describe, it, expect } from 'vitest';
import { authenticate, type AuthClient } from './authenticate';

// verify_login RPC 한 번만 호출 → fake rpc 로 주입
function fakeRpc(data: unknown, error: unknown = null): AuthClient {
  return { rpc: async () => ({ data, error }) } as unknown as AuthClient;
}

const APPROVED = { id: 7, shop_name: '서울꽃집', username: 'seoul', is_approved: 'Y' };

describe('authenticate (verify_login RPC)', () => {
  it('정상이면 세션을 반환한다', async () => {
    const r = await authenticate(fakeRpc(APPROVED), 'seoul', 'pw123');
    expect(r.ok).toBe(true);
    expect(r.session).toEqual({ shopKey: 7, shopName: '서울꽃집', username: 'seoul' });
  });

  it('불일치(null)면 일반화 에러', async () => {
    const r = await authenticate(fakeRpc(null), 'seoul', 'wrong');
    expect(r.ok).toBe(false);
    expect(r.session).toBeUndefined();
  });

  it('미승인 계정은 승인대기 에러', async () => {
    const r = await authenticate(fakeRpc({ ...APPROVED, is_approved: 'N' }), 'seoul', 'pw123');
    expect(r.ok).toBe(false);
    expect(r.error).toContain('승인');
  });

  it('RPC 에러면 실패를 반환한다', async () => {
    const r = await authenticate(fakeRpc(null, { message: 'boom' }), 'seoul', 'pw123');
    expect(r.ok).toBe(false);
  });
});
