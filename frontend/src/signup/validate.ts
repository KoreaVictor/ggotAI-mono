export interface SignupForm {
  username: string;
  password: string;
  passwordConfirm: string;
  shopName: string;
  representativeName: string;
  mobile: string;
  email?: string;
  landline?: string;
  address?: string;
  addressDetail?: string;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** 검증 통과 시 null, 실패 시 사용자 메시지 반환. */
export function validateSignup(f: SignupForm): string | null {
  if (!f.username.trim()) return '아이디를 입력해주세요';
  if (!f.password) return '비밀번호를 입력해주세요';
  if (f.password !== f.passwordConfirm) return '비밀번호가 일치하지 않습니다';
  if (!f.shopName.trim()) return '꽃집명을 입력해주세요';
  if (!f.representativeName.trim()) return '대표자명을 입력해주세요';
  if (!f.mobile.trim()) return '핸드폰 번호를 입력해주세요';
  if (f.email && !EMAIL_RE.test(f.email)) return '이메일 형식이 올바르지 않습니다';
  return null;
}
