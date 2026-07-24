import type { DashRpc } from '../dashboard/client';

export interface OrderRow {
  id: number;
  call_history_id: number;
  customer_name: string | null;
  customer_phone_number: string;
  product_name: string;
  quantity: number | null;
  price: number | null;
  delivery_at: string;
  delivery_at_text: string | null;
  delivery_place: string;
  receiver_name: string;
  receiver_phone_number: string;
  ribbon_sender: string | null;
  ribbon_congratulations: string | null;
  card_message: string | null;
  // 'hold' = 필수값 누락으로 자동입력 보류 — 사장님이 채워야 넘어간다.
  rpa_status: 'ready' | 'success' | 'manual' | 'fail' | 'hold';
  created_at: string;
  channel_order: string | null;
}

export interface OrderFilters {
  channel?: string | null;  // null=전체
  status?: string | null;   // null=전체
  start: string;            // ISO(오프셋 포함)
  end: string;              // ISO(오프셋 포함, 미포함 경계)
}

export async function getOrders(
  rpc: DashRpc, shopKey: number, token: string, f: OrderFilters,
): Promise<{ ok: boolean; rows?: OrderRow[]; reason?: string }> {
  const { data, error } = await rpc('get_orders', {
    p_shop_key: shopKey, p_token: token,
    p_channel: f.channel ?? null, p_status: f.status ?? null,
    p_start: f.start, p_end: f.end,
  });
  if (error) return { ok: false, reason: 'error' };
  const d = data as { ok?: boolean; rows?: OrderRow[]; reason?: string } | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true, rows: d.rows ?? [] };
}

/** 보류 주문 보완 화면에서 편집 가능한 필드(안 채운 칸은 생략). */
export interface HoldPatch {
  product_name?: string;
  price?: number;
  quantity?: number;
  delivery_at?: string;
  delivery_place?: string;
  receiver_name?: string;
  receiver_phone_number?: string;
  customer_name?: string;
  customer_phone_number?: string;
  ribbon_congratulations?: string;
  card_message?: string;
  sang_divi?: string;
}

const HOLD_FIELDS: (keyof HoldPatch)[] = [
  'product_name', 'price', 'quantity', 'delivery_at', 'delivery_place',
  'receiver_name', 'receiver_phone_number', 'customer_name', 'customer_phone_number',
  'ribbon_congratulations', 'card_message', 'sang_divi',
];

/**
 * 보류(hold) 주문의 빈 칸을 채우고 자동입력 대기로 되돌린다.
 *
 * 안 채운 필드는 null 로 보낸다 — 서버가 '변경 없음'으로 처리해 기존 값을 덮어쓰지 않는다.
 * 보완 후에도 필수값이 비어 있으면 서버가 still_incomplete 로 거절하고 hold 를 유지한다.
 */
export async function completeHoldOrder(
  rpc: DashRpc, shopKey: number, token: string, orderId: number, patch: HoldPatch,
): Promise<{ ok: boolean; rpa_status?: string; reason?: string }> {
  const args: Record<string, unknown> = {
    p_shop_key: shopKey, p_token: token, p_order_id: orderId,
  };
  for (const field of HOLD_FIELDS) {
    args[`p_${field}`] = patch[field] ?? null;
  }
  const { data, error } = await rpc('complete_hold_order', args);
  if (error) return { ok: false, reason: 'error' };
  const d = data as { ok?: boolean; rpa_status?: string; reason?: string } | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true, rpa_status: d.rpa_status };
}

export async function requeueOrder(
  rpc: DashRpc, shopKey: number, token: string, orderId: number,
): Promise<{ ok: boolean; rpa_status?: string; reason?: string }> {
  const { data, error } = await rpc('requeue_order', {
    p_shop_key: shopKey, p_token: token, p_order_id: orderId,
  });
  if (error) return { ok: false, reason: 'error' };
  const d = data as { ok?: boolean; rpa_status?: string; reason?: string } | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true, rpa_status: d.rpa_status };
}
