import React, { useState, useEffect } from 'react';
import { DashboardView } from './views/dashboard';
import { OrderListView } from './views/order_list';
import { SettingsView } from './views/settings';
import { supabase } from './supabase';
import { 
  LayoutDashboard, ClipboardList, Settings, Store, 
  CircleDot, HelpCircle, LogOut 
} from 'lucide-react';

function App() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'orders' | 'settings'>('dashboard');
  const [shopName, setShopName] = useState('ggotAI 꽃가게');
  
  // 윈도우 서비스 상태 ('RUNNING' | 'STOPPED' | 'NOT_INSTALLED' | 'LOADING')
  const [serviceStatus, setServiceStatus] = useState<'RUNNING' | 'STOPPED' | 'NOT_INSTALLED' | 'LOADING'>('LOADING');

  const defaultShopKey = 1;

  // 윈도우 서비스 상태 조회 (사이드바 상태 뱃지용)
  const checkServiceStatus = async () => {
    if (!window.electronAPI) {
      setServiceStatus('STOPPED');
      return;
    }
    try {
      const res = await window.electronAPI.getServiceStatus();
      setServiceStatus(res.status);
    } catch (err) {
      setServiceStatus('STOPPED');
    }
  };

  useEffect(() => {
    // 꽃집 정보 로드
    async function loadShopInfo() {
      try {
        const { data, error } = await supabase
          .from('member_info')
          .select('shop_name')
          .eq('id', defaultShopKey)
          .single();

        if (data && !error) {
          setShopName(data.shop_name);
        }
      } catch (err) {
        console.error('샵 정보 조회 실패:', err);
      }
    }

    loadShopInfo();
    checkServiceStatus();
    const interval = setInterval(checkServiceStatus, 3000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex h-screen bg-brand-bg text-brand-text-primary overflow-hidden font-sans">
      
      {/* 1. 사이드바 내비게이션 영역 */}
      <aside className="w-64 bg-brand-card border-r border-brand-border flex flex-col justify-between shrink-0">
        
        {/* 상단: 브랜드 로고 및 샵 상태 */}
        <div className="p-6 space-y-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-brand-primary flex items-center justify-center shadow-lg shadow-brand-primary/20">
              <span className="font-display font-bold text-white text-base">G</span>
            </div>
            <div>
              <div className="font-display font-bold text-base tracking-tight leading-none text-brand-text-primary">ggotAIya</div>
              <div className="text-[9px] text-brand-text-muted mt-1 uppercase font-semibold tracking-wider">주문 관제 상황판</div>
            </div>
          </div>

          {/* 꽃집 계정 프로필 위젯 */}
          <div className="bg-brand-bg/40 p-4 border border-brand-border/60 rounded-xl flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-brand-primary/10 border border-brand-primary/20 flex items-center justify-center shrink-0">
              <Store className="h-4 w-4 text-brand-primary" />
            </div>
            <div className="min-w-0">
              <div className="text-xs font-semibold text-brand-text-primary truncate">{shopName}</div>
              <div className="text-[10px] text-brand-text-muted mt-0.5">사장님 계정</div>
            </div>
          </div>

          {/* 내비게이션 리스트 */}
          <nav className="space-y-1.5">
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`w-full flex items-center gap-3 px-4 py-3 text-sm font-semibold rounded-lg transition-all ${
                activeTab === 'dashboard'
                  ? 'bg-brand-primary text-white shadow-lg shadow-brand-primary/10'
                  : 'text-brand-text-secondary hover:text-brand-text-primary hover:bg-brand-card-hover'
              }`}
            >
              <LayoutDashboard className="h-4.5 w-4.5" />
              <span>실시간 상황판</span>
            </button>

            <button
              onClick={() => setActiveTab('orders')}
              className={`w-full flex items-center gap-3 px-4 py-3 text-sm font-semibold rounded-lg transition-all ${
                activeTab === 'orders'
                  ? 'bg-brand-primary text-white shadow-lg shadow-brand-primary/10'
                  : 'text-brand-text-secondary hover:text-brand-text-primary hover:bg-brand-card-hover'
              }`}
            >
              <ClipboardList className="h-4.5 w-4.5" />
              <span>주문 내역 관리</span>
            </button>

            <button
              onClick={() => setActiveTab('settings')}
              className={`w-full flex items-center gap-3 px-4 py-3 text-sm font-semibold rounded-lg transition-all ${
                activeTab === 'settings'
                  ? 'bg-brand-primary text-white shadow-lg shadow-brand-primary/10'
                  : 'text-brand-text-secondary hover:text-brand-text-primary hover:bg-brand-card-hover'
              }`}
            >
              <Settings className="h-4.5 w-4.5" />
              <span>수집 환경설정</span>
            </button>
          </nav>
        </div>

        {/* 하단: 엔진 상태 현황 및 푸터 정보 */}
        <div className="p-6 border-t border-brand-border space-y-4 bg-brand-bg/10">
          <div className="flex items-center justify-between text-xs">
            <span className="text-brand-text-muted">로컬 서비스 상태</span>
            {serviceStatus === 'RUNNING' ? (
              <span className="text-brand-success font-semibold flex items-center gap-1">
                <CircleDot className="h-3 w-3 animate-pulse" /> RUNNING
              </span>
            ) : (
              <span className="text-brand-error font-semibold flex items-center gap-1">
                <CircleDot className="h-3 w-3" /> STOPPED
              </span>
            )}
          </div>
          
          <div className="text-[10px] text-brand-text-muted text-center pt-2 border-t border-brand-border/40">
            © 2026 ggotAI Corp. All rights reserved.
          </div>
        </div>

      </aside>

      {/* 2. 메인 컨텐트 뷰포트 */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        {/* 상단 윈도우 탑 바 (디자인 보조 및 백엔드 연동) */}
        <header className="h-14 bg-brand-card border-b border-brand-border flex items-center justify-between px-6 shrink-0">
          <div className="text-xs font-semibold text-brand-text-secondary">
            ggotAIya <span className="text-brand-text-muted">v1.0.0</span>
          </div>
          
          {/* 간이 헬프/서포트 아이콘 */}
          <div className="flex items-center gap-4">
            <div className="text-[10px] text-brand-text-muted bg-brand-bg px-2.5 py-1 rounded border border-brand-border font-mono">
              Admin Privileges Activated
            </div>
            <button className="text-brand-text-secondary hover:text-brand-text-primary transition" title="도움말">
              <HelpCircle className="h-4.5 w-4.5" />
            </button>
          </div>
        </header>

        {/* 탭 뷰 분기 로드 */}
        {activeTab === 'dashboard' && <DashboardView />}
        {activeTab === 'orders' && <OrderListView />}
        {activeTab === 'settings' && <SettingsView />}
      </main>

    </div>
  );
}

export default App;
