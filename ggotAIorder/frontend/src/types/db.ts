// Supabase 4개 테이블 Row 타입 (docs/database_schema.sql 기준)

export interface MemberInfo {
  id: number;
  username: string;
  password: string;
  shop_name: string;
  representative_name: string;
  landline_number: string | null;
  mobile_number: string;
  email: string | null;
  address: string | null;
  address_detail: string | null;
  is_approved: 'Y' | 'N';
  created_at: string;
}

export interface ServerCallHistory {
  id: number;
  channel_order: string;
  channel_classification: string;
  shop_key: number;
  shop_name: string;
  customer_phone_number: string;
  customer_name: string;
  call_date: string;
  call_time: string;
  duration_seconds: number;
  audio_file_name: string | null;
  stt_text: string | null;
  is_order: 'Y' | 'N';
  created_at: string;
}

export interface OrderDetails {
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
  delivery_at_text: string | null;
  delivery_place: string;
  receiver_name: string;
  receiver_phone_number: string;
  ribbon_sender: string | null;
  ribbon_congratulations: string | null;
  card_message: string | null;
  rpa_status: 'ready' | 'success' | 'manual' | 'fail';
  created_at: string;
}

export interface SettingInfo {
  id: number;
  shop_key: number;
  use_notification: 'Y' | 'N';
  notification_phone_number: string | null;
  rpa_success_message: string;
  rpa_manual_message: string | null;
  rpa_fail_message: string;
  order_hp_1: string;
  order_hp_2: string | null;
  order_landline_1: string | null;
  order_landline_2: string | null;
  shopping_mall_url: string | null;
  shopping_mall_id: string | null;
  shopping_mall_password: string | null;
  intranet_url: string | null;
  intranet_id: string | null;
  intranet_password: string | null;
  shopping_mall_check_interval: number;
  intranet_check_interval: number;
  rpa_program_type: string | null;
  rpa_program_url: string | null;
  rpa_login_id: string | null;
  rpa_login_password: string | null;
  rpa_enabled: string | null;
  rpa_auto_submit: string | null;
  created_at: string;
}
