import { useState, useEffect } from 'react';
import { supabase } from '../supabase';
import { useSession } from '../session/SessionContext';
import { getDashboard, type DashboardData, type DashRpc } from '../dashboard/client';
import { CHANNELS, deriveCurrentTask, latestForChannel } from '../dashboard/currentTask';
import {
  Play, Square, RefreshCw, Phone, Smartphone, Globe, Radio, MessageSquare, ShieldAlert, Clock,
} from 'lucide-react';

const rpc: DashRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<DashRpc>;

type ServiceStatus = 'RUNNING' | 'STOPPED' | 'NOT_INSTALLED' | 'LOADING';

function channelIcon(label: string) {
  if (label.startsWith('핸드폰')) return <Smartphone className="h-5 w-5 text-brand-primary" />;
  if (label === '가게전화') return <Phone className="h-5 w-5 text-brand-success" />;
  if (label === '쇼핑몰') return <Globe className="h-5 w-5 text-purple-400" />;
  if (label === '인터라넷') return <Radio className="h-5 w-5 text-pink-400" />;
  return <MessageSquare className="h-5 w-5 text-teal-400" />; // 가게음성
}

export function DashboardView() {
  const { session, readToken } = useSession();
  const shopKey = session?.shopKey ?? 0;

  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>('LOADING');
  const [statusError, setStatusError] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const [data, setData] = useState<DashboardData | null>(null);
  const [dataError, setDataError] = useState('');
  const [loading, setLoading] = useState(true);

  // 수집엔진 상태는 백엔드 하트비트(get_dashboard.engine_alive)로 판정한다.
  // Electron 데스크톱뿐 아니라 웹(브라우저)에서도 동일하게 동작한다.
  const fetchData = async () => {
    if (!shopKey || !readToken) { setDataError('세션이 만료되었습니다. 다시 로그인해주세요.'); setLoading(false); return; }
    const r = await getDashboard(rpc, shopKey, readToken);
    if (!r.ok || !r.data) { setDataError(r.reason === 'unauthorized' ? '세션이 만료되었습니다. 다시 로그인해주세요.' : '상황판 데이터를 불러오지 못했습니다.'); setLoading(false); return; }
    setDataError(''); setData(r.data); setServiceStatus(r.data.engineAlive ? 'RUNNING' : 'STOPPED'); setLoading(false);
  };

  useEffect(() => {
    fetchData();
    const poll = setInterval(fetchData, 2500);
    return () => { clearInterval(poll); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shopKey, readToken]);

  const handleStart = async () => {
    if (!window.electronAPI) return;
    setActionLoading(true); setStatusError('');
    try {
      const res = await window.electronAPI.startService();
      if (!res.success) setStatusError(res.error || '서비스를 시작하지 못했습니다.');
      await fetchData();
    } catch (e) { setStatusError(e instanceof Error ? e.message : String(e)); }
    finally { setActionLoading(false); }
  };
  const handleStop = async () => {
    if (!window.electronAPI) return;
    setActionLoading(true); setStatusError('');
    try {
      const res = await window.electronAPI.stopService();
      if (!res.success) setStatusError(res.error || '서비스를 중지하지 못했습니다.');
      await fetchData();
    } catch (e) { setStatusError(e instanceof Error ? e.message : String(e)); }
    finally { setActionLoading(false); }
  };

  const stats = data?.stats ?? { today_total: 0, rpa_success: 0, rpa_fail: 0, rpa_ready: 0 };
  const running = serviceStatus === 'RUNNING';
  // 수집엔진 시작/중지 제어는 PC(데스크톱 앱)에서만 가능. 웹은 상태 조회 전용.
  const isDesktop = typeof window !== 'undefined' && !!window.electronAPI;

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8">
      {/* 헤더 + 마스터 제어 */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-8 bg-brand-card p-6 border border-brand-border rounded-2xl shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-display font-bold text-brand-text-primary tracking-tight">ggotAIya 실시간 상황판</h1>
            <div className="flex items-center gap-1.5 px-3 py-1 bg-brand-bg/60 rounded-full border border-brand-border text-xs font-semibold">
              <span>수집엔진:</span>
              {running ? <span className="text-brand-success flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-brand-success animate-ping" /> 가동중</span>
                : serviceStatus === 'NOT_INSTALLED' ? <span className="text-brand-text-muted">⚠️ 미설치</span>
                : serviceStatus === 'LOADING' ? <span className="text-brand-text-muted animate-pulse">조회중...</span>
                : <span className="text-brand-error flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-brand-error" /> 중지됨</span>}
            </div>
          </div>
          <p className="text-brand-text-secondary text-sm">6대 채널 비정형 주문을 실시간 감지하여 자동 전산 입력을 구동합니다.</p>
        </div>
        <div className="flex items-center gap-3 justify-end">
          {statusError && <div className="flex items-center gap-1 text-xs text-brand-error font-medium max-w-xs truncate" title={statusError}><ShieldAlert className="h-4 w-4 shrink-0" /><span>권한 부족/오류</span></div>}
          {isDesktop ? (
            running ? (
              <button onClick={handleStop} disabled={actionLoading} className="flex items-center gap-2 px-5 py-3 bg-brand-error hover:bg-brand-error/90 disabled:bg-brand-text-muted text-white text-sm font-bold rounded-xl shadow-lg transition">
                <Square className="h-4 w-4 fill-current" /><span>주문 자동 수집 중지</span>
              </button>
            ) : (
              <button onClick={handleStart} disabled={actionLoading || serviceStatus === 'NOT_INSTALLED'} className="flex items-center gap-2 px-5 py-3 bg-brand-success hover:bg-brand-success/90 disabled:bg-brand-text-muted text-brand-bg text-sm font-bold rounded-xl shadow-lg transition">
                <Play className="h-4 w-4 fill-current" /><span>주문 자동 수집 시작</span>
              </button>
            )
          ) : (
            <div className="text-xs text-brand-text-secondary">수집엔진 시작/중지는 매장 PC에서 제어됩니다.</div>
          )}
        </div>
      </div>

      {dataError && <div className="mb-6 text-sm text-brand-error bg-brand-error/10 border border-brand-error/20 rounded-xl px-4 py-3">{dataError}</div>}

      {/* 통계 카드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
        <div className="glass-panel p-5 rounded-xl border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">오늘 총 수집</div>
          <div className="flex items-baseline justify-between">
            <div className="text-3xl font-display font-bold text-brand-text-primary">{stats.today_total} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
            <div className="text-xs text-brand-primary font-medium flex items-center gap-1"><Clock className="h-3.5 w-3.5" /> 2.5초 동기화</div>
          </div>
        </div>
        <div className="glass-panel p-5 rounded-xl border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">전산 입력 성공</div>
          <div className="text-3xl font-display font-bold text-brand-success">{stats.rpa_success} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
        </div>
        <div className="glass-panel p-5 rounded-xl border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">전산 입력 실패(수동확인)</div>
          <div className="text-3xl font-display font-bold text-brand-error">{stats.rpa_fail} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
        </div>
        <div className="glass-panel p-5 rounded-xl border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">RPA 순차 입력 대기</div>
          <div className="text-3xl font-display font-bold text-brand-warning">{stats.rpa_ready} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
        </div>
      </div>

      {/* 6채널 그리드 + 피드 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-4">
          <h3 className="text-base font-bold text-brand-text-primary">6대 채널 작동 상태</h3>
          <div className="grid grid-cols-2 gap-3">
            {CHANNELS.map((ch) => {
              const configured = data?.config[ch.configKey] ?? false;
              const active = configured && running;
              const agg = data?.channels.find((c) => c.channel_order === ch.channelOrder);
              const task = deriveCurrentTask(data ? latestForChannel(data.feed, ch.channelOrder) : undefined);
              return (
                <div key={ch.label} className="glass-panel p-4 rounded-xl border border-brand-border space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">{channelIcon(ch.label)}<span className="text-sm font-semibold text-brand-text-primary">{ch.label}</span></div>
                    <span className={`w-2.5 h-2.5 rounded-full ${active ? 'bg-brand-success animate-pulse' : 'bg-brand-error'}`} title={active ? '작동' : (configured ? '중지' : '미설정')} />
                  </div>
                  <div className="text-[11px] text-brand-text-secondary">현재작업: <span className="font-semibold text-brand-text-primary">{configured ? task : '미사용'}</span></div>
                  <div className="text-[11px] text-brand-text-muted">오늘작업: <span className="font-semibold text-brand-success">{agg?.success ?? 0}</span>건</div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-brand-text-primary">실시간 주문 수집 피드</h3>
            <button onClick={fetchData} className="p-1 hover:bg-brand-card rounded text-brand-text-secondary hover:text-brand-text-primary transition" title="새로고침"><RefreshCw className="h-4 w-4" /></button>
          </div>
          <div className="glass-panel rounded-xl p-5 border border-brand-border space-y-3 max-h-[360px] overflow-y-auto">
            {loading ? (
              <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-brand-primary" /></div>
            ) : !data || data.feed.length === 0 ? (
              <div className="text-center py-20 text-brand-text-muted text-sm">수집된 실시간 주문 이력이 없습니다.</div>
            ) : (
              data.feed.map((item) => (
                <div key={item.id} className="flex gap-4 p-3 bg-brand-bg/40 border border-brand-border/40 rounded-lg">
                  <div className="shrink-0 w-8 h-8 rounded-full bg-brand-card border border-brand-border flex items-center justify-center">{channelIcon(item.channel_order.startsWith('핸드폰') ? '핸드폰1' : item.channel_order)}</div>
                  <div className="flex-1 space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-brand-text-primary">{item.customer_name ?? '고객'} 님 ({item.channel_order})</span>
                      <span className="text-[10px] text-brand-text-muted">{new Date(item.created_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                    </div>
                    <p className="text-xs text-brand-text-secondary bg-brand-bg/50 p-2.5 rounded border border-brand-border/40 font-mono">{item.stt_text || '비정형 음성 원문 추출 대기중...'}</p>
                    <div className="flex justify-end"><span className="inline-flex items-center text-[9px] font-bold text-brand-text-primary bg-brand-card px-2 py-0.5 rounded border border-brand-border">{deriveCurrentTask(item)}</span></div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
