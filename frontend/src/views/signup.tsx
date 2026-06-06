import React, { useState } from 'react';
import { supabase } from '../supabase';
import { validateSignup, type SignupForm } from '../signup/validate';
import { openPostcodeSearch } from '../utils/daumPostcode';

const EMPTY: SignupForm = {
  username: '', password: '', passwordConfirm: '', shopName: '',
  representativeName: '', mobile: '', email: '', landline: '', address: '', addressDetail: '',
};

const INPUT = 'w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary';

export function SignupView({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState<SignupForm>(EMPTY);
  const [dupMsg, setDupMsg] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const set = (k: keyof SignupForm) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF((p) => ({ ...p, [k]: e.target.value }));

  // PRD 6-1: 엔터 시 다음 입력으로 포커스 이동
  const focusNext = (e: React.KeyboardEvent) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const form = (e.target as HTMLElement).closest('form');
    if (!form) return;
    const fields = Array.from(form.querySelectorAll<HTMLInputElement>('input:not([type=checkbox])'));
    const i = fields.indexOf(e.target as HTMLInputElement);
    if (i >= 0 && i < fields.length - 1) fields[i + 1].focus();
  };

  const checkUsername = async () => {
    setDupMsg('');
    if (!f.username.trim()) { setDupMsg('아이디를 입력해주세요'); return; }
    const { data, error: e } = await supabase.rpc('check_username', { p_username: f.username.trim() });
    if (e) { setDupMsg('확인 중 오류가 발생했습니다'); return; }
    setDupMsg(data ? '이미 사용 중인 아이디입니다' : '사용 가능한 아이디입니다');
  };

  const findAddress = async () => {
    try {
      const r = await openPostcodeSearch();
      setF((p) => ({ ...p, address: r.address }));
    } catch {
      setError('주소찾기를 열 수 없습니다. 주소를 직접 입력해주세요.');
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    const v = validateSignup(f);
    if (v) { setError(v); return; }
    setBusy(true);
    const { error: e2 } = await supabase.rpc('signup_member', {
      p_username: f.username.trim(), p_password: f.password, p_shop_name: f.shopName.trim(),
      p_representative_name: f.representativeName.trim(), p_landline: f.landline || null,
      p_mobile: f.mobile.trim(), p_email: f.email || null, p_address: f.address || null,
      p_address_detail: f.addressDetail || null,
    });
    setBusy(false);
    if (e2) {
      setError(/USERNAME_TAKEN/.test(e2.message) ? '이미 사용 중인 아이디입니다' : '회원가입 중 오류가 발생했습니다');
      return;
    }
    alert('회원가입이 완료되었습니다. 관리자 승인 후 로그인할 수 있습니다.');
    onDone();
  };

  return (
    <div className="flex-1 overflow-auto p-10 flex justify-center">
      <form onSubmit={submit} className="w-full max-w-md bg-brand-card border border-brand-border rounded-2xl p-8 space-y-3">
        <div className="font-display font-bold text-lg text-brand-text-primary mb-2">회원가입</div>

        <div className="flex gap-2">
          <input value={f.username} onChange={(e) => { set('username')(e); setDupMsg(''); }} onKeyDown={focusNext} placeholder="아이디" autoFocus className={INPUT} />
          <button type="button" onClick={checkUsername} className="shrink-0 px-3 rounded-lg border border-brand-border text-xs text-brand-text-secondary hover:bg-brand-card-hover">중복확인</button>
        </div>
        {dupMsg && <div className="text-xs text-brand-text-muted">{dupMsg}</div>}

        <input value={f.password} onChange={set('password')} onKeyDown={focusNext} type="password" placeholder="비밀번호" className={INPUT} />
        <input value={f.passwordConfirm} onChange={set('passwordConfirm')} onKeyDown={focusNext} type="password" placeholder="비밀번호 확인" className={INPUT} />
        <input value={f.shopName} onChange={set('shopName')} onKeyDown={focusNext} placeholder="꽃집명" className={INPUT} />
        <input value={f.representativeName} onChange={set('representativeName')} onKeyDown={focusNext} placeholder="대표자명" className={INPUT} />
        <input value={f.landline} onChange={set('landline')} onKeyDown={focusNext} placeholder="전화(선택)" className={INPUT} />

        <div className="flex gap-2">
          <input value={f.mobile} onChange={set('mobile')} onKeyDown={focusNext} placeholder="핸드폰" className={INPUT} />
          <button type="button" disabled title="다음 단계(B2)에서 제공됩니다" className="shrink-0 px-3 rounded-lg border border-brand-border text-xs text-brand-text-muted opacity-50 cursor-not-allowed">인증</button>
        </div>

        <input value={f.email} onChange={set('email')} onKeyDown={focusNext} placeholder="이메일(선택)" className={INPUT} />

        <div className="flex gap-2">
          <input value={f.address} onChange={set('address')} onKeyDown={focusNext} placeholder="주소" className={INPUT} />
          <button type="button" onClick={findAddress} className="shrink-0 px-3 rounded-lg border border-brand-border text-xs text-brand-text-secondary hover:bg-brand-card-hover">주소찾기</button>
        </div>
        <input value={f.addressDetail} onChange={set('addressDetail')} onKeyDown={focusNext} placeholder="상세주소(선택)" className={INPUT} />

        {error && <div className="text-brand-error text-xs">{error}</div>}
        <button type="submit" disabled={busy} className="w-full py-2.5 rounded-lg bg-brand-primary text-white font-semibold text-sm hover:opacity-90 transition disabled:opacity-50">
          {busy ? '처리 중…' : '회원가입'}
        </button>
        <button type="button" onClick={onDone} className="w-full text-xs text-brand-text-muted hover:text-brand-text-secondary">로그인으로 돌아가기</button>
      </form>
    </div>
  );
}
