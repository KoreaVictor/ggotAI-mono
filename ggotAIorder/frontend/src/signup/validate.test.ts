import { describe, it, expect } from 'vitest';
import { validateSignup, type SignupForm } from './validate';

const OK: SignupForm = {
  username: 'seoul', password: 'pw123456', passwordConfirm: 'pw123456',
  shopName: '서울꽃집', representativeName: '홍길동', mobile: '01012345678', email: 'a@b.com',
};

describe('validateSignup', () => {
  it('정상 폼은 null(에러 없음)', () => {
    expect(validateSignup(OK)).toBeNull();
  });
  it('필수값(아이디) 누락 시 에러', () => {
    expect(validateSignup({ ...OK, username: '' })).toContain('아이디');
  });
  it('비밀번호 불일치 시 에러', () => {
    expect(validateSignup({ ...OK, passwordConfirm: 'different' })).toContain('비밀번호');
  });
  it('이메일 형식 오류 시 에러', () => {
    expect(validateSignup({ ...OK, email: 'not-an-email' })).toContain('이메일');
  });
  it('이메일 미입력은 허용(선택값)', () => {
    expect(validateSignup({ ...OK, email: '' })).toBeNull();
  });
});
