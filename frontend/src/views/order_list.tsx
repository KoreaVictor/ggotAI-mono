import React, { useState, useEffect } from 'react';
import { supabase } from '../supabase';
import { 
  Search, Eye, Edit2, Play, CheckCircle2, XCircle, AlertCircle, 
  MapPin, Calendar, User, Phone, ShoppingBag, X, Save 
} from 'lucide-react';

interface OrderDetail {
  id: number;
  call_history_id: number;
  shop_key: number;
  shop_name: string;
  customer_name: string;
  customer_phone_number: string;
  product_name: string;
  quantity: number;
  price: number;
  delivery_at: string;
  delivery_place: string;
  receiver_name: string;
  receiver_phone_number: string;
  ribbon_sender: string | null;
  ribbon_congratulations: string | null;
  card_message: string | null;
  rpa_status: 'ready' | 'success' | 'fail';
  created_at: string;
}

export function OrderListView() {
  const [orders, setOrders] = useState<OrderDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  
  // 모달 상태 제어
  const [selectedOrder, setSelectedOrder] = useState<OrderDetail | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedOrder, setEditedOrder] = useState<OrderDetail | null>(null);
  const [modalSuccess, setModalSuccess] = useState('');
  const [modalError, setModalError] = useState('');

  // 1:1 매핑 shop_key 기준 조회
  const defaultShopKey = 1;

  // 주문 로드 함수
  const loadOrders = async () => {
    try {
      setLoading(true);
      let query = supabase
        .from('order_details')
        .select('*')
        .eq('shop_key', defaultShopKey)
        .order('created_at', { ascending: false });

      if (statusFilter !== 'all') {
        query = query.eq('rpa_status', statusFilter);
      }

      const { data, error } = await query;
      if (error) throw error;
      setOrders(data || []);
    } catch (err: any) {
      console.error('주문 로드 에러:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOrders();
  }, [statusFilter]);

  // 검색 필터링 (로컬 필터링)
  const filteredOrders = orders.filter((order) => {
    const query = searchQuery.toLowerCase();
    return (
      order.customer_name.toLowerCase().includes(query) ||
      order.product_name.toLowerCase().includes(query) ||
      order.delivery_place.toLowerCase().includes(query) ||
      order.customer_phone_number.includes(query) ||
      order.receiver_name.toLowerCase().includes(query)
    );
  });

  // 주문 상세 보기 클릭
  const handleViewDetail = (order: OrderDetail) => {
    setSelectedOrder(order);
    setEditedOrder({ ...order });
    setIsEditing(false);
    setModalSuccess('');
    setModalError('');
  };

  // 상세 수정 폼 핸들러
  const handleModalInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    if (editedOrder) {
      setEditedOrder((prev: any) => ({
        ...prev,
        [name]: value,
      }));
    }
  };

  // 수동 수정 사항 저장
  const handleSaveChanges = async () => {
    if (!editedOrder) return;
    setModalSuccess('');
    setModalError('');

    try {
      const { error } = await supabase
        .from('order_details')
        .update({
          customer_name: editedOrder.customer_name,
          customer_phone_number: editedOrder.customer_phone_number,
          product_name: editedOrder.product_name,
          quantity: Number(editedOrder.quantity),
          price: Number(editedOrder.price),
          delivery_at: editedOrder.delivery_at,
          delivery_place: editedOrder.delivery_place,
          receiver_name: editedOrder.receiver_name,
          receiver_phone_number: editedOrder.receiver_phone_number,
          ribbon_sender: editedOrder.ribbon_sender || null,
          ribbon_congratulations: editedOrder.ribbon_congratulations || null,
          card_message: editedOrder.card_message || null,
        })
        .eq('id', editedOrder.id);

      if (error) throw error;

      setModalSuccess('주문 상세 정보가 수동 업데이트되었습니다.');
      setIsEditing(false);
      setSelectedOrder({ ...editedOrder });
      loadOrders(); // 메인 리스트 갱신
    } catch (err: any) {
      setModalError('저장 중 오류 발생: ' + err.message);
    }
  };

  // RPA 재전송 트리거 (RPA 상태를 'ready'로 되돌려 백엔드가 감지해 수행하도록 유도)
  const handleTriggerRPA = async (orderId: number) => {
    try {
      const { error } = await supabase
        .from('order_details')
        .update({ rpa_status: 'ready' })
        .eq('id', orderId);

      if (error) throw error;

      setModalSuccess('RPA 대기열에 주문 전송을 완료했습니다. 백엔드가 즉시 입력을 개시합니다!');
      if (selectedOrder && selectedOrder.id === orderId) {
        setSelectedOrder((prev: any) => ({ ...prev, rpa_status: 'ready' }));
        if (editedOrder) setEditedOrder((prev: any) => ({ ...prev, rpa_status: 'ready' }));
      }
      loadOrders(); // 리스트 갱신
    } catch (err: any) {
      setModalError('RPA 트리거 중 오류 발생: ' + err.message);
    }
  };

  // 상태 뱃지 드로잉
  const renderStatusBadge = (status: 'ready' | 'success' | 'fail') => {
    switch (status) {
      case 'success':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-brand-success/15 text-brand-success border border-brand-success/30">
            <CheckCircle2 className="h-3 w-3" />
            성공
          </span>
        );
      case 'fail':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-brand-error/15 text-brand-error border border-brand-error/30">
            <XCircle className="h-3 w-3" />
            실패
          </span>
        );
      case 'ready':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-brand-warning/15 text-brand-warning border border-brand-warning/30 animate-pulse">
            <Play className="h-3 w-3" />
            RPA 대기중
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
          <h1 className="text-3xl font-display font-bold text-brand-text-primary tracking-tight">주문 내역 관리</h1>
          <p className="text-brand-text-secondary text-sm mt-1">다중 채널에서 AI가 추출한 주문 목록입니다. 수동 편집 및 RPA 재수행이 가능합니다.</p>
        </div>
      </div>

      {/* 필터 및 검색 대시 */}
      <div className="flex flex-col md:flex-row gap-4 items-center justify-between mb-6">
        <div className="relative w-full md:w-80">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-brand-text-muted" />
          <input
            type="text"
            placeholder="주문자, 상품명, 배송지 등 검색..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-brand-card border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg pl-10 pr-4 py-2 text-sm text-brand-text-primary outline-none transition"
          />
        </div>

        {/* 상태별 탭 필터 */}
        <div className="flex bg-brand-card p-1 border border-brand-border rounded-lg self-stretch md:self-auto">
          <button
            onClick={() => setStatusFilter('all')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition ${statusFilter === 'all' ? 'bg-brand-primary text-white shadow-md' : 'text-brand-text-secondary hover:text-brand-text-primary'}`}
          >
            전체 보기
          </button>
          <button
            onClick={() => setStatusFilter('ready')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition ${statusFilter === 'ready' ? 'bg-brand-warning text-brand-bg shadow-md' : 'text-brand-text-secondary hover:text-brand-text-primary'}`}
          >
            RPA 대기
          </button>
          <button
            onClick={() => setStatusFilter('success')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition ${statusFilter === 'success' ? 'bg-brand-success text-white shadow-md' : 'text-brand-text-secondary hover:text-brand-text-primary'}`}
          >
            입력 성공
          </button>
          <button
            onClick={() => setStatusFilter('fail')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition ${statusFilter === 'fail' ? 'bg-brand-error text-white shadow-md' : 'text-brand-text-secondary hover:text-brand-text-primary'}`}
          >
            입력 실패
          </button>
        </div>
      </div>

      {/* 주문 데이터 그리드 테이블 */}
      <div className="glass-panel rounded-xl shadow-xl overflow-hidden">
        {loading ? (
          <div className="flex justify-center items-center py-24">
            <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-brand-primary"></div>
          </div>
        ) : filteredOrders.length === 0 ? (
          <div className="text-center py-24 text-brand-text-muted space-y-2">
            <AlertCircle className="h-10 w-10 mx-auto text-brand-text-muted" />
            <p className="text-sm">조건에 부합하는 주문 내역이 존재하지 않습니다.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-brand-border/80 bg-brand-card/50 text-[11px] font-semibold text-brand-text-secondary uppercase tracking-wider">
                  <th className="px-6 py-4">주문자 정보</th>
                  <th className="px-6 py-4">상품 / 수량</th>
                  <th className="px-6 py-4">배달 일시</th>
                  <th className="px-6 py-4">배달 장소</th>
                  <th className="px-6 py-4 text-center">RPA 결과</th>
                  <th className="px-6 py-4 text-right">관리</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border/40 text-sm text-brand-text-primary">
                {filteredOrders.map((order) => (
                  <tr 
                    key={order.id} 
                    className="hover:bg-brand-card-hover/40 transition group cursor-pointer"
                    onClick={() => handleViewDetail(order)}
                  >
                    <td className="px-6 py-4.5">
                      <div className="font-semibold text-brand-text-primary">{order.customer_name}</div>
                      <div className="text-xs text-brand-text-muted mt-0.5">{order.customer_phone_number}</div>
                    </td>
                    <td className="px-6 py-4.5">
                      <div className="font-medium">{order.product_name}</div>
                      <div className="text-xs text-brand-text-muted mt-0.5">{order.quantity}개 / {order.price.toLocaleString()}원</div>
                    </td>
                    <td className="px-6 py-4.5">
                      <div className="text-xs">
                        {new Date(order.delivery_at).toLocaleString('ko-KR', {
                          month: 'long',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </div>
                    </td>
                    <td className="px-6 py-4.5 max-w-[200px] truncate">
                      <span className="text-xs text-brand-text-secondary">{order.delivery_place}</span>
                    </td>
                    <td className="px-6 py-4.5 text-center">
                      {renderStatusBadge(order.rpa_status)}
                    </td>
                    <td className="px-6 py-4.5 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => handleViewDetail(order)}
                          className="p-1.5 hover:bg-brand-border rounded-lg text-brand-text-secondary hover:text-brand-primary transition"
                          title="상세 보기"
                        >
                          <Eye className="h-4 w-4" />
                        </button>
                        {order.rpa_status === 'fail' && (
                          <button
                            onClick={() => handleTriggerRPA(order.id)}
                            className="p-1.5 hover:bg-brand-warning/15 rounded-lg text-brand-warning hover:text-brand-warning transition"
                            title="RPA 수동 재시작"
                          >
                            <Play className="h-4 w-4" />
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
      </div>

      {/* 주문 상세 및 수정 모달 (Glassmorphism 팝업) */}
      {selectedOrder && editedOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in-up">
          <div className="glass-panel w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden border border-brand-border flex flex-col max-h-[90vh]">
            {/* 모달 헤더 */}
            <div className="px-6 py-4 border-b border-brand-border/80 flex justify-between items-center bg-brand-card">
              <div className="flex items-center gap-2">
                <ShoppingBag className="h-5 w-5 text-brand-primary" />
                <h3 className="font-semibold text-brand-text-primary text-base">주문 상세 명세서</h3>
                {renderStatusBadge(selectedOrder.rpa_status)}
              </div>
              <button 
                onClick={() => setSelectedOrder(null)}
                className="p-1.5 hover:bg-brand-border rounded-lg text-brand-text-muted hover:text-brand-text-primary transition"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* 모달 내용물 */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1">
              
              {modalSuccess && (
                <div className="flex items-center gap-2 p-3.5 bg-brand-success/15 border border-brand-success/30 rounded-lg text-brand-success text-xs">
                  <CheckCircle2 className="h-4.5 w-4.5" />
                  <span>{modalSuccess}</span>
                </div>
              )}

              {modalError && (
                <div className="flex items-center gap-2 p-3.5 bg-brand-error/15 border border-brand-error/30 rounded-lg text-brand-error text-xs">
                  <AlertCircle className="h-4.5 w-4.5" />
                  <span>{modalError}</span>
                </div>
              )}

              {/* 편집 폼과 정보 출력 분기 */}
              {!isEditing ? (
                // 1) 상세 정보 뷰어
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  
                  {/* 주문자/수령자 */}
                  <div className="space-y-4 bg-brand-bg/30 p-5 border border-brand-border/50 rounded-xl">
                    <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider border-b border-brand-border/40 pb-2 flex items-center gap-1.5">
                      <User className="h-4 w-4" /> 인적 사항 (주문 & 배달 대상)
                    </h4>
                    <div className="space-y-3.5 text-sm">
                      <div className="flex justify-between">
                        <span className="text-brand-text-secondary">보내는 분:</span>
                        <span className="font-semibold">{selectedOrder.customer_name} ({selectedOrder.customer_phone_number})</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-brand-text-secondary">받으시는 분:</span>
                        <span className="font-semibold">{selectedOrder.receiver_name} ({selectedOrder.receiver_phone_number})</span>
                      </div>
                    </div>
                  </div>

                  {/* 배송/결제 */}
                  <div className="space-y-4 bg-brand-bg/30 p-5 border border-brand-border/50 rounded-xl">
                    <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider border-b border-brand-border/40 pb-2 flex items-center gap-1.5">
                      <Calendar className="h-4 w-4" /> 상품 및 배송 내역
                    </h4>
                    <div className="space-y-3.5 text-sm">
                      <div className="flex justify-between">
                        <span className="text-brand-text-secondary">상품 / 수량:</span>
                        <span className="font-semibold">{selectedOrder.product_name} ({selectedOrder.quantity}개)</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-brand-text-secondary">결제 가격:</span>
                        <span className="font-semibold text-brand-success">{selectedOrder.price.toLocaleString()} 원</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-brand-text-secondary">배달 약속 일시:</span>
                        <span className="font-semibold">{new Date(selectedOrder.delivery_at).toLocaleString('ko-KR')}</span>
                      </div>
                    </div>
                  </div>

                  {/* 배송지 */}
                  <div className="md:col-span-2 space-y-3 bg-brand-bg/30 p-5 border border-brand-border/50 rounded-xl">
                    <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider border-b border-brand-border/40 pb-2 flex items-center gap-1.5">
                      <MapPin className="h-4 w-4" /> 배달 목적지 주소
                    </h4>
                    <div className="text-sm font-semibold">{selectedOrder.delivery_place}</div>
                  </div>

                  {/* 꽃집용 경조사 리본 및 메시지 카드 */}
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
              ) : (
                // 2) 상세 정보 편집 수정 폼
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  
                  <div>
                    <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">보내는분 성명</label>
                    <input
                      type="text"
                      name="customer_name"
                      value={editedOrder.customer_name}
                      onChange={handleModalInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">보내는분 전화번호</label>
                    <input
                      type="text"
                      name="customer_phone_number"
                      value={editedOrder.customer_phone_number}
                      onChange={handleModalInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">받는분 성명</label>
                    <input
                      type="text"
                      name="receiver_name"
                      value={editedOrder.receiver_name}
                      onChange={handleModalInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">받는분 전화번호</label>
                    <input
                      type="text"
                      name="receiver_phone_number"
                      value={editedOrder.receiver_phone_number}
                      onChange={handleModalInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">주문 상품명</label>
                    <input
                      type="text"
                      name="product_name"
                      value={editedOrder.product_name}
                      onChange={handleModalInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">수량</label>
                      <input
                        type="number"
                        name="quantity"
                        value={editedOrder.quantity}
                        onChange={handleModalInputChange}
                        className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">결제 금액(원)</label>
                      <input
                        type="number"
                        name="price"
                        value={editedOrder.price}
                        onChange={handleModalInputChange}
                        className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition"
                      />
                    </div>
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">배달 약속 일시</label>
                    <input
                      type="text"
                      name="delivery_at"
                      placeholder="YYYY-MM-DD HH:MM:SS"
                      value={editedOrder.delivery_at}
                      onChange={handleModalInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">배달 목적지 주소</label>
                    <input
                      type="text"
                      name="delivery_place"
                      value={editedOrder.delivery_place}
                      onChange={handleModalInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">리본 경조문구(오른쪽)</label>
                    <input
                      type="text"
                      name="ribbon_congratulations"
                      value={editedOrder.ribbon_congratulations || ''}
                      onChange={handleModalInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">리본 보내는이(왼쪽)</label>
                    <input
                      type="text"
                      name="ribbon_sender"
                      value={editedOrder.ribbon_sender || ''}
                      onChange={handleModalInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-[10px] font-bold text-brand-text-secondary uppercase mb-1.5">전달할 메시지 카드 문구</label>
                    <textarea
                      name="card_message"
                      rows={3}
                      value={editedOrder.card_message || ''}
                      onChange={handleModalInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary rounded-lg px-4 py-2 text-sm text-brand-text-primary outline-none transition resize-y"
                    />
                  </div>

                </div>
              )}

            </div>

            {/* 모달 푸터 */}
            <div className="px-6 py-4 border-t border-brand-border/80 flex flex-col sm:flex-row gap-3 sm:justify-between bg-brand-card">
              {/* 왼쪽: RPA 실패 시 재전송 */}
              <div>
                {selectedOrder.rpa_status === 'fail' && !isEditing && (
                  <button
                    onClick={() => handleTriggerRPA(selectedOrder.id)}
                    className="flex items-center gap-1.5 px-4 py-2 bg-brand-warning text-brand-bg hover:bg-brand-warning/90 text-xs font-semibold rounded-lg transition cursor-pointer"
                  >
                    <Play className="h-3.5 w-3.5" />
                    <span>전산에 RPA로 재입력 시키기</span>
                  </button>
                )}
              </div>

              {/* 오른쪽: 편집/저장 버튼 */}
              <div className="flex gap-2.5 justify-end">
                {isEditing ? (
                  <>
                    <button
                      onClick={() => setIsEditing(false)}
                      className="px-4 py-2 border border-brand-border hover:bg-brand-card text-brand-text-secondary hover:text-brand-text-primary text-xs font-semibold rounded-lg transition"
                    >
                      취소
                    </button>
                    <button
                      onClick={handleSaveChanges}
                      className="flex items-center gap-1.5 px-4 py-2 bg-brand-primary hover:bg-brand-primary-hover text-white text-xs font-semibold rounded-lg transition cursor-pointer"
                    >
                      <Save className="h-3.5 w-3.5" />
                      <span>저장하기</span>
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => setIsEditing(true)}
                    className="flex items-center gap-1.5 px-4 py-2 bg-brand-card hover:bg-brand-border border border-brand-border text-brand-text-primary text-xs font-semibold rounded-lg transition"
                  >
                    <Edit2 className="h-3.5 w-3.5" />
                    <span>상세 내역 수동 수정</span>
                  </button>
                )}
              </div>

            </div>

          </div>
        </div>
      )}

    </div>
  );
}
