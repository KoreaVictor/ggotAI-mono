import CryptoJS from 'crypto-js';

const ENV_KEY = import.meta.env.VITE_AES_ENCRYPTION_KEY as string | undefined;

/**
 * 64자 hex 키 문자열을 32바이트 WordArray 로 파싱한다.
 * 백엔드(Python `bytes.fromhex`)와 동일한 키여야 호환된다.
 */
function parseKey(key: string | undefined): CryptoJS.lib.WordArray {
  if (!key) throw new Error('AES 키가 없습니다 (VITE_AES_ENCRYPTION_KEY).');
  return CryptoJS.enc.Hex.parse(key);
}

/**
 * 평문을 AES-256-CBC(PKCS7) 로 암호화해 "iv_hex:ciphertext_base64" 를 반환한다.
 * key 미지정 시 환경변수 키 사용(테스트는 명시 키 주입).
 */
export function encryptPassword(plainText: string, key: string | undefined = ENV_KEY): string {
  if (!plainText) return '';
  try {
    const wKey = parseKey(key);
    const iv = CryptoJS.lib.WordArray.random(16);
    const encrypted = CryptoJS.AES.encrypt(plainText, wKey, {
      iv,
      mode: CryptoJS.mode.CBC,
      padding: CryptoJS.pad.Pkcs7,
    });
    return `${iv.toString(CryptoJS.enc.Hex)}:${encrypted.toString()}`;
  } catch (error) {
    console.error('암호화 실패:', error);
    return '';
  }
}

/**
 * "iv_hex:ciphertext_base64" 를 복호화해 평문을 반환한다(눈 아이콘 가시화용).
 * 실패 시 빈 문자열.
 */
export function decryptPassword(dbValue: string, key: string | undefined = ENV_KEY): string {
  if (!dbValue) return '';
  try {
    const wKey = parseKey(key);
    const sep = dbValue.indexOf(':');
    if (sep < 0) return '';
    const iv = CryptoJS.enc.Hex.parse(dbValue.slice(0, sep));
    const cipherText = dbValue.slice(sep + 1);
    const decrypted = CryptoJS.AES.decrypt(cipherText, wKey, {
      iv,
      mode: CryptoJS.mode.CBC,
      padding: CryptoJS.pad.Pkcs7,
    });
    return decrypted.toString(CryptoJS.enc.Utf8);
  } catch (error) {
    console.error('복호화 실패:', error);
    return '';
  }
}
