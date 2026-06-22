import { describe, it, expect } from 'vitest';
import { deriveCurrentTask, latestForChannel, CHANNELS, channelLabel } from './currentTask';
import type { FeedRow } from './client';

function row(p: Partial<FeedRow>): FeedRow {
  return { id: 1, channel_order: '핸드폰', customer_name: null, stt_text: null, is_order: null, rpa_status: null, created_at: '2026-06-07T00:00:00Z', ...p };
}

describe('deriveCurrentTask', () => {
  it('행 없음 → 대기', () => expect(deriveCurrentTask(undefined)).toBe('대기'));
  it('is_order null + stt 없음 → STT 분석중', () => expect(deriveCurrentTask(row({ stt_text: null }))).toBe('STT 분석중'));
  it('is_order null + stt 있음 → 주문정보 분석중', () => expect(deriveCurrentTask(row({ stt_text: '장미' }))).toBe('주문정보 분석중'));
  it('N → 주문 아님', () => expect(deriveCurrentTask(row({ is_order: 'N' }))).toBe('주문 아님'));
  it('Y + ready → 입력 대기', () => expect(deriveCurrentTask(row({ is_order: 'Y', rpa_status: 'ready' }))).toBe('입력 대기'));
  it('Y + success → 입력 완료', () => expect(deriveCurrentTask(row({ is_order: 'Y', rpa_status: 'success' }))).toBe('입력 완료'));
  it('Y + manual → 수동입력 필요', () => expect(deriveCurrentTask(row({ is_order: 'Y', rpa_status: 'manual' }))).toBe('수동입력 필요'));
  it('Y + fail → 입력 실패', () => expect(deriveCurrentTask(row({ is_order: 'Y', rpa_status: 'fail' }))).toBe('입력 실패'));
  it('Y + rpa null → 대기', () => expect(deriveCurrentTask(row({ is_order: 'Y', rpa_status: null }))).toBe('대기'));
});

describe('latestForChannel', () => {
  it('해당 채널 첫 매치 반환(피드는 desc 전제)', () => {
    const feed = [row({ id: 2, channel_order: '쇼핑몰' }), row({ id: 1, channel_order: '핸드폰' })];
    expect(latestForChannel(feed, '핸드폰')?.id).toBe(1);
    expect(latestForChannel(feed, '없음')).toBeUndefined();
  });
});

describe('CHANNELS', () => {
  it('6칸 정의', () => expect(CHANNELS.length).toBe(6));
  it('핸드폰1·2는 같은 channelOrder 공유', () => {
    const hp = CHANNELS.filter((c) => c.channelOrder === '핸드폰');
    expect(hp.map((c) => c.label)).toEqual(['핸드폰1', '핸드폰2']);
  });
  it('가게음성 채널은 매장판매로 라벨 표기(channelOrder는 가게음성 유지)', () => {
    const voice = CHANNELS.find((c) => c.channelOrder === '가게음성');
    expect(voice?.label).toBe('매장판매');
  });
});

describe('channelLabel', () => {
  it('가게음성 → 매장판매', () => expect(channelLabel('가게음성')).toBe('매장판매'));
  it('그 외 채널은 그대로', () => {
    expect(channelLabel('핸드폰')).toBe('핸드폰');
    expect(channelLabel('가게전화')).toBe('가게전화');
    expect(channelLabel('쇼핑몰')).toBe('쇼핑몰');
  });
});
