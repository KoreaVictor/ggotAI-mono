export interface SmsProvider {
  send(to: string, text: string): Promise<void>;
}

// 오프라인/개발: 코드를 로그로 출력(절대 응답에 싣지 않음)
export class FakeSmsProvider implements SmsProvider {
  async send(to: string, text: string): Promise<void> {
    console.log(`[FakeSMS] ${to}: ${text}`);
  }
}

// 골격(계정 준비 시 페이로드 규격 완성)
export class HttpSmsProvider implements SmsProvider {
  async send(to: string, text: string): Promise<void> {
    const url = Deno.env.get('SMS_API_URL');
    const key = Deno.env.get('SMS_API_KEY');
    if (!url || !key) throw new Error('SMS env 미설정');
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ to, text, from: Deno.env.get('SMS_SENDER') }),
    });
    if (!res.ok) throw new Error(`SMS 발송 실패 ${res.status}`);
  }
}

export function getProvider(): SmsProvider {
  return Deno.env.get('SMS_PROVIDER') === 'http' ? new HttpSmsProvider() : new FakeSmsProvider();
}
