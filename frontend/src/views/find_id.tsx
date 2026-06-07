import { useState } from 'react';
import { supabase } from '../supabase';
import { PhoneVerify } from '../components/PhoneVerify';
import { findUsername, type OtpRpc } from '../otp/client';
import { otpMessage } from '../otp/messages';

const rpc: OtpRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<OtpRpc>;
const INPUT = 'w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary';

export function FindIdView({ onDone }: { onDone: () => void }) {
  const [shopName, setShopName] = useState('');
  const [phone, setPhone] = useState('');
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState('');

  const onVerified = async (token: string) => {
    setError(''); setResult(null);
    const r = await findUsername(rpc, phone, shopName.trim(), token);
    if (r.ok && r.username) { setResult(r.username); return; }
    setError(r.reason === 'not_found' ? '일치하는 계정이 없습니다' : otpMessage(r.reason));
  };

  return (
    <div className="flex-1 overflow-auto p-10 flex justify-center">
      <div className="w-full max-w-md bg-brand-card border border-brand-border rounded-2xl p-8 space-y-3">
        <div className="font-display font-bold text-lg text-brand-text-primary mb-2">아이디 찾기</div>

        {result === null ? (
          <>
            <input value={shopName} onChange={(e) => setShopName(e.target.value)} placeholder="꽃집명" autoFocus className={INPUT} />
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="핸드폰" className={INPUT} />
            <PhoneVerify phone={phone} purpose="find_id" onVerified={onVerified} />
            {error && <div className="text-brand-error text-xs">{error}</div>}
          </>
        ) : (
          <div className="text-sm text-brand-text-primary py-4">
            회원님의 아이디는 <span className="font-bold text-brand-primary">{result}</span> 입니다.
          </div>
        )}

        <button type="button" onClick={onDone} className="w-full text-xs text-brand-text-muted hover:text-brand-text-secondary">로그인으로 돌아가기</button>
      </div>
    </div>
  );
}
