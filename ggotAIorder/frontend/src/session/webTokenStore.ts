// 웹(브라우저)용 remember-token 저장소. Electron(safeStorage)이 없을 때 폴백.
// - 자동로그인 체크 → localStorage(브라우저 종료 후에도 유지)
// - 미체크라도 sessionStorage 에 저장 → 새로고침으로 로그인 화면에 튕기지 않음(탭 한정)
// 공개 테스트 배포라 토큰이 localStorage 에 평문 저장됨(anon/AES 키와 동일 수준의 테스트용 노출).

interface Saved { userId: number; token: string; }

const LS_KEY = 'ggotai.remember'; // 영구(자동로그인)
const SS_KEY = 'ggotai.session';  // 탭 한정(새로고침 유지)

function ls(): Storage | null { try { return globalThis.localStorage ?? null; } catch { return null; } }
function ss(): Storage | null { try { return globalThis.sessionStorage ?? null; } catch { return null; } }

export const webTokenStore = {
  save(userId: number, token: string, persistent: boolean): void {
    const v = JSON.stringify({ userId, token });
    try { ss()?.setItem(SS_KEY, v); } catch { /* storage 불가 환경 무시 */ }
    try {
      if (persistent) ls()?.setItem(LS_KEY, v);
      else ls()?.removeItem(LS_KEY);
    } catch { /* ignore */ }
  },
  load(): Saved | null {
    try {
      const raw = ls()?.getItem(LS_KEY) ?? ss()?.getItem(SS_KEY) ?? null;
      return raw ? (JSON.parse(raw) as Saved) : null;
    } catch { return null; }
  },
  clear(): void {
    try { ls()?.removeItem(LS_KEY); } catch { /* ignore */ }
    try { ss()?.removeItem(SS_KEY); } catch { /* ignore */ }
  },
};
