import { describe, it, expect } from 'vitest';
import { getProfile, updateAccount, profileMessage, type ProfileRpc } from './client';

function fakeRpc(data: unknown, error: unknown = null): ProfileRpc {
  return (async () => ({ data, error })) as ProfileRpc;
}

const PROFILE = {
  username: 'seoul', shop_name: '서울꽃집', representative_name: '홍길동',
  landline_number: null, mobile_number: '01011112222', email: null,
  address: null, address_detail: null, is_approved: 'Y',
};

describe('getProfile', () => {
  it('성공이면 profile 반환', async () => {
    const r = await getProfile(fakeRpc({ ok: true, profile: PROFILE }), 'seoul');
    expect(r).toEqual({ ok: true, profile: PROFILE });
  });
  it('없음이면 not_found', async () => {
    const r = await getProfile(fakeRpc({ ok: false, reason: 'not_found' }), 'x');
    expect(r).toEqual({ ok: false, reason: 'not_found' });
  });
  it('RPC 에러면 error', async () => {
    const r = await getProfile(fakeRpc(null, { message: 'boom' }), 'x');
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});

describe('updateAccount', () => {
  const base = {
    username: 'seoul', authToken: 'tk', shopName: '새', representativeName: '대표',
    landline: '', email: '', address: '', addressDetail: '',
  };
  it('성공이면 profile 반환', async () => {
    const r = await updateAccount(fakeRpc({ ok: true, profile: PROFILE }), base);
    expect(r).toEqual({ ok: true, profile: PROFILE });
  });
  it('reason 전달(bad_password)', async () => {
    const r = await updateAccount(fakeRpc({ ok: false, reason: 'bad_password' }), base);
    expect(r).toEqual({ ok: false, reason: 'bad_password' });
  });
  it('RPC 에러면 error', async () => {
    const r = await updateAccount(fakeRpc(null, { message: 'boom' }), base);
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});

describe('profileMessage', () => {
  it('reason 별 한글 매핑', () => {
    expect(profileMessage('bad_password')).toBe('현재 비밀번호가 올바르지 않습니다');
    expect(profileMessage('new_phone_unverified')).toBe('새 핸드폰 인증을 완료해주세요');
    expect(profileMessage('invalid_token')).toBe('인증이 만료되었습니다. 다시 인증해주세요');
    expect(profileMessage('not_found')).toBe('회원 정보를 찾을 수 없습니다');
    expect(profileMessage(undefined)).toBe('저장 중 오류가 발생했습니다. 다시 시도해주세요');
  });
});
