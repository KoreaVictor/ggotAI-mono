import { describe, expect, it } from 'vitest';

import { validateTextUpload } from './validate';

/** formData.get 을 흉내내는 헬퍼 — 없는 키는 null. */
function form(fields: Record<string, string>) {
  return (key: string) => (key in fields ? fields[key] : null);
}

const SMS = {
  channel_order: '문자',
  user_phone_number: '01011112222',
  phone_number: '01033334444',
  customer_name: '김철수',
  stt_text: '내일 오후 3시 근조화환 10만원짜리 부탁드려요',
  call_date: '2026-07-21',
  call_time: '14:30:00',
};

describe('validateTextUpload', () => {
  it('문자 주문의 필수값이 모두 있으면 통과한다', () => {
    const result = validateTextUpload(form(SMS));

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.channelOrder).toBe('문자');
    expect(result.sttText).toBe(SMS.stt_text);
    expect(result.callDate).toBe('2026-07-21');
  });

  it('카톡·문자 외 채널은 거부한다', () => {
    // 조용히 기본값으로 강제하면 엉뚱한 채널로 적재돼 원인 추적이 어려워진다.
    for (const channel of ['핸드폰', '가게음성', '쇼핑몰', '']) {
      const result = validateTextUpload(form({ ...SMS, channel_order: channel }));
      expect(result.ok, `channel=${channel}`).toBe(false);
    }
  });

  it('메시지 본문이 없거나 공백뿐이면 거부한다', () => {
    expect(validateTextUpload(form({ ...SMS, stt_text: '' })).ok).toBe(false);
    expect(validateTextUpload(form({ ...SMS, stt_text: '   ' })).ok).toBe(false);
  });

  it('기기 번호·수신일시가 없으면 거부한다', () => {
    expect(validateTextUpload(form({ ...SMS, user_phone_number: '' })).ok).toBe(false);
    expect(validateTextUpload(form({ ...SMS, call_date: '' })).ok).toBe(false);
    expect(validateTextUpload(form({ ...SMS, call_time: '' })).ok).toBe(false);
  });

  it('문자는 발신번호가 필수다', () => {
    expect(validateTextUpload(form({ ...SMS, phone_number: '' })).ok).toBe(false);
  });

  it('카톡은 발신번호 없이 표시명만으로 통과한다', () => {
    // 카톡 알림은 표시명만 주고 번호를 알려주지 않는다.
    const result = validateTextUpload(
      form({ ...SMS, channel_order: '카톡', phone_number: '', customer_name: '이영희' }),
    );

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.channelOrder).toBe('카톡');
    expect(result.phoneNumber).toBe('');
    expect(result.senderName).toBe('이영희');
  });

  it('카톡인데 표시명도 없으면 거부한다', () => {
    const result = validateTextUpload(
      form({ ...SMS, channel_order: '카톡', phone_number: '', customer_name: '' }),
    );
    expect(result.ok).toBe(false);
  });

  it('앞뒤 공백은 제거해 반환한다', () => {
    const result = validateTextUpload(form({ ...SMS, stt_text: '  장미 5만원  ' }));

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.sttText).toBe('장미 5만원');
  });
});
