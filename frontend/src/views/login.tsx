import React, { useState } from 'react';
import { useSession } from '../session/SessionContext';

export function LoginView({ onFindId, onFindPw }: { onFindId: () => void; onFindPw: () => void }) {
  const { login } = useSession();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [autoLogin, setAutoLogin] = useState(false); // 표시만(영구화는 B)
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // PRD 6-1: 엔터 시 다음 입력으로 포커스 이동
  const focusNext = (e: React.KeyboardEvent) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const form = (e.target as HTMLElement).closest('form');
    if (!form) return;
    const fields = Array.from(form.querySelectorAll('input'));
    const i = fields.indexOf(e.target as HTMLInputElement);
    if (i >= 0 && i < fields.length - 1) fields[i + 1].focus();
    else (form.querySelector('button[type=submit]') as HTMLButtonElement | null)?.focus();
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    const r = await login(username.trim(), password);
    setBusy(false);
    if (!r.ok) setError(r.error ?? '로그인에 실패했습니다');
  };

  return (
    <div className="flex-1 flex items-center justify-center p-10">
      <form onSubmit={submit} className="w-full max-w-sm bg-brand-card border border-brand-border rounded-2xl p-8 space-y-4">
        <div className="font-display font-bold text-lg text-brand-text-primary mb-2">로그인</div>
        <input
          value={username} onChange={(e) => setUsername(e.target.value)} onKeyDown={focusNext}
          placeholder="아이디" autoFocus
          className="w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary"
        />
        <input
          value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={focusNext}
          type="password" placeholder="비밀번호"
          className="w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary"
        />
        <label className="flex items-center gap-2 text-xs text-brand-text-secondary">
          <input type="checkbox" checked={autoLogin} onChange={(e) => setAutoLogin(e.target.checked)} />
          자동로그인
        </label>
        {error && <div className="text-brand-error text-xs">{error}</div>}
        <button
          type="submit" disabled={busy}
          className="w-full py-2.5 rounded-lg bg-brand-primary text-white font-semibold text-sm hover:opacity-90 transition disabled:opacity-50"
        >
          {busy ? '확인 중…' : '로그인'}
        </button>
        <div className="flex justify-center gap-4 text-xs text-brand-text-muted pt-1">
          <button type="button" onClick={onFindId} className="hover:text-brand-text-secondary">아이디 찾기</button>
          <button type="button" onClick={onFindPw} className="hover:text-brand-text-secondary">비밀번호 찾기</button>
        </div>
      </form>
    </div>
  );
}
