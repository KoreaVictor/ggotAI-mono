import { describe, it, expect } from 'vitest';
import { encryptPassword, decryptPassword } from './crypto';

// 백엔드 crypto.py(bytes.fromhex) 와 동일 키
const KEY = '00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff';

describe('AES crypto (백엔드 hex 계약 호환)', () => {
  it('encrypt→decrypt 라운드트립으로 원문을 복원한다', () => {
    const plain = 'ggot비밀!Pass_가나다';
    const enc = encryptPassword(plain, KEY);
    expect(enc).toContain(':');               // iv_hex:base64 포맷
    expect(decryptPassword(enc, KEY)).toBe(plain);
  });

  it('백엔드(crypto.py)가 만든 고정 벡터를 복호화한다 (hex 계약 실증)', () => {
    // 백엔드 encrypt("Ggot!Pass123", KEY, iv=00..0f) 로 생성한 결정적 벡터
    const VECTOR = '000102030405060708090a0b0c0d0e0f:cUzGelhg3Ctci6t160pS2g==';
    expect(decryptPassword(VECTOR, KEY)).toBe('Ggot!Pass123');
  });

  it('빈 입력은 빈 문자열을 반환한다', () => {
    expect(encryptPassword('', KEY)).toBe('');
    expect(decryptPassword('', KEY)).toBe('');
  });
});
