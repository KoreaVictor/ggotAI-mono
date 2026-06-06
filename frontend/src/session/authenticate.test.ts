import { describe, it, expect } from 'vitest';
import { authenticate, type AuthClient } from './authenticate';

function fakeClient(row: unknown, error: unknown = null): AuthClient {
  return {
    from: () => ({
      select: () => ({
        eq: () => ({
          maybeSingle: async () => ({ data: row, error }),
        }),
      }),
    }),
  } as unknown as AuthClient;
}

const APPROVED = {
  id: 7, shop_name: '서울꽃집', username: 'seoul', password: 'pw123', is_approved: 'Y',
};

describe('authenticate', () => {
  it('정상 자격증명이면 세션을 반환한다', async () => {
    const r = await authenticate(fakeClient(APPROVED), 'seoul', 'pw123');
    expect(r.ok).toBe(true);
    expect(r.session).toEqual({ shopKey: 7, shopName: '서울꽃집', username: 'seoul' });
  });

  it('비밀번호 불일치면 일반화 에러', async () => {
    const r = await authenticate(fakeClient(APPROVED), 'seoul', 'wrong');
    expect(r.ok).toBe(false);
    expect(r.session).toBeUndefined();
  });

  it('아이디 없으면(행 없음) 일반화 에러', async () => {
    const r = await authenticate(fakeClient(null), 'nobody', 'x');
    expect(r.ok).toBe(false);
  });

  it('미승인 계정은 승인대기 에러', async () => {
    const r = await authenticate(fakeClient({ ...APPROVED, is_approved: 'N' }), 'seoul', 'pw123');
    expect(r.ok).toBe(false);
    expect(r.error).toContain('승인');
  });

  it('조회 에러면 실패를 반환한다', async () => {
    const r = await authenticate(fakeClient(null, { message: 'boom' }), 'seoul', 'pw123');
    expect(r.ok).toBe(false);
  });
});
