import { useState, useEffect } from 'react';
import { SessionProvider, useSession } from './session/SessionContext';
import { TopHeader } from './shell/TopHeader';
import { HomeView } from './views/home';
import { LoginView } from './views/login';
import { MyPageView } from './views/mypage';
import { FindIdView } from './views/find_id';
import { FindPwView } from './views/find_pw';
import { SignupView } from './views/signup';
import { DashboardView } from './views/dashboard';
import { OrderListView } from './views/order_list';
import { SettingsView } from './views/settings';
import type { ServiceStatus } from './types/electron';
import type { Route } from './shell/routes';

function Shell() {
  const { session, authReady, logout } = useSession();
  const [route, setRoute] = useState<Route>('home');
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | 'LOADING'>('LOADING');

  // 서비스 상태 폴링(헤더 뱃지)
  useEffect(() => {
    let active = true;
    const check = async () => {
      if (!window.electronAPI) { if (active) setServiceStatus('STOPPED'); return; }
      try {
        const res = await window.electronAPI.getServiceStatus();
        if (active) setServiceStatus(res.status);
      } catch { if (active) setServiceStatus('STOPPED'); }
    };
    check();
    const t = setInterval(check, 3000);
    return () => { active = false; clearInterval(t); };
  }, []);

  // 로그인/로그아웃 "전환" 시에만 기본 라우트 보정.
  // (session 객체 자체가 갱신돼도 — 예: 마이페이지 shop_name 변경 — 라우트를 튕기지 않도록 로그인 여부 불리언에 의존)
  const isLoggedIn = !!session;
  useEffect(() => {
    setRoute(isLoggedIn ? 'dashboard' : 'home');
  }, [isLoggedIn]);

  return (
    <div className="flex flex-col h-screen bg-brand-bg text-brand-text-primary overflow-hidden font-sans">
      <TopHeader
        session={session}
        route={route}
        serviceStatus={serviceStatus}
        onNavigate={setRoute}
        onLogout={logout}
      />
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {!authReady && (
          <div className="flex-1 flex items-center justify-center text-brand-text-muted text-sm">불러오는 중…</div>
        )}
        {authReady && !session && route === 'home' && <HomeView onLogin={() => setRoute('login')} onSignup={() => setRoute('signup')} />}
        {authReady && !session && route === 'login' && <LoginView onFindId={() => setRoute('findId')} onFindPw={() => setRoute('findPw')} />}
        {authReady && !session && route === 'signup' && <SignupView onDone={() => setRoute('login')} />}
        {authReady && !session && route === 'findId' && <FindIdView onDone={() => setRoute('login')} />}
        {authReady && !session && route === 'findPw' && <FindPwView onDone={() => setRoute('login')} />}

        {authReady && session && route === 'dashboard' && <DashboardView />}
        {authReady && session && route === 'orders' && <OrderListView />}
        {authReady && session && route === 'settings' && <SettingsView />}
        {authReady && session && route === 'mypage' && <MyPageView />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <Shell />
    </SessionProvider>
  );
}
