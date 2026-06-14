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
    case 'fail':    return '입력 실패';
    default:        return '대기';
  }
}

export interface ChannelDef { label: string; channelOrder: string; configKey: keyof Config; }
export const CHANNELS: ChannelDef[] = [
  { label: '가게전화', channelOrder: '가게전화', configKey: 'garjeon' },
  { label: '핸드폰1',  channelOrder: '핸드폰',   configKey: 'hp1' },
  { label: '핸드폰2',  channelOrder: '핸드폰',   configKey: 'hp2' },
  { label: '가게음성', channelOrder: '가게음성', configKey: 'voice' },
  { label: '쇼핑몰',   channelOrder: '쇼핑몰',   configKey: 'mall' },
  { label: '인터라넷', channelOrder: '인터라넷', configKey: 'intranet' },
];

export function latestForChannel(feed: FeedRow[], channelOrder: string): FeedRow | undefined {
  return feed.find((r) => r.channel_order === channelOrder);
}
