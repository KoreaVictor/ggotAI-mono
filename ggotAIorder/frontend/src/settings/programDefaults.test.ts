import { describe, it, expect } from 'vitest';
import { RPA_PROGRAM_DEFAULT_URL, nextRpaUrl } from './programDefaults';

describe('nextRpaUrl', () => {
  const FLOWER = RPA_PROGRAM_DEFAULT_URL.flowernt;

  it('빈 URL에서 FlowerNT 선택 시 기본 URL을 채운다', () => {
    expect(nextRpaUrl('flowernt', '', '')).toBe(FLOWER);
    expect(nextRpaUrl('flowernt', null, '')).toBe(FLOWER);
  });

  it('사용자가 직접 넣은 URL은 보존한다', () => {
    expect(nextRpaUrl('flowernt', 'https://my.custom/url', '')).toBe('https://my.custom/url');
  });

  it('이전 타입 기본값이 들어있으면 새 타입 기본값으로 교체한다', () => {
    // flowernt 기본값 상태에서 기본URL 없는 타입(roseweb)으로 바꾸면 유지(roseweb 기본 미정)
    expect(nextRpaUrl('roseweb', FLOWER, 'flowernt')).toBe(FLOWER);
  });

  it('기본값이 없는 타입(선택 안 함/etc/roseweb)은 현재 URL을 유지한다', () => {
    expect(nextRpaUrl('', '', '')).toBe('');
    expect(nextRpaUrl('etc', 'https://x', 'flowernt')).toBe('https://x');
  });
});
