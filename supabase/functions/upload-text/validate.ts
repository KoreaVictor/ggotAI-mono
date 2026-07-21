// upload-text 요청 검증 (Deno 비의존 순수 로직 — frontend 의 vitest 로 테스트한다).
//
// 필드명·멱등성 키는 upload-call 과 일부러 동일하게 맞췄다(call_date/call_time).
// 저장 대상이 같은 server_call_history 이므로 새 이름을 만들 이유가 없다.

export const TEXT_CHANNELS = ["카톡", "문자"] as const;
export type TextChannel = (typeof TEXT_CHANNELS)[number];

export interface ValidUpload {
  ok: true;
  channelOrder: TextChannel;
  userPhoneNumber: string;
  phoneNumber: string;
  senderName: string;
  sttText: string;
  callDate: string;
  callTime: string;
}

export interface InvalidUpload {
  ok: false;
  message: string;
}

export type ValidationResult = ValidUpload | InvalidUpload;

/** formData.get 결과를 문자열로 정규화한다(File 등 비문자열·null 은 빈 문자열). */
function str(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * 텍스트 주문 업로드 요청을 검증한다.
 *
 * 채널은 '카톡'|'문자'만 허용한다 — upload-call 처럼 조용히 기본값으로 강제하면
 * 잘못 보낸 건이 엉뚱한 채널로 적재돼 원인 추적이 어려워진다.
 *
 * 발신번호는 문자만 필수다. 카톡 알림은 표시명만 주고 번호를 알려주지 않으므로
 * 카톡은 발신자 표시명을 대신 요구한다.
 */
export function validateTextUpload(
  get: (key: string) => unknown,
): ValidationResult {
  const channel = str(get("channel_order"));
  if (!(TEXT_CHANNELS as readonly string[]).includes(channel)) {
    return { ok: false, message: "channel_order 는 '카톡' 또는 '문자'만 허용합니다." };
  }
  const channelOrder = channel as TextChannel;

  const userPhoneNumber = str(get("user_phone_number"));
  const callDate = str(get("call_date"));
  const callTime = str(get("call_time"));
  const sttText = str(get("stt_text"));
  const phoneNumber = str(get("phone_number"));
  const senderName = str(get("customer_name"));

  if (!userPhoneNumber || !callDate || !callTime) {
    return { ok: false, message: "필수 파라미터가 누락됐습니다." };
  }
  if (!sttText) {
    return { ok: false, message: "메시지 본문(stt_text)이 비어 있습니다." };
  }
  if (channelOrder === "문자" && !phoneNumber) {
    return { ok: false, message: "문자는 발신번호(phone_number)가 필요합니다." };
  }
  if (channelOrder === "카톡" && !senderName) {
    return { ok: false, message: "카톡은 발신자 표시명(customer_name)이 필요합니다." };
  }

  return {
    ok: true,
    channelOrder,
    userPhoneNumber,
    phoneNumber,
    senderName,
    sttText,
    callDate,
    callTime,
  };
}
