import React, { useState, useEffect } from 'react';
import { supabase } from '../supabase';
import { 
  Play, Square, AlertCircle, RefreshCw, Phone, Smartphone, 
  Globe, Radio, MessageSquare, ShieldAlert, Sparkles, CheckCircle2, Clock
} from 'lucide-react';

interface Stats {
  todayTotal: number;
  rpaSuccess: number;
  rpaFail: number;
  rpaReady: number;
}

interface CallHistory {
  id: number;
  channel_order: string;
  channel_classification: string;
  customer_name: string;
  stt_text: string | null;
  is_order: string;
  created_at: string;
}

export function DashboardView() {
  // 윈도우 서비스 상태 ('RUNNING' | 'STOPPED' | 'NOT_INSTALLED' | 'LOADING')
  const [serviceStatus, setServiceStatus] = useState<'RUNNING' | 'STOPPED' | 'NOT_INSTALLED' | 'LOADING'>('LOADING');
  const [statusError, setStatusError] = useState('');
  
  // 통계 및 최근 내역
  const [stats, setStats] = useState<Stats>({ todayTotal: 0, rpaSuccess: 0, rpaFail: 0, rpaReady: 0 });
  const [feed, setFeed] = useState<CallHistory[]>([]);
  const [loadingFeed, setLoadingFeed] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  const defaultShopKey = 1;

  // 1. 윈도우 서비스 상태 조회 (Electron SCM 연동)
  const checkServiceStatus = async () => {
    if (!window.electronAPI) {
      setServiceStatus('STOPPED'); // Electron 환경 외부 테스트용 대체 동작
      return;
    }
    try {
      const res = await window.electronAPI.getServiceStatus();
      if (res.error) setStatusError(res.error);
      setServiceStatus(res.status);
    } catch (err: any) {
      console.error(err);
      setServiceStatus('STOPPED');
    }
  };

  // 2. 통계 데이터 집계 (Supabase 연동)
  const fetchStats = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];

      // 오늘 들어온 주문 이력 전체 카운트
      const { count: total, error: err1 } = await supabase
        .from('server_call_history')
        .select('*', { count: 'exact', head: true })
        .eq('shop_key', defaultShopKey)
        .gte('created_at', `${today}T00:00:00Z`);

      if (err1) throw err1;

      // RPA 상태별 카운트
      const { data: rpaData, error: err2 } = await supabase
        .from('order_details')
        .select('rpa_status')
        .eq('shop_key', defaultShopKey)
        .gte('created_at', `${today}T00:00:00Z`);

      if (err2) throw err2;

      let success = 0;
      let fail = 0;
      let ready = 0;

      rpaData?.forEach((item) => {
        if (item.rpa_status === 'success') success++;
        else if (item.rpa_status === 'fail') fail++;
        else if (item.rpa_status === 'ready') ready++;
      });

      setStats({
        todayTotal: total || 0,
        rpaSuccess: success,
        rpaFail: fail,
        rpaReady: ready
      });
    } catch (err) {
      console.error('통계 로드 오류:', err);
    }
  };

  // 3. 최근 주문 수집 내역 피드 가져오기
  const fetchFeed = async () => {
    try {
      setLoadingFeed(true);
      const { data, error } = await supabase
        .from('server_call_history')
        .select('id, channel_order, channel_classification, customer_name, stt_text, is_order, created_at')
        .eq('shop_key', defaultShopKey)
        .order('created_at', { ascending: false })
        .limit(6);

      if (error) throw error;
      setFeed(data || []);
    } catch (err) {
      console.error('피드 로드 오류:', err);
    } finally {
      setLoadingFeed(false);
    }
  };

  // 4. 서비스 제어 버튼 핸들러
  const handleStartService = async () => {
    if (!window.electronAPI) return;
    setActionLoading(true);
    setStatusError('');
    try {
      const res = await window.electronAPI.startService();
      if (!res.success) {
        setStatusError(res.error || '서비스를 시작하지 못했습니다.');
      }
      await checkServiceStatus();
    } catch (err: any) {
      setStatusError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleStopService = async () => {
    if (!window.electronAPI) return;
    setActionLoading(true);
    setStatusError('');
    try {
      const res = await window.electronAPI.stopService();
      if (!res.success) {
        setStatusError(res.error || '서비스를 중지하지 못했습니다.');
      }
      await checkServiceStatus();
    } catch (err: any) {
      setStatusError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // 초기 실행 및 실시간 Realtime 구독 설정
  useEffect(() => {
    checkServiceStatus();
    fetchStats();
    fetchFeed();

    // 2초 간격 윈도우 서비스 SCM 상태 폴링
    const statusInterval = setInterval(checkServiceStatus, 2000);

    // Supabase Realtime을 통한 실시간 신규 음성/문자 유입 감시
    // PRD F2 실시간 감시 대응: server_call_history에 신규 INSERT 발생 시 대시보드 피드 및 통계 즉시 갱신
    const channel = supabase
      .channel('schema-db-changes')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'server_call_history',
        },
        (payload) => {
          console.log('실시간 신규 주문 감지:', payload.new);
          // 피드 최상단에 반짝이며 슬라이드 추가
          setFeed((prev) => [payload.new as CallHistory, ...prev.slice(0, 5)]);
          // 통계 재계산
          fetchStats();
        }
      )
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'order_details',
        },
        () => {
          // order_details 상태 변경 시 통계 즉시 갱신
          fetchStats();
        }
      )
      .subscribe();

    return () => {
      clearInterval(statusInterval);
      supabase.removeChannel(channel);
    };
  }, []);

  // 채널별 아이콘 분기 드로잉
  const renderChannelIcon = (channel: string) => {
    switch (channel) {
      case '핸드폰':
        return <Smartphone className="h-5 w-5 text-brand-primary" />;
      case '가게전화':
        return <Phone className="h-5 w-5 text-brand-success" />;
      case '쇼핑몰':
        return <Globe className="h-5 w-5 text-purple-400" />;
      case '인터라넷':
        return <Radio className="h-5 w-5 text-pink-400" />;
      case '가게음성':
        return <MessageSquare className="h-5 w-5 text-teal-400" />;
      default:
        return <Sparkles className="h-5 w-5 text-brand-warning" />;
    }
  };

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8 animate-fade-in-up">
      {/* 1. 상단 상황 헤더 및 수집 시작/중지 제어부 */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-8 bg-brand-card p-6 border border-brand-border rounded-2xl shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-display font-bold text-brand-text-primary tracking-tight">ggotAIya 실시간 상황판</h1>
            <div className="flex items-center gap-1.5 px-3 py-1 bg-brand-bg/60 rounded-full border border-brand-border text-xs font-semibold">
              <span>수집엔진:</span>
              {serviceStatus === 'RUNNING' ? (
                <span className="text-brand-success flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-brand-success animate-ping"></span>
                  🟢 수집 가동중
                </span>
              ) : serviceStatus === 'STOPPED' ? (
                <span className="text-brand-error flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-brand-error"></span>
                  🔴 수집 중지됨
                </span>
              ) : serviceStatus === 'NOT_INSTALLED' ? (
                <span className="text-brand-text-muted flex items-center gap-1">
                  ⚠️ 미설치
                </span>
              ) : (
                <span className="text-brand-text-muted animate-pulse">조회중...</span>
              )}
            </div>
          </div>
          <p className="text-brand-text-secondary text-sm">
            다중 채널(가게전화, 핸드폰, 로컬음성 등) 비정형 주문을 실시간 감지하여 자동 전산 RPA를 구동합니다.
          </p>
        </div>

        {/* 제어 패널 버튼 */}
        <div className="flex items-center gap-3 self-stretch lg:self-auto justify-end">
          {statusError && (
            <div className="flex items-center gap-1 text-xs text-brand-error font-medium max-w-xs truncate" title={statusError}>
              <ShieldAlert className="h-4 w-4 shrink-0" />
              <span>권한 부족/오류</span>
            </div>
          )}
          
          {serviceStatus === 'STOPPED' || serviceStatus === 'NOT_INSTALLED' ? (
            <button
              onClick={handleStartService}
              disabled={actionLoading || serviceStatus === 'NOT_INSTALLED'}
              className="flex items-center gap-2 px-5 py-3 bg-brand-success hover:bg-brand-success/90 disabled:bg-brand-text-muted text-brand-bg text-sm font-bold rounded-xl shadow-lg shadow-brand-success/15 hover:shadow-brand-success/25 transition cursor-pointer"
            >
              <Play className="h-4 w-4 fill-current" />
              <span>주문 자동 수집 시작</span>
            </button>
          ) : (
            <button
              onClick={handleStopService}
              disabled={actionLoading}
              className="flex items-center gap-2 px-5 py-3 bg-brand-error hover:bg-brand-error/90 disabled:bg-brand-text-muted text-white text-sm font-bold rounded-xl shadow-lg shadow-brand-error/15 hover:shadow-brand-error/25 transition cursor-pointer"
            >
              <Square className="h-4 w-4 fill-current" />
              <span>주문 자동 수집 중지</span>
            </button>
          )}
        </div>
      </div>

      {/* 2. 오늘 수집 및 RPA 통계 카드 현황판 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
        
        {/* 오늘 총 수집 */}
        <div className="glass-panel p-5 rounded-xl shadow-md border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">오늘 총 수집 이력</div>
          <div className="flex items-baseline justify-between">
            <div className="text-3xl font-display font-bold text-brand-text-primary">{stats.todayTotal} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
            <div className="text-xs text-brand-primary font-medium flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" /> 실시간 동기화
            </div>
          </div>
        </div>

        {/* RPA 성공 */}
        <div className="glass-panel p-5 rounded-xl shadow-md border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">전산 자동 입력 성공</div>
          <div className="flex items-baseline justify-between">
            <div className="text-3xl font-display font-bold text-brand-success">{stats.rpaSuccess} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
            <div className="text-xs text-brand-success font-semibold px-2 py-0.5 rounded-full bg-brand-success/10 border border-brand-success/20">
              성공률 {stats.todayTotal > 0 ? Math.round(((stats.rpaSuccess) / (stats.rpaSuccess + stats.rpaFail || 1)) * 100) : 0}%
            </div>
          </div>
        </div>

        {/* RPA 실패 */}
        <div className="glass-panel p-5 rounded-xl shadow-md border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">전산 자동 입력 실패 (수동확인)</div>
          <div className="flex items-baseline justify-between">
            <div className="text-3xl font-display font-bold text-brand-error">{stats.rpaFail} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
            {stats.rpaFail > 0 && (
              <div className="text-[10px] text-brand-error font-medium animate-pulse">
                ※ 리스트에서 수동 조치 요망
              </div>
            )}
          </div>
        </div>

        {/* RPA 대기 */}
        <div className="glass-panel p-5 rounded-xl shadow-md border border-brand-border space-y-2">
          <div className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider">RPA 락 순차 입력 대기</div>
          <div className="flex items-baseline justify-between">
            <div className="text-3xl font-display font-bold text-brand-warning">{stats.rpaReady} <span className="text-sm font-normal text-brand-text-secondary">건</span></div>
            {stats.rpaReady > 0 && (
              <span className="text-[10px] text-brand-warning bg-brand-warning/10 px-2 py-0.5 rounded-full border border-brand-warning/20 animate-pulse">
                RPA 싱글턴 큐 작동중
              </span>
            )}
          </div>
        </div>

      </div>

      {/* 3. 채널별 작동 현황 정보판 & 실시간 타임라인 피드 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* 왼쪽: 수집 채널별 구동 위젯 */}
        <div className="lg:col-span-1 space-y-5">
          <h3 className="text-base font-bold text-brand-text-primary flex items-center gap-2">
            <span>수집 채널 작동 상태</span>
            <span className="text-[10px] text-brand-text-muted">(설정 주기 기준)</span>
          </h3>

          <div className="space-y-4">
            {/* 핸드폰 수집 채널 */}
            <div className="glass-panel p-4 rounded-xl flex items-center justify-between border border-brand-border">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-brand-primary/10 rounded-lg">
                  <Smartphone className="h-5 w-5 text-brand-primary" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-brand-text-primary">스마트폰 음성 수집</h4>
                  <p className="text-[10px] text-brand-text-muted">Supabase Realtime 구독 감시</p>
                </div>
              </div>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-brand-success/10 text-brand-success border border-brand-success/20">
                🟢 감시 중
              </span>
            </div>

            {/* 가게 일반 전화 */}
            <div className="glass-panel p-4 rounded-xl flex items-center justify-between border border-brand-border">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-brand-success/10 rounded-lg">
                  <Phone className="h-5 w-5 text-brand-success" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-brand-text-primary">가게 일반전화 Webhook</h4>
                  <p className="text-[10px] text-brand-text-muted">FastAPI VoIP 수신 API 가동</p>
                </div>
              </div>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-brand-success/10 text-brand-success border border-brand-success/20">
                🟢 리스닝 중
              </span>
            </div>

            {/* 쇼핑몰 연동 */}
            <div className="glass-panel p-4 rounded-xl flex items-center justify-between border border-brand-border">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-purple-500/10 rounded-lg">
                  <Globe className="h-5 w-5 text-purple-400" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-brand-text-primary">꽃가게 공식 쇼핑몰</h4>
                  <p className="text-[10px] text-brand-text-muted">Playwright 정기 백그라운드 크롤링</p>
                </div>
              </div>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-brand-primary/10 text-brand-primary border border-brand-primary/20">
                🔵 크롤러 대기
              </span>
            </div>

            {/* 인터라넷 연합 */}
            <div className="glass-panel p-4 rounded-xl flex items-center justify-between border border-brand-border">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-pink-500/10 rounded-lg">
                  <Radio className="h-5 w-5 text-pink-400" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-brand-text-primary">화원 연합 인트라넷</h4>
                  <p className="text-[10px] text-brand-text-muted">타지역 전산 주문 주기적 감시</p>
                </div>
              </div>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-brand-primary/10 text-brand-primary border border-brand-primary/20">
                🔵 크롤러 대기
              </span>
            </div>

          </div>
        </div>

        {/* 오른쪽: 실시간 타임라인 피드 */}
        <div className="lg:col-span-2 space-y-5">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-brand-text-primary">실시간 주문 수집 피드 (음성 및 텍스트)</h3>
            <button
              onClick={fetchFeed}
              className="p-1 hover:bg-brand-card rounded text-brand-text-secondary hover:text-brand-text-primary transition"
              title="새로고침"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>

          <div className="glass-panel rounded-xl p-5 border border-brand-border shadow-xl space-y-4 max-h-[360px] overflow-y-auto">
            {loadingFeed ? (
              <div className="flex justify-center items-center py-20">
                <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-brand-primary"></div>
              </div>
            ) : feed.length === 0 ? (
              <div className="text-center py-20 text-brand-text-muted text-sm">
                수집된 실시간 주문 이력이 존재하지 않습니다.
              </div>
            ) : (
              <div className="space-y-4 relative before:absolute before:left-6.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-brand-border/60">
                {feed.map((item) => (
                  <div 
                    key={item.id} 
                    className="flex gap-4 p-3 bg-brand-bg/40 border border-brand-border/40 rounded-lg hover:bg-brand-card-hover/40 transition animate-fade-in-up"
                  >
                    {/* 타임라인 채널 서클 */}
                    <div className="relative z-10 shrink-0 w-8 h-8 rounded-full bg-brand-card border border-brand-border flex items-center justify-center shadow-md">
                      {renderChannelIcon(item.channel_order)}
                    </div>
                    
                    {/* 주문 내역 정보 */}
                    <div className="flex-1 space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-brand-text-primary">
                          {item.customer_name} 님 ({item.channel_order})
                        </span>
                        <span className="text-[10px] text-brand-text-muted">
                          {new Date(item.created_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                      </div>
                      
                      {/* 수집 원문 출력 (Whisper STT 결과물) */}
                      <p className="text-xs text-brand-text-secondary bg-brand-bg/50 p-2.5 rounded border border-brand-border/40 leading-relaxed font-mono">
                        {item.stt_text || '비정형 음성 원문 추출 대기중...'}
                      </p>

                      {/* Gemini 꽃 주문 적합성 판별 상태 */}
                      <div className="flex justify-end">
                        {item.is_order === 'Y' ? (
                          <span className="inline-flex items-center gap-1 text-[9px] font-bold text-brand-success bg-brand-success/10 px-2 py-0.5 rounded border border-brand-success/20">
                            <CheckCircle2 className="h-2.5 w-2.5" /> AI 꽃 주문 식별
                          </span>
                        ) : item.is_order === 'N' ? (
                          <span className="inline-flex items-center gap-1 text-[9px] font-bold text-brand-error bg-brand-error/10 px-2 py-0.5 rounded border border-brand-error/20">
                            <X className="h-2.5 w-2.5" /> AI 일반 통화 필터링
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[9px] font-bold text-brand-text-muted bg-brand-card px-2 py-0.5 rounded border border-brand-border animate-pulse">
                            AI 분석중...
                          </span>
                        )}
                      </div>

                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
