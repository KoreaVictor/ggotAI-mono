import { useEffect, useState } from 'react';
import { supabase } from '../supabase';
import { useSession } from '../session/SessionContext';
import { PhoneVerify } from '../components/PhoneVerify';
import { getProfile, updateAccount, profileMessage, type ProfileRpc } from '../profile/client';
import { openPostcodeSearch } from '../utils/daumPostcode';

const rpc: ProfileRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<ProfileRpc>;
const INPUT = 'w-full px-4 py-2.5 rounded-lg bg-brand-bg border border-brand-border text-sm text-brand-text-primary outline-none focus:border-brand-primary disabled:opacity-60';

export function MyPageView() {
  const { session, updateShopName } = useSession();
  const username = session?.username ?? '';

  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState('');
  const [authToken, setAuthToken] = useState<string | null>(null);

  const [shopName, setShopName] = useState('');
  const [repName, setRepName] = useState('');
  const [landline, setLandline] = useState('');
  const [email, setEmail] = useState('');
  const [address, setAddress] = useState('');
  const [addressDetail, setAddressDetail] = useState('');
  const [curMobile, setCurMobile] = useState('');

  const [changingPhone, setChangingPhone] = useState(false);
  const [newMobile, setNewMobile] = useState('');
  const [newPhoneToken, setNewPhoneToken] = useState<string | null>(null);

  const [changingPw, setChangingPw] = useState(false);
  const [curPw, setCurPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [newPw2, setNewPw2] = useState('');

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  useEffect(() => {
    let active = true;
    (async () => {
      const r = await getProfile(rpc, username);
      if (!active) return;
      if (!r.ok || !r.profile) { setLoadErr('회원 정보를 불러오지 못했습니다'); setLoading(false); return; }
      const p = r.profile;
      setShopName(p.shop_name ?? ''); setRepName(p.representative_name ?? '');
      setLandline(p.landline_number ?? ''); setEmail(p.email ?? '');
      setAddress(p.address ?? ''); setAddressDetail(p.address_detail ?? '');
      setCurMobile(p.mobile_number ?? '');
      setLoading(false);
    })();
    return () => { active = false; };
  }, [username]);

  const findAddr = async () => {
    try { const r = await openPostcodeSearch(); setAddress(r.address); }
    catch { setError('주소찾기를 열 수 없습니다. 직접 입력해주세요.'); }
  };

  const save = async () => {
    setError(''); setDone('');
    if (!authToken) { setError('핸드폰 인증을 먼저 완료해주세요'); return; }
    if (changingPw) {
      if (!curPw) { setError('현재 비밀번호를 입력해주세요'); return; }
      if (!newPw) { setError('새 비밀번호를 입력해주세요'); return; }
      if (newPw !== newPw2) { setError('새 비밀번호가 일치하지 않습니다'); return; }
    }
    if (changingPhone && !newPhoneToken) { setError('새 핸드폰 인증을 완료해주세요'); return; }
    setBusy(true);
    const r = await updateAccount(rpc, {
      username, authToken,
      shopName, representativeName: repName, landline, email, address, addressDetail,
      newMobile: changingPhone ? newMobile : undefined,
      newPhoneToken: changingPhone ? (newPhoneToken ?? undefined) : undefined,
      currentPassword: changingPw ? curPw : undefined,
      newPassword: changingPw ? newPw : undefined,
    });
    setBusy(false);
    if (!r.ok) {
      setError(profileMessage(r.reason));
      // update_account 는 검증 통과 후에만 토큰을 소비 → 검증 실패(bad_password/new_phone_unverified)면
      // 권한 토큰은 아직 유효하므로 유지. invalid_token(만료/무효)일 때만 재인증 강제.
      if (r.reason === 'invalid_token') setAuthToken(null);
      return;
    }
    updateShopName(r.profile?.shop_name ?? shopName);
    if (changingPhone && r.profile?.mobile_number) {
      setCurMobile(r.profile.mobile_number); setChangingPhone(false); setNewMobile(''); setNewPhoneToken(null);
    }
    if (changingPw) { setChangingPw(false); setCurPw(''); setNewPw(''); setNewPw2(''); }
    setAuthToken(null); // 토큰 단일사용 소비 → 재인증 필요
    setDone('수정되었습니다');
  };

  if (loading) return <div className="flex-1 flex items-center justify-center text-brand-text-muted text-sm">불러오는 중…</div>;
  if (loadErr) return <div className="flex-1 flex items-center justify-center text-brand-error text-sm">{loadErr}</div>;

  return (
    <div className="flex-1 overflow-auto p-10 flex justify-center">
      <div className="w-full max-w-md bg-brand-card border border-brand-border rounded-2xl p-8 space-y-3">
        <div className="font-display font-bold text-lg text-brand-text-primary mb-2">마이페이지</div>

        <input value={username} disabled className={INPUT} />
        <input value={shopName} onChange={(e) => setShopName(e.target.value)} placeholder="꽃집명" className={INPUT} />
        <input value={repName} onChange={(e) => setRepName(e.target.value)} placeholder="대표자명" className={INPUT} />
        <input value={landline} onChange={(e) => setLandline(e.target.value)} placeholder="전화(선택)" className={INPUT} />
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="이메일(선택)" className={INPUT} />
        <div className="flex gap-2">
          <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="주소" className={INPUT} />
          <button type="button" onClick={findAddr} className="shrink-0 px-3 rounded-lg border border-brand-border text-xs text-brand-text-secondary hover:bg-brand-card-hover">주소찾기</button>
        </div>
        <input value={addressDetail} onChange={(e) => setAddressDetail(e.target.value)} placeholder="상세주소(선택)" className={INPUT} />

        <div className="pt-1 text-xs text-brand-text-muted">등록된 핸드폰: {curMobile || '-'}</div>
        {!authToken
          ? <PhoneVerify phone={curMobile} purpose="update_profile" onVerified={setAuthToken} />
          : <div className="text-xs text-brand-success">✓ 본인 인증됨</div>}

        <label className="flex items-center gap-2 text-xs text-brand-text-secondary pt-1">
          <input type="checkbox" checked={changingPhone} onChange={(e) => { setChangingPhone(e.target.checked); setNewPhoneToken(null); setNewMobile(''); }} />
          핸드폰 번호 변경
        </label>
        {changingPhone && (
          <>
            <input value={newMobile} onChange={(e) => setNewMobile(e.target.value)} placeholder="새 핸드폰" disabled={!!newPhoneToken} className={INPUT} />
            {!newPhoneToken
              ? <PhoneVerify phone={newMobile} purpose="update_profile" onVerified={setNewPhoneToken} />
              : <div className="text-xs text-brand-success">✓ 새 핸드폰 인증됨</div>}
          </>
        )}

        <label className="flex items-center gap-2 text-xs text-brand-text-secondary pt-1">
          <input type="checkbox" checked={changingPw} onChange={(e) => setChangingPw(e.target.checked)} />
          비밀번호 변경
        </label>
        {changingPw && (
          <>
            <input value={curPw} onChange={(e) => setCurPw(e.target.value)} type="password" placeholder="현재 비밀번호" className={INPUT} />
            <input value={newPw} onChange={(e) => setNewPw(e.target.value)} type="password" placeholder="새 비밀번호" className={INPUT} />
            <input value={newPw2} onChange={(e) => setNewPw2(e.target.value)} type="password" placeholder="새 비밀번호 확인" className={INPUT} />
          </>
        )}

        {error && <div className="text-brand-error text-xs">{error}</div>}
        {done && <div className="text-brand-success text-xs">{done}</div>}
        <button type="button" onClick={save} disabled={busy || !authToken} className="w-full py-2.5 rounded-lg bg-brand-primary text-white font-semibold text-sm hover:opacity-90 disabled:opacity-50">
          {busy ? '저장 중…' : '저장'}
        </button>
      </div>
    </div>
  );
}
