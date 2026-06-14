import { useState, useEffect } from 'react';
import { supabase } from '../supabase';
import { useSession } from '../session/SessionContext';
import { getOrders, requeueOrder, type OrderRow } from '../orders/client';
import type { DashRpc } from '../dashboard/client';
import {
  Search, Eye, Play, CheckCircle2, XCircle, AlertCircle,
  MapPin, Calendar, User, ShoppingBag, X, RefreshCw,
} from 'lucide-react';

const rpc: DashRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<DashRpc>;

// 채널 세그먼트(전체 + 5채널). value=null 이면 전체. 핸드폰1·2는 '핸드폰' 공유.
const CHANNEL_SEGMENTS: { label: string; value: string | null }[] = [
  { label: '전체', value: null },
  { label: '핸드폰', value: '핸드폰' },
  { label: '가게전화', value: '가게전화' },
  { label: '쇼핑몰', value: '쇼핑몰' },
  { label: '인터라넷', value: '인터라넷' },
  { label: '가게음성', value: '가게음성' },
];

// 오늘(KST) 'YYYY-MM-DD'
function todayKst(): string {
  return new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
}
// 'YYYY-MM-DD' → 해당일 00:00 KST(포함 경계)
function kstStartIso(dateStr: string): string {
  return `${dateStr}T00:00:00+09:00`;
}
// 'YYYY-MM-DD' → 다음날 00:00 KST(미포함 경계)
function kstEndIsoExclusive(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const next = new Date(Date.UTC(y, m - 1, d + 1));
  const ny = next.getUTCFullYear();
  const nm = String(next.getUTCMonth() + 1).padStart(2, '0');
  const nd = String(next.getUTCDate()).padStart(2, '0');
  return `${ny}-${nm}-${nd}T00:00:00+09:00`;
}

export function OrderListView() {
  const { session, readToken } = useSession();
  const shopKey = session?.shopKey ?? 0;

  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  // 필터(서버): 채널 / 상태 / 기간
  const [channel, setChannel] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [startDate, setStartDate] = useState<string>(todayKst());
  const [endDate, setEndDate] = useState<string>(todayKst());

  // 검색(클라이언트)
  const [searchQuery, setSearchQuery] = useState('');

  // 읽기전용 상세 모달
  const [selectedOrder, setSelectedOrder] = useState<OrderRow | null>(null);
  const [modalSuccess, setModalSuccess] = useState('');
  const [modalError, setModalError] = useState('');

  const loadOrders = async () => {
    if (!shopKey || !readToken) { setLoadError('세션이 만료되었습니다. 다시 로그인해주세요.'); setLoading(false); return; }
    setLoading(true);
    const r = await getOrders(rpc, shopKey, readToken, {
      channel,
      status: statusFilter === 'all' ? null : statusFilter,
      start: kstStartIso(startDate),
      end: kstEndIsoExclusive(endDate),
    });
    if (!r.ok || !r.rows) {
      setLoadError(r.reason === 'unauthorized' ? '세션이 만료되었습니다. 다시 로그인해주세요.' : '주문 내역을 불러오지 못했습니다.');
      setLoading(false);
      return;
    }
    setLoadError('');
    setOrders(r.rows);
    setLoading(false);
  };

  // 진입 시 + 채널/상태 변경 시 자동 조회(기간은 [조회] 버튼으로 명시 조회)
  useEffect(() => {
    loadOrders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shopKey, readToken, channel, statusFilter]);

  // 텍스트 검색(불러온 행 narrowing)
  const filteredOrders = orders.filter((order) => {
    const q = searchQuery.toLowerCase();
    if (!q) return true;
    return (
      (order.customer_name ?? '').toLowerCase().includes(q) ||
      order.product_name.toLowerCase().includes(q) ||
      order.delivery_place.toLowerCase().includes(q) ||
      order.customer_phone_number.includes(q) ||
      order.receiver_name.toLowerCase().includes(q)
    );
  });

  // 요약바: 화면 표시중(검색 적용 후) 행 기준 클라이언트 파생
  const totalCount = filteredOrders.length;
  const totalAmount = filteredOrders.reduce((sum, o) => sum + (o.price ?? 0), 0);

  const handleViewDetail = (order: OrderRow) => {
    setSelectedOrder(order);
    setModalSuccess('');
    setModalError('');
  };

  const handleRequeue = async (orderId: number) => {
    setModalSuccess('');
    setModalError('');
    const r = await requeueOrder(rpc, shopKey, readToken ?? '', orderId);
    if (!r.ok) {
      setModalError(r.reason === 'unauthorized' ? '세션이 만료되었습니다. 다시 로그인해주세요.'
        : r.reason === 'not_found' ? '해당 주문을 찾을 수 없습니다.' : 'RPA 재전송 중 오류가 발생했습니다.');
      return;
    }
    setModalSuccess('RPA 대기열에 주문을 전송했습니다. 백엔드가 곧 입력을 시작합니다.');
    setOrders((prev) => prev.map((o) => (o.id === orderId ? { ...o, rpa_status: 'ready' } : o)));
    if (selectedOrder && selectedOrder.id === orderId) {
      setSelectedOrder((prev) => (prev ? { ...prev, rpa_status: 'ready' } : prev));
    }
  };

  const renderStatusBadge = (status: 'ready' | 'success' | 'fail') => {
    switch (status) {
      case 'success':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-brand-success/15 text-brand-success border border-brand-success/30">
            <CheckCircle2 className="h-3 w-3" />성공
          </span>
        );
      case 'fail':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-brand-error/15 text-brand-error border border-brand-error/30">
            <XCircle className="h-3 w-3" />실패
          </span>
        );
      case 'ready':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-brand-warning/15 text-brand-warning border border-brand-warning/30 animate-pulse">
            <Play className="h-3 w-3" />대기중
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8 animate-fade-in-up">
      {/* 헤더 */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-display font-bold text-brand-text-primary tracking-tight">주문 내역 조회</h1>
          <p className="text-brand-text-secondary text-sm mt-1">채널·기간·상태로 조회하고, 입력 실패 주문을 RPA로 재전송할 수 있습니다.</p>
        </div>
      </div>

      {/* 필터바: 채널 세그먼트 + 기간 + 조회 + 검색 */}
      <div className="glass-panel rounded-xl border border-brand-border p-4 mb-6 space-y-4">
        {/* 채널 세그먼트 */}
        <div className="flex flex-wrap gap-1.5">
          {CHANNEL_SEGMENTS.map((seg) => (
            <button
              key={seg.label}
              onClick={() => setChannel(seg.value)}
              className={`px-3.5 py-1.5 text-xs font-semibold rounded-md transition ${channel === seg.value ? 'bg-brand-primary text-white shadow' : 'bg-brand-card text-brand-text-secondary hover:text-brand-text-primary border border-brand-border'}`}
            >
              {seg.label}
            </button>
          ))}
        </div>

        {/* 기간 + 조회 + 상태 + 검색 */}
        <div className="flex flex-col lg:flex-row lg:items-center gap-3">
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-brand-text-muted" />
            <input type="date" value={startDate} max={endDate} onChange={(e) => setStartDate(e.target.value)}
              className="bg-brand-card border border-brand-border rounded-lg px-3 py-2 text-sm text-brand-text-primary outline-none focus:border-brand-primary" />
            <span className="text-brand-text-muted text-sm">~</span>
            <input type="date" value={endDate} min={startDate} onChange={(e) => setEndDate(e.target.value)}
              className="bg-brand-card border border-brand-border rounded-lg px-3 py-2 text-sm text-brand-text-primary outline-none focus:border-brand-primary" />
            <button onClick={loadOrders}
              className="flex items-center gap-1.5 px-4 py-2 bg-brand-primary hover:bg-brand-primary-hover text-white text-xs font-semibold rounded-lg transition">
              <Search className="h-3.5 w-3.5" />조회
            </button>
          </div>

          {/* 상태 탭 */}
          <div className="flex bg-brand-card p-1 border border-brand-border rounded-lg lg:ml-2">
            {([['all', '전체'], ['ready', '대기'], ['success', '성공'], ['fail', '실패']] as const).map(([val, label]) => (
              <button key={val} onClick={() => setStatusFilter(val)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition ${statusFilter === val ? 'bg-brand-primary text-white shadow-md' : 'text-brand-text-secondary hover:text-brand-text-primary'}`}>
                {label}
              </button>
            ))}
          </div>

          {/* 검색(클라이언트) */}
          <div className="relative w-full lg:w-64 lg:ml-auto">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-brand-text-muted" />
            <input type="text" placeholder="고객명·상품·배송지 검색..." value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-brand-card border border-brand-border focus:border-brand-primary rounded-lg pl-10 pr-4 py-2 text-sm text-brand-text-primary outline-none transition" />
          </div>
        </div>
      </div>

      {loadError && <div className="mb-6 text-sm text-brand-error bg-brand-error/10 border border-brand-error/20 rounded-xl px-4 py-3">{loadError}</div>}

      {/* 주문 그리드 */}
      <div className="glass-panel rounded-xl shadow-xl overflow-hidden">
        {loading ? (
          <div className="flex justify-center items-center py-24">
            <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-brand-primary"></div>
          </div>
        ) : filteredOrders.length === 0 ? (
          <div className="text-center py-24 text-brand-text-muted space-y-2">
            <AlertCircle className="h-10 w-10 mx-auto text-brand-text-muted" />
            <p className="text-sm">조건에 부합하는 주문 내역이 없습니다.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-brand-border/80 bg-brand-card/50 text-[11px] font-semibold text-brand-text-secondary uppercase tracking-wider">
                  <th className="px-5 py-4">주문일시</th>
                  <th className="px-5 py-4">주문자</th>
                  <th className="px-5 py-4">상품 / 수량</th>
                  <th className="px-5 py-4 text-right">가격</th>
                  <th className="px-5 py-4">배달 장소</th>
                  <th className="px-5 py-4 text-center">채널</th>
                  <th className="px-5 py-4 text-center">입력상태</th>
                  <th className="px-5 py-4 text-right">관리</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border/40 text-sm text-brand-text-primary">
                {filteredOrders.map((order) => (
                  <tr key={order.id} className="hover:bg-brand-card-hover/40 transition group cursor-pointer" onClick={() => handleViewDetail(order)}>
                    <td className="px-5 py-4 text-xs">
                      {new Date(order.created_at).toLocaleString('ko-KR', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="px-5 py-4">
                      <div className="font-semibold text-brand-text-primary">{order.customer_name ?? '고객'}</div>
                      <div className="text-xs text-brand-text-muted mt-0.5">{order.customer_phone_number}</div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="font-medium">{order.product_name}</div>
                      <div className="text-xs text-brand-text-muted mt-0.5">{order.quantity ?? 0}개</div>
                    </td>
                    <td className="px-5 py-4 text-right font-semibold text-brand-success">{(order.price ?? 0).toLocaleString()}원</td>
                    <td className="px-5 py-4 max-w-[180px] truncate"><span className="text-xs text-brand-text-secondary">{order.delivery_place}</span></td>
                    <td className="px-5 py-4 text-center"><span className="text-xs text-brand-text-secondary">{order.channel_order ?? '-'}</span></td>
                    <td className="px-5 py-4 text-center">{renderStatusBadge(order.rpa_status)}</td>
                    <td className="px-5 py-4 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-2">
                        <button onClick={() => handleViewDetail(order)} className="p-1.5 hover:bg-brand-border rounded-lg text-brand-text-secondary hover:text-brand-primary transition" title="상세 보기">
                          <Eye className="h-4 w-4" />
                        </button>
                        {order.rpa_status === 'fail' && (
                          <button onClick={() => handleRequeue(order.id)} className="p-1.5 hover:bg-brand-warning/15 rounded-lg text-brand-warning transition" title="RPA 재전송">
                            <RefreshCw className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 하단 요약바 */}
        {!loading && filteredOrders.length > 0 && (
          <div className="flex items-center justify-end gap-6 px-6 py-4 border-t border-brand-border/80 bg-brand-card/40 text-sm">
            <span className="text-brand-text-secondary">총 건수 <span className="font-bold text-brand-text-primary">{totalCount.toLocaleString()}</span>건</span>
            <span className="text-brand-text-secondary">총 금액 <span className="font-bold text-brand-success">{totalAmount.toLocaleString()}</span>원</span>
          </div>
        )}
      </div>

      {/* 읽기전용 상세 모달 */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in-up">
          <div className="glass-panel w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden border border-brand-border flex flex-col max-h-[90vh]">
            <div className="px-6 py-4 border-b border-brand-border/80 flex justify-between items-center bg-brand-card">
              <div className="flex items-center gap-2">
                <ShoppingBag className="h-5 w-5 text-brand-primary" />
                <h3 className="font-semibold text-brand-text-primary text-base">주문 상세 명세서</h3>
                {renderStatusBadge(selectedOrder.rpa_status)}
                <span className="text-xs text-brand-text-muted">({selectedOrder.channel_order ?? '-'})</span>
              </div>
              <button onClick={() => setSelectedOrder(null)} className="p-1.5 hover:bg-brand-border rounded-lg text-brand-text-muted hover:text-brand-text-primary transition">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-6 flex-1">
              {modalSuccess && (
                <div className="flex items-center gap-2 p-3.5 bg-brand-success/15 border border-brand-success/30 rounded-lg text-brand-success text-xs">
                  <CheckCircle2 className="h-4.5 w-4.5" /><span>{modalSuccess}</span>
                </div>
              )}
              {modalError && (
                <div className="flex items-center gap-2 p-3.5 bg-brand-error/15 border border-brand-error/30 rounded-lg text-brand-error text-xs">
                  <AlertCircle className="h-4.5 w-4.5" /><span>{modalError}</span>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-4 bg-brand-bg/30 p-5 border border-brand-border/50 rounded-xl">
                  <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider border-b border-brand-border/40 pb-2 flex items-center gap-1.5">
                    <User className="h-4 w-4" /> 인적 사항 (주문 & 배달 대상)
                  </h4>
                  <div className="space-y-3.5 text-sm">
                    <div className="flex justify-between">
                      <span className="text-brand-text-secondary">보내는 분:</span>
                      <span className="font-semibold">{selectedOrder.customer_name ?? '고객'} ({selectedOrder.customer_phone_number})</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-brand-text-secondary">받으시는 분:</span>
                      <span className="font-semibold">{selectedOrder.receiver_name} ({selectedOrder.receiver_phone_number})</span>
                    </div>
                  </div>
                </div>

                <div className="space-y-4 bg-brand-bg/30 p-5 border border-brand-border/50 rounded-xl">
                  <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider border-b border-brand-border/40 pb-2 flex items-center gap-1.5">
                    <Calendar className="h-4 w-4" /> 상품 및 배송 내역
                  </h4>
                  <div className="space-y-3.5 text-sm">
                    <div className="flex justify-between">
                      <span className="text-brand-text-secondary">상품 / 수량:</span>
                      <span className="font-semibold">{selectedOrder.product_name} ({selectedOrder.quantity ?? 0}개)</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-brand-text-secondary">결제 가격:</span>
                      <span className="font-semibold text-brand-success">{(selectedOrder.price ?? 0).toLocaleString()} 원</span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-brand-text-secondary shrink-0">배달 약속 일시:</span>
                      <span className="font-semibold text-right">
                        {selectedOrder.delivery_at_text ?? new Date(selectedOrder.delivery_at).toLocaleString('ko-KR')}
                        {selectedOrder.delivery_at_text && !selectedOrder.delivery_at.startsWith('2099') && (
                          <span className="block text-xs font-normal text-brand-text-muted">
                            {new Date(selectedOrder.delivery_at).toLocaleString('ko-KR')}
                          </span>
                        )}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="md:col-span-2 space-y-3 bg-brand-bg/30 p-5 border border-brand-border/50 rounded-xl">
                  <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider border-b border-brand-border/40 pb-2 flex items-center gap-1.5">
                    <MapPin className="h-4 w-4" /> 배달 목적지 주소
                  </h4>
                  <div className="text-sm font-semibold">{selectedOrder.delivery_place}</div>
                </div>

                <div className="md:col-span-2 space-y-4 bg-brand-bg/30 p-5 border border-brand-border/50 rounded-xl">
                  <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider border-b border-brand-border/40 pb-2">
                    🎗️ 리본 문구 및 메시지 카드 내역
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                    <div className="bg-brand-card p-3 rounded-lg border border-brand-border/50">
                      <span className="block text-[10px] text-brand-text-muted font-bold uppercase mb-1">리본 경조 문구 (오른쪽 리본)</span>
                      <div className="font-semibold text-brand-text-primary">{selectedOrder.ribbon_congratulations || '(없음)'}</div>
                    </div>
                    <div className="bg-brand-card p-3 rounded-lg border border-brand-border/50">
                      <span className="block text-[10px] text-brand-text-muted font-bold uppercase mb-1">리본 보내는이 문구 (왼쪽 리본)</span>
                      <div className="font-semibold text-brand-text-primary">{selectedOrder.ribbon_sender || '(없음)'}</div>
                    </div>
                    <div className="md:col-span-2 bg-brand-card p-3 rounded-lg border border-brand-border/50">
                      <span className="block text-[10px] text-brand-text-muted font-bold uppercase mb-1">전달할 카드 메시지</span>
                      <div className="font-semibold text-brand-text-primary whitespace-pre-line">{selectedOrder.card_message || '(없음)'}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 모달 푸터: fail 시 재전송만 */}
            <div className="px-6 py-4 border-t border-brand-border/80 flex justify-between items-center bg-brand-card">
              <div>
                {selectedOrder.rpa_status === 'fail' && (
                  <button onClick={() => handleRequeue(selectedOrder.id)}
                    className="flex items-center gap-1.5 px-4 py-2 bg-brand-warning text-brand-bg hover:bg-brand-warning/90 text-xs font-semibold rounded-lg transition">
                    <RefreshCw className="h-3.5 w-3.5" /><span>전산에 RPA로 재입력 시키기</span>
                  </button>
                )}
              </div>
              <button onClick={() => setSelectedOrder(null)}
                className="px-4 py-2 border border-brand-border hover:bg-brand-card text-brand-text-secondary hover:text-brand-text-primary text-xs font-semibold rounded-lg transition">
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
