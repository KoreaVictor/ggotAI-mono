import type { Config, FeedRow } from './client';

export function deriveCurrentTask(row?: FeedRow): string {
  if (!row) return '대기';
  if (row.is_order == null) {
    return row.stt_text && row.stt_text.trim() !== '' ? '주문정보 분석중' : 'STT 분석중';
  }
  if (row.is_order === 'N') return '주문 아님';
  switch (row.rpa_status) {
    case 'ready':   return '입력 대기';
    case 'success': return '입력 완료';
    case 'manual':  return '수동입력 필요';
    case 'fail':    return '입력 실패';
    default:        return '대기';
  }
}

export interface ChannelDef { label: string; channelOrder: string; configKey: keyof Config; }
export const CHANNELS: ChannelDef[] = [
  { label: '가게전화', channelOrder: '가게전화', configKey: 'garjeon' },
  { label: '핸드폰1',  channelOrder: '핸드폰',   configKey: 'hp1' },
  { label: '핸드폰2',  channelOrder: '핸드폰',   configKey: 'hp2' },
  { label: '매장판매', channelOrder: '가게음성', configKey: 'voice' },
  { label: '쇼핑몰',   channelOrder: '쇼핑몰',   configKey: 'mall' },
  { label: '인터라넷', channelOrder: '인터라넷', configKey: 'intranet' },
];

// DB의 channel_order 값을 사용자 표시용 라벨로 변환한다. DB값('가게음성')은 그대로 두고
// 화면에서만 '매장판매'로 보여준다(상황판 피드·주문내역 표/모달 공용).
export function channelLabel(channelOrder: string): string {
  return channelOrder === '가게음성' ? '매장판매' : channelOrder;
}

export function latestForChannel(feed: FeedRow[], channelOrder: string): FeedRow | undefined {
  return feed.find((r) => r.channel_order === channelOrder);
}
