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
  rpa_status: 'ready' | 'success' | 'manual' | 'fail';
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
