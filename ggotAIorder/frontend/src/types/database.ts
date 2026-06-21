export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  graphql_public: {
    Tables: {
      [_ in never]: never
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      graphql: {
        Args: {
          extensions?: Json
          operationName?: string
          query?: string
          variables?: Json
        }
        Returns: Json
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  public: {
    Tables: {
      member_info: {
        Row: {
          address: string | null
          address_detail: string | null
          created_at: string | null
          email: string | null
          id: number
          is_approved: string | null
          landline_number: string | null
          mobile_number: string
          password: string
          remember_token_expires_at: string | null
          remember_token_hash: string | null
          representative_name: string
          shop_name: string
          username: string
        }
        Insert: {
          address?: string | null
          address_detail?: string | null
          created_at?: string | null
          email?: string | null
          id?: number
          is_approved?: string | null
          landline_number?: string | null
          mobile_number: string
          password: string
          remember_token_expires_at?: string | null
          remember_token_hash?: string | null
          representative_name: string
          shop_name: string
          username: string
        }
        Update: {
          address?: string | null
          address_detail?: string | null
          created_at?: string | null
          email?: string | null
          id?: number
          is_approved?: string | null
          landline_number?: string | null
          mobile_number?: string
          password?: string
          remember_token_expires_at?: string | null
          remember_token_hash?: string | null
          representative_name?: string
          shop_name?: string
          username?: string
        }
        Relationships: []
      }
      order_details: {
        Row: {
          call_history_id: number
          card_message: string | null
          created_at: string | null
          customer_name: string | null
          customer_phone_number: string
          delivery_at: string
          delivery_at_text: string | null
          delivery_place: string
          id: number
          price: number | null
          product_name: string
          quantity: number | null
          receiver_name: string
          receiver_phone_number: string
          ribbon_congratulations: string | null
          ribbon_sender: string | null
          rpa_status: string | null
          shop_key: number
          shop_name: string
        }
        Insert: {
          call_history_id: number
          card_message?: string | null
          created_at?: string | null
          customer_name?: string | null
          customer_phone_number: string
          delivery_at: string
          delivery_at_text?: string | null
          delivery_place: string
          id?: number
          price?: number | null
          product_name: string
          quantity?: number | null
          receiver_name: string
          receiver_phone_number: string
          ribbon_congratulations?: string | null
          ribbon_sender?: string | null
          rpa_status?: string | null
          shop_key: number
          shop_name: string
        }
        Update: {
          call_history_id?: number
          card_message?: string | null
          created_at?: string | null
          customer_name?: string | null
          customer_phone_number?: string
          delivery_at?: string
          delivery_at_text?: string | null
          delivery_place?: string
          id?: number
          price?: number | null
          product_name?: string
          quantity?: number | null
          receiver_name?: string
          receiver_phone_number?: string
          ribbon_congratulations?: string | null
          ribbon_sender?: string | null
          rpa_status?: string | null
          shop_key?: number
          shop_name?: string
        }
        Relationships: [
          {
            foreignKeyName: "order_details_call_history_id_fkey"
            columns: ["call_history_id"]
            isOneToOne: false
            referencedRelation: "server_call_history"
            referencedColumns: ["id"]
          },
        ]
      }
      phone_verification: {
        Row: {
          attempts: number
          code_hash: string
          created_at: string
          expires_at: string
          id: number
          phone: string
          purpose: string
          token_expires_at: string | null
          token_hash: string | null
          verified: boolean
        }
        Insert: {
          attempts?: number
          code_hash: string
          created_at?: string
          expires_at: string
          id?: number
          phone: string
          purpose: string
          token_expires_at?: string | null
          token_hash?: string | null
          verified?: boolean
        }
        Update: {
          attempts?: number
          code_hash?: string
          created_at?: string
          expires_at?: string
          id?: number
          phone?: string
          purpose?: string
          token_expires_at?: string | null
          token_hash?: string | null
          verified?: boolean
        }
        Relationships: []
      }
      server_call_history: {
        Row: {
          audio_file_name: string | null
          call_date: string
          call_time: string
          channel_classification: string
          channel_order: string | null
          created_at: string | null
          customer_name: string | null
          customer_phone_number: string | null
          duration_seconds: number | null
          id: number
          is_order: string | null
          process_attempts: number
          processed_at: string | null
          shop_key: number
          shop_name: string
          stt_text: string | null
        }
        Insert: {
          audio_file_name?: string | null
          call_date: string
          call_time: string
          channel_classification: string
          channel_order?: string | null
          created_at?: string | null
          customer_name?: string | null
          customer_phone_number?: string | null
          duration_seconds?: number | null
          id?: number
          is_order?: string | null
          process_attempts?: number
          processed_at?: string | null
          shop_key: number
          shop_name: string
          stt_text?: string | null
        }
        Update: {
          audio_file_name?: string | null
          call_date?: string
          call_time?: string
          channel_classification?: string
          channel_order?: string | null
          created_at?: string | null
          customer_name?: string | null
          customer_phone_number?: string | null
          duration_seconds?: number | null
          id?: number
          is_order?: string | null
          process_attempts?: number
          processed_at?: string | null
          shop_key?: number
          shop_name?: string
          stt_text?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "server_call_history_shop_key_fkey"
            columns: ["shop_key"]
            isOneToOne: false
            referencedRelation: "member_info"
            referencedColumns: ["id"]
          },
        ]
      }
      setting_info: {
        Row: {
          created_at: string | null
          id: number
          intranet_check_interval: number | null
          intranet_id: string | null
          intranet_password: string | null
          intranet_url: string | null
          notification_phone_number: string | null
          order_hp_1: string
          order_hp_2: string | null
          order_landline_1: string | null
          order_landline_2: string | null
          rpa_auto_submit: string | null
          rpa_enabled: string | null
          rpa_fail_message: string | null
          rpa_login_id: string | null
          rpa_login_password: string | null
          rpa_program_type: string | null
          rpa_program_url: string | null
          rpa_success_message: string | null
          shop_key: number
          shopping_mall_check_interval: number | null
          shopping_mall_id: string | null
          shopping_mall_password: string | null
          shopping_mall_url: string | null
          use_notification: string | null
        }
        Insert: {
          created_at?: string | null
          id?: number
          intranet_check_interval?: number | null
          intranet_id?: string | null
          intranet_password?: string | null
          intranet_url?: string | null
          notification_phone_number?: string | null
          order_hp_1: string
          order_hp_2?: string | null
          order_landline_1?: string | null
          order_landline_2?: string | null
          rpa_auto_submit?: string | null
          rpa_enabled?: string | null
          rpa_fail_message?: string | null
          rpa_login_id?: string | null
          rpa_login_password?: string | null
          rpa_program_type?: string | null
          rpa_program_url?: string | null
          rpa_success_message?: string | null
          shop_key: number
          shopping_mall_check_interval?: number | null
          shopping_mall_id?: string | null
          shopping_mall_password?: string | null
          shopping_mall_url?: string | null
          use_notification?: string | null
        }
        Update: {
          created_at?: string | null
          id?: number
          intranet_check_interval?: number | null
          intranet_id?: string | null
          intranet_password?: string | null
          intranet_url?: string | null
          notification_phone_number?: string | null
          order_hp_1?: string
          order_hp_2?: string | null
          order_landline_1?: string | null
          order_landline_2?: string | null
          rpa_auto_submit?: string | null
          rpa_enabled?: string | null
          rpa_fail_message?: string | null
          rpa_login_id?: string | null
          rpa_login_password?: string | null
          rpa_program_type?: string | null
          rpa_program_url?: string | null
          rpa_success_message?: string | null
          shop_key?: number
          shopping_mall_check_interval?: number | null
          shopping_mall_id?: string | null
          shopping_mall_password?: string | null
          shopping_mall_url?: string | null
          use_notification?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "setting_info_shop_key_fkey"
            columns: ["shop_key"]
            isOneToOne: true
            referencedRelation: "member_info"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      check_username: { Args: { p_username: string }; Returns: boolean }
      clear_remember_token: { Args: { p_user_id: number }; Returns: undefined }
      find_username: {
        Args: { p_phone: string; p_shop_name: string; p_token: string }
        Returns: Json
      }
      get_dashboard: {
        Args: { p_shop_key: number; p_token: string }
        Returns: Json
      }
      get_orders: {
        Args: {
          p_channel?: string
          p_end?: string
          p_shop_key: number
          p_start?: string
          p_status?: string
          p_token: string
        }
        Returns: Json
      }
      get_profile: { Args: { p_username: string }; Returns: Json }
      get_settings: {
        Args: { p_shop_key: number; p_token: string }
        Returns: Json
      }
      issue_remember_token: { Args: { p_user_id: number }; Returns: string }
      request_otp: {
        Args: { p_phone: string; p_purpose: string }
        Returns: string
      }
      requeue_order: {
        Args: { p_order_id: number; p_shop_key: number; p_token: string }
        Returns: Json
      }
      reset_password: {
        Args: {
          p_new_password: string
          p_phone: string
          p_token: string
          p_username: string
        }
        Returns: Json
      }
      save_settings: {
        Args: {
          p_intranet_password?: string
          p_settings: Json
          p_shop_key: number
          p_shopping_mall_password?: string
          p_token: string
        }
        Returns: Json
      }
      signup_member: {
        Args: {
          p_address: string
          p_address_detail: string
          p_email: string
          p_landline: string
          p_mobile: string
          p_password: string
          p_representative_name: string
          p_shop_name: string
          p_username: string
          p_verification_token: string
        }
        Returns: Json
      }
      update_account: {
        Args: {
          p_address: string
          p_address_detail: string
          p_auth_token: string
          p_current_password: string
          p_email: string
          p_landline: string
          p_new_mobile: string
          p_new_password: string
          p_new_phone_token: string
          p_representative_name: string
          p_shop_name: string
          p_username: string
        }
        Returns: Json
      }
      verify_login: {
        Args: { p_password: string; p_username: string }
        Returns: Json
      }
      verify_otp: {
        Args: { p_code: string; p_phone: string; p_purpose: string }
        Returns: Json
      }
      verify_remember_token: {
        Args: { p_token: string; p_user_id: number }
        Returns: Json
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  graphql_public: {
    Enums: {},
  },
  public: {
    Enums: {},
  },
} as const
