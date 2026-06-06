import { useState, useEffect, useRef } from 'react';
import { supabase } from '../supabase';
import { sendOtp, verifyOtp, type Purpose, type OtpRpc, type FunctionsClient } from '../otp/client';
import { otpMessage } from '../otp/messages';

// supabase.rpc / supabase.functions 를 래퍼 계약으로 단일지점 캐스트 (B1 authenticate 패턴)
const rpc: OtpRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<OtpRpc>;
const fns = supabase.functions as unknown as FunctionsClient;

const CODE_TTL = 180; // 초 (코드 만료 3분)

export function PhoneVerify({
  phone, purpose, onVerified,
}: {
  phone: string;
  purpose: Purpose;
  onVerified: (token: string) => void;
}) {
  const [stage, setStage] = useState<'idle' | 'sent' | 'verified'>('idle');
  const [code, setCode] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const startCountdown = () => {
    setLeft(CODE_TTL);
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(() => {
      setLeft((s) => {
        if (s <= 1) { if (timer.current) clearInterval(timer.current); return 0; }
        return s - 1;
      });
    }, 1000);
  };

  const request = async () => {
    if (!phone.trim()) { setMsg('핸드폰 번호를 입력해주세요'); return; }
    setBusy(true); setMsg('');
    const r = await sendOtp(fns, phone, purpose);
    setBusy(false);
    if (!r.ok) { setMsg(otpMessage(r.reason)); return; }
    setStage('sent'); setCode(''); startCountdown();
    setMsg('인증번호를 발송했습니다');
  };

  const confirm = async () => {
    if (!code.trim()) { setMsg('인증번호를 입력해주세요'); return; }
    setBusy(true); setMsg('');
    const r = await verifyOtp(rpc, phone, purpose, code.trim());
    setBusy(false);
    if (!r.ok || !r.token) { setMsg(otpMessage(r.reason)); return; }
    if (timer.current) clearInterval(timer.current);
    setStage('verified'); setMsg('');
    onVerified(r.token);
  };

  const mmss = `${String(Math.floor(left / 60)).padStart(1, '0')}:${String(left % 60).padStart(2, '0')}`;

  if (stage === 'verified') {
    return <div className="text-xs text-brand-success">✓ 인증되었습니다</div>;
  }

  return (
    <div className="space-y-2">
      <button
        type="button" onClick={request} disabled={busy}
        className="shrink-0 px-3 py-2 rounded-lg border border-brand-border text-xs text-brand-text-secondary hover:bg-brand-card-hover disabled:opacity-50"
      >
        {stage === 'sent' ? '재전송' : '인증요청'}
      </button>
      {stage === 'sent' && (
        <div className="flex gap-2 items-center">
          <input
            value={code} onChange={(e) => setCode(e.target.value)} placeholder="인증번호 6자리"
            inputMode="numeric" maxLength={6}
            className="flex-1 px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary"
          />
          {left > 0 && <span className="text-xs text-brand-text-muted shrink-0">{mmss}</span>}
          <button
            type="button" onClick={confirm} disabled={busy}
            className="shrink-0 px-3 py-2.5 rounded-lg bg-brand-primary text-white text-xs font-semibold hover:opacity-90 disabled:opacity-50"
          >확인</button>
        </div>
      )}
      {msg && <div className="text-xs text-brand-text-muted">{msg}</div>}
    </div>
  );
}
