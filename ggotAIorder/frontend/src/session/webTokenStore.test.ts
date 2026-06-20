import { describe, it, expect, beforeEach } from 'vitest';
import { webTokenStore } from './webTokenStore';

class FakeStorage {
  private m = new Map<string, string>();
  getItem(k: string) { return this.m.has(k) ? this.m.get(k)! : null; }
  setItem(k: string, v: string) { this.m.set(k, String(v)); }
  removeItem(k: string) { this.m.delete(k); }
  get size() { return this.m.size; }
}

beforeEach(() => {
  (globalThis as unknown as { localStorage: unknown }).localStorage = new FakeStorage();
  (globalThis as unknown as { sessionStorage: unknown }).sessionStorage = new FakeStorage();
});

describe('webTokenStore', () => {
  it('미저장이면 load 는 null', () => {
    expect(webTokenStore.load()).toBeNull();
  });

  it('자동로그인(persistent) 저장 → load 복원 + localStorage 보존', () => {
    webTokenStore.save(7, 'tk', true);
    expect(webTokenStore.load()).toEqual({ userId: 7, token: 'tk' });
    const ls = globalThis.localStorage as unknown as FakeStorage;
    expect(ls.size).toBe(1);
  });

  it('미체크 저장 → sessionStorage 로 새로고침 유지, localStorage 엔 안 남김', () => {
    webTokenStore.save(7, 'tk', false);
    expect(webTokenStore.load()).toEqual({ userId: 7, token: 'tk' });
    const ls = globalThis.localStorage as unknown as FakeStorage;
    expect(ls.size).toBe(0);
  });

  it('영구 저장은 탭 종료(sessionStorage 소실) 후에도 복원', () => {
    webTokenStore.save(7, 'tk', true);
    (globalThis as unknown as { sessionStorage: unknown }).sessionStorage = new FakeStorage();
    expect(webTokenStore.load()).toEqual({ userId: 7, token: 'tk' });
  });

  it('clear 후 load 는 null', () => {
    webTokenStore.save(7, 'tk', true);
    webTokenStore.clear();
    expect(webTokenStore.load()).toBeNull();
  });
});
