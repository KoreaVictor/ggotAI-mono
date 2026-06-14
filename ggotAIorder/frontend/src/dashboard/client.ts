// supabase.rpc 와 호환되는 최소 계약(테스트 주입용)
export type DashRpc = (fn: string, args: Record<string, unknown>) => Promise<{ data: unknown; error: unknown }>;

export interface Stats { today_total: number; rpa_success: number; rpa_fail: number; rpa_ready: number; }
export interface ChannelAgg { channel_order: string; total: number; success: number; }
export interface Config { garjeon: boolean; hp1: boolean; hp2: boolean; voice: boolean; mall: boolean; intranet: boolean; }
export interface FeedRow {
  id: number; channel_order: string; customer_name: string | null;
  stt_text: string | null; is_order: string | null; rpa_status: string | null; created_at: string;
}
export interface DashboardData { stats: Stats; channels: ChannelAgg[]; config: Config; feed: FeedRow[]; }

export async function getDashboard(
  rpc: DashRpc, shopKey: number, token: string,
): Promise<{ ok: boolean; data?: DashboardData; reason?: string }> {
  const { data, error } = await rpc('get_dashboard', { p_shop_key: shopKey, p_token: token });
  if (error) return { ok: false, reason: 'error' };
  const d = data as (DashboardData & { ok?: boolean; reason?: string }) | null;
  if (!d || !d.ok) return { ok: false, reason: d?.reason ?? 'error' };
  return { ok: true, data: { stats: d.stats, channels: d.channels, config: d.config, feed: d.feed } };
}
