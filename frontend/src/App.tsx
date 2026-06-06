import { useState, useEffect } from 'react';
import { SessionProvider, useSession } from './session/SessionContext';
import { TopHeader } from './shell/TopHeader';
import { HomeView } from './views/home';
import { LoginView } from './views/login';
import { SignupView, FindIdView, FindPwView, MyPageView } from './views/_placeholders';
import { DashboardView } from './views/dashboard';
import { OrderListView } from './views/order_list';
import { SettingsView } from './views/settings';
import type { ServiceStatus } from './types/electron';

type Route = 'home' | 'login' | 'signup' | 'findId' | 'findPw' | 'dashboard' | 'orders' | 'settings' | 'mypage';

function Shell() {
  const { session, logout } = useSession();
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

  const handleLogout = () => { logout(); };

  return (
    <div className="flex flex-col h-screen bg-brand-bg text-brand-text-primary overflow-hidden font-sans">
      <TopHeader
        session={session}
        route={route}
        serviceStatus={serviceStatus}
        onNavigate={setRoute}
        onLogout={handleLogout}
      />
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {!session && route === 'home' && <HomeView onLogin={() => setRoute('login')} onSignup={() => setRoute('signup')} />}
        {!session && route === 'login' && <LoginView onFindId={() => setRoute('findId')} onFindPw={() => setRoute('findPw')} />}
        {!session && route === 'signup' && <SignupView />}
        {!session && route === 'findId' && <FindIdView />}
        {!session && route === 'findPw' && <FindPwView />}

        {session && route === 'dashboard' && <DashboardView />}
        {session && route === 'orders' && <OrderListView />}
        {session && route === 'settings' && <SettingsView />}
        {session && route === 'mypage' && <MyPageView />}
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
