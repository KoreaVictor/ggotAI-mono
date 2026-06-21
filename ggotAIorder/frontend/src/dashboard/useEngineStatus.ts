import { useState, useEffect } from 'react';
import { supabase } from '../supabase';
import { getDashboard, type DashRpc } from './client';

const rpc: DashRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<DashRpc>;

export type EngineStatus = 'RUNNING' | 'STOPPED' | 'LOADING';

/**
 * 수집엔진 가동 여부를 백엔드 하트비트(get_dashboard.engine_alive)로 폴링한다.
 * 헤더 배지와 상황판이 동일 신호를 쓰게 해 표시가 어긋나지 않도록 한다.
 * (로그인 전이거나 토큰이 없으면 판단 불가 → STOPPED)
 */
export function useEngineStatus(shopKey: number, readToken: string | null): EngineStatus {
  const [status, setStatus] = useState<EngineStatus>('LOADING');
  useEffect(() => {
    let active = true;
    if (!shopKey || !readToken) { setStatus('STOPPED'); return; }
    const check = async () => {
      const r = await getDashboard(rpc, shopKey, readToken);
      if (!active || !r.ok || !r.data) return;
      setStatus(r.data.engineAlive ? 'RUNNING' : 'STOPPED');
    };
    check();
    const t = setInterval(check, 3000);
    return () => { active = false; clearInterval(t); };
  }, [shopKey, readToken]);
  return status;
}
