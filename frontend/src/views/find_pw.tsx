import { useState } from 'react';
import { supabase } from '../supabase';
import { PhoneVerify } from '../components/PhoneVerify';
import { resetPassword, type OtpRpc } from '../otp/client';
import { otpMessage } from '../otp/messages';

const rpc: OtpRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<OtpRpc>;
const INPUT = 'w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary';

export function FindPwView({ onDone }: { onDone: () => void }) {
  const [username, setUsername] = useState('');
  const [phone, setPhone] = useState('');
  const [token, setToken] = useState<string | null>(null);
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError('');
    if (!pw) { setError('새 비밀번호를 입력해주세요'); return; }
    if (pw !== pw2) { setError('비밀번호가 일치하지 않습니다'); return; }
    if (!token) { setError('핸드폰 인증을 먼저 완료해주세요'); return; }
    setBusy(true);
    const r = await resetPassword(rpc, phone, username.trim(), pw, token);
    setBusy(false);
    if (r.ok) { alert('비밀번호가 재설정되었습니다. 새 비밀번호로 로그인해주세요.'); onDone(); return; }
    setError(r.reason === 'not_found' ? '일치하는 계정이 없습니다' : otpMessage(r.reason));
  };

  return (
    <div className="flex-1 overflow-auto p-10 flex justify-center">
      <div className="w-full max-w-md bg-brand-card border border-brand-border rounded-2xl p-8 space-y-3">
        <div className="font-display font-bold text-lg text-brand-text-primary mb-2">비밀번호 찾기</div>

        <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="아이디" autoFocus disabled={!!token} className={INPUT} />
        <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="핸드폰" disabled={!!token} className={INPUT} />

        {!token ? (
          <PhoneVerify phone={phone} purpose="find_pw" onVerified={setToken} />
        ) : (
          <>
            <input value={pw} onChange={(e) => setPw(e.target.value)} type="password" placeholder="새 비밀번호" className={INPUT} />
            <input value={pw2} onChange={(e) => setPw2(e.target.value)} type="password" placeholder="새 비밀번호 확인" className={INPUT} />
            <button type="button" onClick={submit} disabled={busy} className="w-full py-2.5 rounded-lg bg-brand-primary text-white font-semibold text-sm hover:opacity-90 disabled:opacity-50">
              {busy ? '처리 중…' : '비밀번호 재설정'}
            </button>
          </>
        )}
        {error && <div className="text-brand-error text-xs">{error}</div>}
        <button type="button" onClick={onDone} className="w-full text-xs text-brand-text-muted hover:text-brand-text-secondary">로그인으로 돌아가기</button>
      </div>
    </div>
  );
}
