import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { supabase } from '../supabase';
import { authenticate, type Session, type AuthResult, type AuthClient } from './authenticate';
import { restoreSession, type RpcLike, type TokenStore } from './rememberToken';

interface SessionContextValue {
  session: Session | null;
  authReady: boolean; // 자동로그인 검증 완료 여부(셸 로딩 게이팅)
  readToken: string | null;
  login: (username: string, password: string, rememberMe?: boolean) => Promise<AuthResult>;
  logout: () => void;
  updateShopName: (name: string) => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

// supabase 의 .rpc() 는 구조적으로 AuthClient/RpcLike 를 만족(타입은 단일 캐스트)
const rpcClient = supabase as unknown as AuthClient & RpcLike;

// Electron safeStorage 어댑터(웹 dev 에서는 무음 skip)
const electronStore: TokenStore = {
  load: async () => (await window.electronAPI?.loadRememberToken?.()) ?? null,
  clear: async () => { await window.electronAPI?.clearRememberToken?.(); },
};

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [readToken, setReadToken] = useState<string | null>(null);

  // 앱 시작 1회: 자동로그인 시도
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const restored = await restoreSession(rpcClient, electronStore);
        if (active && restored) { setSession(restored.session); setReadToken(restored.token); }
      } finally {
        if (active) setAuthReady(true);
      }
    })();
    return () => { active = false; };
  }, []);

  const login = useCallback(async (username: string, password: string, rememberMe = false) => {
    const result = await authenticate(rpcClient, username, password);
    if (result.ok && result.session) {
      setSession(result.session);
      const { data: token } = await rpcClient.rpc('issue_remember_token', { p_user_id: result.session.shopKey });
      if (typeof token === 'string') {
        setReadToken(token);
        if (rememberMe && window.electronAPI?.saveRememberToken) {
          await window.electronAPI.saveRememberToken(result.session.shopKey, token);
        }
      }
    }
    return result;
  }, []);

  const logout = useCallback(() => {
    if (session) void rpcClient.rpc('clear_remember_token', { p_user_id: session.shopKey });
    void window.electronAPI?.clearRememberToken?.();
    setSession(null);
    setReadToken(null);
  }, [session]);

  const updateShopName = useCallback((name: string) => {
    setSession((s) => (s ? { ...s, shopName: name } : s));
  }, []);

  return (
    <SessionContext.Provider value={{ session, authReady, readToken, login, logout, updateShopName }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession 은 SessionProvider 내부에서만 사용해야 합니다.');
  return ctx;
}
