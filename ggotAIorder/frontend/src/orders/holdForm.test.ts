import { describe, expect, it } from 'vitest';

import { isUnknownDeliveryAt, toDateTimeLocal, toKstIso } from './holdForm';

describe('toDateTimeLocal', () => {
  it('UTC 로 저장된 배송일시를 한국 시각으로 보여준다', () => {
    // DB 는 UTC(06:00Z)로 갖고 있지만 사장님에게는 15:00 으로 보여야 한다.
    // 그대로 잘라 쓰면 06:00 이 뜨고, 저장 시 9시간 밀린다.
    expect(toDateTimeLocal('2026-07-22T06:00:00+00:00')).toBe('2026-07-22T15:00');
  });

  it('자정을 넘기는 경우에도 날짜가 함께 넘어간다', () => {
    // 2026-07-21T16:00Z = 2026-07-22 01:00 KST
    expect(toDateTimeLocal('2026-07-21T16:00:00+00:00')).toBe('2026-07-22T01:00');
  });

  it('이미 KST 오프셋이 붙어 있어도 같은 벽시계 시각을 준다', () => {
    expect(toDateTimeLocal('2026-07-22T15:00:00+09:00')).toBe('2026-07-22T15:00');
  });
});

describe('toKstIso', () => {
  it('입력칸 값을 KST ISO 로 되돌린다', () => {
    expect(toKstIso('2026-07-22T15:00')).toBe('2026-07-22T15:00:00+09:00');
  });

  it('화면에 보여준 값을 그대로 저장하면 원래 시각이 유지된다', () => {
    // 왕복(round-trip)이 어긋나면 사장님이 손대지 않은 칸도 시각이 밀린다.
    const stored = '2026-07-22T06:00:00+00:00';

    const roundTripped = toKstIso(toDateTimeLocal(stored));

    expect(new Date(roundTripped).toISOString()).toBe(new Date(stored).toISOString());
  });
});

describe('isUnknownDeliveryAt', () => {
  it('2099 센티넬은 미상으로 본다', () => {
    // 배송일 미상일 때 NOT NULL 을 채우려고 넣는 값 — 빈칸으로 보여야 한다.
    expect(isUnknownDeliveryAt('2099-12-31T23:59:59+09:00')).toBe(true);
    expect(isUnknownDeliveryAt('2099-12-31T14:59:59+00:00')).toBe(true);
  });

  it('실제 배송일은 미상이 아니다', () => {
    expect(isUnknownDeliveryAt('2026-07-22T06:00:00+00:00')).toBe(false);
  });
});
