import CryptoJS from 'crypto-js';

const ENCRYPTION_KEY = import.meta.env.VITE_AES_ENCRYPTION_KEY;

/**
 * 비밀번호를 AES-256-CBC 방식으로 안전하게 암호화합니다.
 * 백엔드(Python cryptography)와의 상호 호환성을 위해 IV와 암호문을 ":"로 연결해 반환합니다.
 * 
 * @param plainText 암호화할 평문 비밀번호
 * @returns "IV(Hex값):암호문(Base64값)" 포맷의 문자열
 */
export function encryptPassword(plainText: string): string {
  if (!plainText) return '';
  if (!ENCRYPTION_KEY) {
    console.error('VITE_AES_ENCRYPTION_KEY 환경 변수가 제공되지 않았습니다.');
    return plainText; // 대체 작동
  }

  try {
    // 32바이트 대칭키 획득 (UTF-8 인코딩)
    const key = CryptoJS.enc.Utf8.parse(ENCRYPTION_KEY.substring(0, 32)); // 32자 제한 준수
    
    // 16바이트 무작위 IV 생성
    const iv = CryptoJS.lib.WordArray.random(16);

    // 암호화 수행 (CBC 모드, PKCS7 패딩)
    const encrypted = CryptoJS.AES.encrypt(plainText, key, {
      iv: iv,
      mode: CryptoJS.mode.CBC,
      padding: CryptoJS.pad.Pkcs7,
    });

    // IV(16진수 문자열)와 암호문(Base64 문자열)을 콜론으로 구분하여 결합
    const ivHex = iv.toString(CryptoJS.enc.Hex);
    const cipherTextBase64 = encrypted.toString();

    return `${ivHex}:${cipherTextBase64}`;
  } catch (error) {
    console.error('암호화 실패:', error);
    return '';
  }
}
