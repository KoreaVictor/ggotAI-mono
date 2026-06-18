// 관리 프로그램(RPA) 종류별 기본 웹 주소(랜딩 URL).
// 종류 선택 시 웹 주소를 자동 채우되, 사용자가 직접 넣은 값은 보존한다.
export const RPA_PROGRAM_DEFAULT_URL: Record<string, string> = {
  flowernt: 'https://www.flowernt.com/main.asp?checkintro=Y',
  // roseweb 등 다른 프로그램 기본 URL은 확정되면 여기에 추가.
};

/**
 * 프로그램 종류가 newType 으로 바뀔 때 채워 넣을 웹 주소를 계산한다.
 * - newType 의 기본 URL이 있고, 현재 URL이 비었거나 '이전 타입의 기본값'이면 → 새 기본값으로 채움
 * - 사용자가 직접 입력한 URL이면 보존
 * - 기본 URL이 없는 타입(선택 안 함/roseweb/etc)이면 현재 값 유지
 */
export function nextRpaUrl(
  newType: string,
  currentUrl: string | null,
  prevType: string,
): string | null {
  const def = RPA_PROGRAM_DEFAULT_URL[newType];
  if (!def) return currentUrl ?? null;
  const cur = (currentUrl ?? '').trim();
  const prevDef = RPA_PROGRAM_DEFAULT_URL[prevType] ?? '';
  if (cur === '' || cur === prevDef) return def;
  return currentUrl ?? null;
}
