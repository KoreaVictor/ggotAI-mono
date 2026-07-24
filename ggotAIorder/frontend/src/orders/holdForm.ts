// 보류 주문 보완 폼의 배송일시 변환.
//
// DB 는 timestamptz(주로 UTC)로 돌려주는데 <input type="datetime-local"> 은 오프셋 없는
// 벽시계 문자열을 요구한다. 그대로 잘라 쓰면 사장님 화면에 UTC 시각이 뜨고, 손대지 않고
// 저장하면 9시간 밀려 저장된다. 꽃집은 전부 한국이므로 KST 고정으로 변환한다.

const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

/** 배송일 미상 센티넬(설계서 §6). 이 값이면 폼에 빈칸으로 보여 사장님이 채우게 한다. */
const DELIVERY_AT_UNKNOWN_YEAR = 2099;

/** timestamptz → `<input type="datetime-local">` 값(KST 벽시계, 'YYYY-MM-DDTHH:mm'). */
export function toDateTimeLocal(iso: string): string {
  const shifted = new Date(new Date(iso).getTime() + KST_OFFSET_MS);
  return shifted.toISOString().slice(0, 16);
}

/** `<input type="datetime-local">` 값 → KST 오프셋이 붙은 ISO 문자열. */
export function toKstIso(local: string): string {
  return `${local}:00+09:00`;
}

/** 배송일이 '미상'(2099 센티넬)인지. 오프셋 표기가 달라도 판정된다. */
export function isUnknownDeliveryAt(iso: string): boolean {
  return new Date(iso).getUTCFullYear() >= DELIVERY_AT_UNKNOWN_YEAR;
}
