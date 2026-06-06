// 다음(카카오) 우편번호 서비스 동적 로더. 실패 시 reject → 호출부에서 수기 입력 폴백.
const SCRIPT_SRC = 'https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js';

interface DaumPostcodeResult {
  zonecode: string;
  roadAddress: string;
  jibunAddress: string;
}
interface DaumPostcode {
  new (opts: { oncomplete: (data: DaumPostcodeResult) => void }): { open: () => void };
}
declare global {
  interface Window {
    daum?: { Postcode: DaumPostcode };
  }
}

function loadScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.daum?.Postcode) return resolve();
    const s = document.createElement('script');
    s.src = SCRIPT_SRC;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('주소찾기 스크립트 로드 실패'));
    document.head.appendChild(s);
  });
}

/** 우편번호 검색 팝업을 열고 선택된 주소를 반환한다. */
export async function openPostcodeSearch(): Promise<{ zonecode: string; address: string }> {
  await loadScript();
  return new Promise((resolve) => {
    new window.daum!.Postcode({
      oncomplete: (data) => resolve({ zonecode: data.zonecode, address: data.roadAddress || data.jibunAddress }),
    }).open();
  });
}
