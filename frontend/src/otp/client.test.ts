import { describe, it, expect } from 'vitest';
import {
  normalizePhone, sendOtp, verifyOtp, findUsername, resetPassword,
  type OtpRpc, type FunctionsClient,
} from './client';

function fakeRpc(data: unknown, error: unknown = null): OtpRpc {
  return (async () => ({ data, error })) as OtpRpc;
}
function fakeFns(data: unknown, error: unknown = null): FunctionsClient {
  return { invoke: async () => ({ data, error }) };
}

describe('normalizePhone', () => {
  it('숫자만 남긴다', () => {
    expect(normalizePhone('010-1234-5678')).toBe('01012345678');
  });
});

describe('sendOtp', () => {
  it('success:true 면 ok', async () => {
    const r = await sendOtp(fakeFns({ success: true }), '010-1', 'find_id');
    expect(r.ok).toBe(true);
  });
  it('함수 에러면 send_failed', async () => {
    const r = await sendOtp(fakeFns(null, { message: 'boom' }), '010-1', 'find_id');
    expect(r).toEqual({ ok: false, reason: 'send_failed' });
  });
  it('success:false 면 reason 전달', async () => {
    const r = await sendOtp(fakeFns({ success: false, reason: 'rate_limit' }), '010-1', 'find_id');
    expect(r).toEqual({ ok: false, reason: 'rate_limit' });
  });
});

describe('verifyOtp', () => {
  it('정답이면 토큰', async () => {
    const r = await verifyOtp(fakeRpc({ ok: true, token: 'tk' }), '010-1', 'find_id', '123456');
    expect(r).toEqual({ ok: true, token: 'tk' });
  });
  it('오답이면 reason 전달', async () => {
    const r = await verifyOtp(fakeRpc({ ok: false, reason: 'mismatch' }), '010-1', 'find_id', '0');
    expect(r).toEqual({ ok: false, reason: 'mismatch' });
  });
  it('RPC 에러면 error', async () => {
    const r = await verifyOtp(fakeRpc(null, { message: 'boom' }), '010-1', 'find_id', '0');
    expect(r).toEqual({ ok: false, reason: 'error' });
  });
});

describe('findUsername', () => {
  it('성공이면 username', async () => {
    const r = await findUsername(fakeRpc({ ok: true, username: 'seoul' }), '010-1', '서울꽃집', 'tk');
    expect(r).toEqual({ ok: true, username: 'seoul' });
  });
  it('없음이면 not_found', async () => {
    const r = await findUsername(fakeRpc({ ok: false, reason: 'not_found' }), '010-1', 'x', 'tk');
    expect(r).toEqual({ ok: false, reason: 'not_found' });
  });
});

describe('resetPassword', () => {
  it('성공이면 ok', async () => {
    const r = await resetPassword(fakeRpc({ ok: true }), '010-1', 'seoul', 'newpw', 'tk');
    expect(r).toEqual({ ok: true });
  });
  it('토큰무효면 invalid_token', async () => {
    const r = await resetPassword(fakeRpc({ ok: false, reason: 'invalid_token' }), '010-1', 'seoul', 'n', 'tk');
    expect(r).toEqual({ ok: false, reason: 'invalid_token' });
  });
});
