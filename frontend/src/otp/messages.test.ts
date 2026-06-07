import { describe, it, expect } from 'vitest';
import { otpMessage } from './messages';

describe('otpMessage', () => {
  it('만료', () => expect(otpMessage('expired')).toContain('만료'));
  it('오답', () => expect(otpMessage('mismatch')).toContain('일치'));
  it('시도초과', () => expect(otpMessage('too_many')).toContain('초과'));
  it('없음', () => expect(otpMessage('not_found')).toContain('요청'));
  it('토큰무효', () => expect(otpMessage('invalid_token')).toContain('인증'));
  it('레이트리밋', () => expect(otpMessage('rate_limit')).toContain('잠시'));
  it('발송실패', () => expect(otpMessage('send_failed')).toContain('발송'));
  it('미상', () => expect(otpMessage(undefined)).toContain('오류'));
});
