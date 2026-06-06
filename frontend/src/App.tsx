import { useState, useEffect } from 'react';
import { SessionProvider, useSession } from './session/SessionContext';
import { TopHeader } from './shell/TopHeader';
import { HomeView } from './views/home';
import { LoginView } from './views/login';
import { FindIdView, FindPwView, MyPageView } from './views/_placeholders';
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

  // 로그인/로그아웃 시 기본 라우트 보정
  useEffect(() => {
    setRoute(session ? 'dashboard' : 'home');
  }, [session]);

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
        {authReady && !session && route === 'findId' && <FindIdView />}
        {authReady && !session && route === 'findPw' && <FindPwView />}

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
