import React, { createContext, useContext, useState, useCallback } from 'react';
import { supabase } from '../supabase';
import { authenticate, type AuthClient, type Session, type AuthResult } from './authenticate';

// supabase-js 의 쿼리 빌더는 실제로 .from().select().eq().maybeSingle() 를 제공해
// 런타임상 AuthClient 계약을 만족하지만, PostgrestBuilder(thenable)·깊은 제네릭 테이블
// 타입 때문에 TS 구조적 할당이 실패한다. 단일 호출 지점에서만 좁혀 어댑팅한다.
const authClient = supabase as unknown as AuthClient;

interface SessionContextValue {
  session: Session | null;
  login: (username: string, password: string) => Promise<AuthResult>;
  logout: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);

  const login = useCallback(async (username: string, password: string) => {
    const result = await authenticate(authClient, username, password);
    if (result.ok && result.session) setSession(result.session);
    return result;
  }, []);

  const logout = useCallback(() => setSession(null), []);

  return (
    <SessionContext.Provider value={{ session, login, logout }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession 은 SessionProvider 내부에서만 사용해야 합니다.');
  return ctx;
}
