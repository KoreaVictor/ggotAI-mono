import { CircleDot } from 'lucide-react';
import type { Session } from '../session/authenticate';
import type { ServiceStatus } from '../types/electron';

type Route = 'home' | 'login' | 'signup' | 'findId' | 'findPw' | 'dashboard' | 'orders' | 'settings' | 'mypage';

interface Props {
  session: Session | null;
  route: Route;
  serviceStatus: ServiceStatus | 'LOADING';
  onNavigate: (route: Route) => void;
  onLogout: () => void;
}

const NAV: { key: Route; label: string }[] = [
  { key: 'dashboard', label: '주문접수상황판' },
  { key: 'orders', label: '주문접수조회' },
  { key: 'settings', label: '환경설정' },
];

export function TopHeader({ session, route, serviceStatus, onNavigate, onLogout }: Props) {
  return (
    <header className="h-14 bg-brand-card border-b border-brand-border flex items-center justify-between px-6 shrink-0">
      <button onClick={() => onNavigate(session ? 'dashboard' : 'home')} className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-brand-primary flex items-center justify-center">
          <span className="font-display font-bold text-white text-sm">G</span>
        </div>
        <span className="font-display font-bold text-sm text-brand-text-primary">ggotAIya</span>
      </button>

      {session && (
        <nav className="flex items-center gap-1">
          {NAV.map((n) => (
            <button
              key={n.key}
              onClick={() => onNavigate(n.key)}
              className={`px-4 py-2 text-sm font-semibold rounded-lg transition ${
                route === n.key
                  ? 'bg-brand-primary text-white'
                  : 'text-brand-text-secondary hover:text-brand-text-primary hover:bg-brand-card-hover'
              }`}
            >
              {n.label}
            </button>
          ))}
        </nav>
      )}

      <div className="flex items-center gap-3">
        <span className="text-[11px] flex items-center gap-1 font-semibold">
          {serviceStatus === 'RUNNING' ? (
            <span className="text-brand-success flex items-center gap-1"><CircleDot className="h-3 w-3 animate-pulse" /> RUNNING</span>
          ) : (
            <span className="text-brand-error flex items-center gap-1"><CircleDot className="h-3 w-3" /> STOPPED</span>
          )}
        </span>
        {session ? (
          <>
            <span className="text-xs font-semibold text-brand-text-primary">{session.shopName}</span>
            <button onClick={() => onNavigate('mypage')} className="text-xs text-brand-text-secondary hover:text-brand-text-primary">마이페이지</button>
            <button onClick={onLogout} className="text-xs text-brand-text-secondary hover:text-brand-text-primary">로그아웃</button>
          </>
        ) : (
          <>
            <button onClick={() => onNavigate('login')} className="text-xs font-semibold text-brand-text-primary hover:opacity-80">로그인</button>
            <button onClick={() => onNavigate('signup')} className="text-xs text-brand-text-secondary hover:text-brand-text-primary">회원가입</button>
          </>
        )}
      </div>
    </header>
  );
}
