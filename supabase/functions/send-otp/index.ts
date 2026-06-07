import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';
import { corsHeaders } from '../_shared/cors.ts';
import { getProvider } from './provider.ts';

const VALID_PURPOSES = ['signup', 'find_id', 'find_pw', 'update_profile'];

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    const { phone, purpose } = await req.json();
    const normPhone = String(phone ?? '').replace(/\D/g, '');
    if (normPhone.length < 10 || !VALID_PURPOSES.includes(purpose)) {
      return json({ success: false, reason: 'bad_request' }, 400);
    }

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
    );
    const { data: code, error } = await supabase.rpc('request_otp', {
      p_phone: normPhone,
      p_purpose: purpose,
    });
    if (error) {
      const isRate = /RATE_LIMIT/.test(error.message);
      return json({ success: false, reason: isRate ? 'rate_limit' : 'error' }, isRate ? 429 : 400);
    }

    // 코드는 응답에 절대 싣지 않음 — SMS 로만 전달
    await getProvider().send(normPhone, `[꽃아이] 인증번호 ${code} (3분 내 입력)`);
    return json({ success: true }, 200);
  } catch (_e) {
    return json({ success: false, reason: 'send_failed' }, 502);
  }
});
