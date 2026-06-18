import React, { useState, useEffect } from 'react';
import { supabase } from '../supabase';
import { useSession } from '../session/SessionContext';
import { getSettings, saveSettings, type SettingsData } from '../settings/client';
import type { DashRpc } from '../dashboard/client';
import { encryptPassword } from '../utils/crypto';
import { Save, Shield, Bell, Globe, Key, AlertTriangle, CheckCircle2, Lock } from 'lucide-react';

const rpc: DashRpc = (fn, args) => supabase.rpc(fn, args) as unknown as ReturnType<DashRpc>;

const DEFAULTS: SettingsData = {
  use_notification: 'Y',
  notification_phone_number: '',
  rpa_success_message: '{channel} 주문 {count}건 꽃가게 관리 프로그램에 입력 완료했습니다.',
  rpa_manual_message: '[ggotAI] {channel} 주문 {count}건 접수 — 관리 프로그램에 직접 입력해 주세요.',
  rpa_fail_message: '[ggotAI 경고] {channel} 주문 자동 입력 실패! 수동 확인 바랍니다.',
  order_hp_1: '',
  order_hp_2: '',
  order_landline_1: '',
  order_landline_2: '',
  shopping_mall_url: '',
  shopping_mall_id: '',
  intranet_url: '',
  intranet_id: '',
  shopping_mall_check_interval: 10,
  intranet_check_interval: 30,
  has_shopping_mall_password: false,
  has_intranet_password: false,
  rpa_program_type: '',
  rpa_program_url: '',
  rpa_login_id: '',
  rpa_enabled: 'N',
  rpa_auto_submit: 'Y',
  has_rpa_login_password: false,
};

function PwBadge({ set }: { set: boolean }) {
  return set ? (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-brand-success">
      <Lock className="h-3 w-3" /> 설정됨
    </span>
  ) : (
    <span className="text-[10px] font-bold text-brand-text-muted">미설정</span>
  );
}

export function SettingsView() {
  const { session, readToken } = useSession();
  const shopKey = session?.shopKey ?? 0;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const [settings, setSettings] = useState<SettingsData>(DEFAULTS);
  const [shoppingMallPassword, setShoppingMallPassword] = useState('');
  const [intranetPassword, setIntranetPassword] = useState('');
  const [rpaLoginPassword, setRpaLoginPassword] = useState('');

  useEffect(() => {
    let active = true;
    (async () => {
      if (!shopKey || !readToken) { setErrorMsg('세션이 만료되었습니다. 다시 로그인해주세요.'); setLoading(false); return; }
      setLoading(true);
      const r = await getSettings(rpc, shopKey, readToken);
      if (!active) return;
      if (!r.ok) {
        setErrorMsg(r.reason === 'unauthorized' ? '세션이 만료되었습니다. 다시 로그인해주세요.' : '설정을 불러오지 못했습니다.');
        setLoading(false);
        return;
      }
      if (r.settings) {
        setSettings({
          ...DEFAULTS,
          ...r.settings,
          notification_phone_number: r.settings.notification_phone_number ?? '',
          order_hp_2: r.settings.order_hp_2 ?? '',
          order_landline_1: r.settings.order_landline_1 ?? '',
          order_landline_2: r.settings.order_landline_2 ?? '',
          shopping_mall_url: r.settings.shopping_mall_url ?? '',
          shopping_mall_id: r.settings.shopping_mall_id ?? '',
          intranet_url: r.settings.intranet_url ?? '',
          intranet_id: r.settings.intranet_id ?? '',
          rpa_program_type: r.settings.rpa_program_type ?? '',
          rpa_program_url: r.settings.rpa_program_url ?? '',
          rpa_login_id: r.settings.rpa_login_id ?? '',
          rpa_enabled: r.settings.rpa_enabled ?? 'N',
          rpa_auto_submit: r.settings.rpa_auto_submit ?? 'Y',
        });
      }
      setLoading(false);
    })();
    return () => { active = false; };
  }, [shopKey, readToken]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setSettings((prev) => ({ ...prev, [name]: value }));
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSuccessMsg('');
    setErrorMsg('');

    const smPw = shoppingMallPassword.trim() ? encryptPassword(shoppingMallPassword.trim()) : null;
    const itPw = intranetPassword.trim() ? encryptPassword(intranetPassword.trim()) : null;
    const rpaPw = rpaLoginPassword.trim() ? encryptPassword(rpaLoginPassword.trim()) : null;

    const r = await saveSettings(rpc, shopKey, readToken ?? '', {
      ...settings,
      shopping_mall_check_interval: Number(settings.shopping_mall_check_interval),
      intranet_check_interval: Number(settings.intranet_check_interval),
    }, smPw, itPw, rpaPw);

    setSaving(false);
    if (!r.ok) {
      setErrorMsg(
        r.reason === 'unauthorized' ? '세션이 만료되었습니다. 다시 로그인해주세요.'
        : r.reason === 'order_hp_1_required' ? '주문 수신 핸드폰 번호 1은 필수입니다.'
        : '설정 저장 중 오류가 발생했습니다.');
      return;
    }
    setSuccessMsg('주문 수집 환경설정이 안전하게 저장되었습니다!');
    setSettings((prev) => ({
      ...prev,
      has_shopping_mall_password: prev.has_shopping_mall_password || smPw !== null,
      has_intranet_password: prev.has_intranet_password || itPw !== null,
      has_rpa_login_password: prev.has_rpa_login_password || rpaPw !== null,
    }));
    setShoppingMallPassword('');
    setIntranetPassword('');
    setRpaLoginPassword('');
  };

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[500px]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-brand-primary"></div>
        <p className="mt-4 text-brand-text-secondary text-sm">설정 정보를 로딩하고 있습니다...</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8 animate-fade-in-up">
      <div className="mb-8">
        <h1 className="text-3xl font-display font-bold text-brand-text-primary tracking-tight">수집 환경설정</h1>
        <p className="text-brand-text-secondary text-sm mt-1">다중 채널 수집 간격, 기기 정보, 연동 계정을 개인화하여 관리합니다.</p>
      </div>

      {successMsg && (
        <div className="mb-6 flex items-center gap-3 p-4 bg-brand-success/15 border border-brand-success/30 rounded-lg text-brand-success text-sm">
          <CheckCircle2 className="h-5 w-5 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}
      {errorMsg && (
        <div className="mb-6 flex items-center gap-3 p-4 bg-brand-error/15 border border-brand-error/30 rounded-lg text-brand-error text-sm">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-8 max-w-5xl">

        {/* 섹션 1: 수신 기기 */}
        <div className="glass-panel rounded-xl p-6 shadow-xl space-y-6">
          <div className="flex items-center gap-2 border-b border-brand-border pb-3">
            <Shield className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-semibold text-brand-text-primary">수신 기기 식별 설정</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 핸드폰 번호 1 (필수)</label>
              <input type="text" name="order_hp_1" required placeholder="예: 010-1234-5678"
                value={settings.order_hp_1} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 핸드폰 번호 2</label>
              <input type="text" name="order_hp_2" placeholder="예: 010-9876-5432"
                value={settings.order_hp_2 ?? ''} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 일반전화 번호 1</label>
              <input type="text" name="order_landline_1" placeholder="예: 02-123-4567"
                value={settings.order_landline_1 ?? ''} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 일반전화 번호 2</label>
              <input type="text" name="order_landline_2" placeholder="예: 02-987-6543"
                value={settings.order_landline_2 ?? ''} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
            </div>
          </div>
        </div>

        {/* 섹션 2: 외부 채널 연동 */}
        <div className="glass-panel rounded-xl p-6 shadow-xl space-y-6">
          <div className="flex items-center gap-2 border-b border-brand-border pb-3">
            <Globe className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-semibold text-brand-text-primary">온라인 채널 연동 설정</h2>
          </div>
          <div className="space-y-6">
            {/* 쇼핑몰 */}
            <div className="border-b border-brand-border/40 pb-6 space-y-4">
              <h3 className="text-sm font-semibold text-brand-primary flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-primary"></span>꽃가게 공식 쇼핑몰
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-3">
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">쇼핑몰 관리자 로그인 주소 (URL)</label>
                  <input type="url" name="shopping_mall_url" placeholder="https://admin.myshop.com"
                    value={settings.shopping_mall_url ?? ''} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">로그인 ID</label>
                  <input type="text" name="shopping_mall_id" placeholder="쇼핑몰 아이디"
                    value={settings.shopping_mall_id ?? ''} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Key className="h-3.5 w-3.5 text-brand-text-muted" />새 비밀번호
                    <PwBadge set={settings.has_shopping_mall_password} />
                  </label>
                  <input type="password" placeholder="수정할 때만 입력"
                    value={shoppingMallPassword} onChange={(e) => setShoppingMallPassword(e.target.value)}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 확인 점검 간격 (분)</label>
                  <input type="number" name="shopping_mall_check_interval" min="1" max="120"
                    value={settings.shopping_mall_check_interval} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
              </div>
            </div>
            {/* 인트라넷 */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-brand-primary flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-primary"></span>화원 연합 인트라넷
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-3">
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">인트라넷 로그인 주소 (URL)</label>
                  <input type="url" name="intranet_url" placeholder="https://intranet.flower-association.com"
                    value={settings.intranet_url ?? ''} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">로그인 ID</label>
                  <input type="text" name="intranet_id" placeholder="인트라넷 아이디"
                    value={settings.intranet_id ?? ''} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Key className="h-3.5 w-3.5 text-brand-text-muted" />새 비밀번호
                    <PwBadge set={settings.has_intranet_password} />
                  </label>
                  <input type="password" placeholder="수정할 때만 입력"
                    value={intranetPassword} onChange={(e) => setIntranetPassword(e.target.value)}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 확인 점검 간격 (분)</label>
                  <input type="number" name="intranet_check_interval" min="1" max="120"
                    value={settings.intranet_check_interval} onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 섹션 3: 관리 프로그램 (자동입력) */}
        <div className="glass-panel rounded-xl p-6 shadow-xl space-y-6">
          <div className="flex items-center gap-2 border-b border-brand-border pb-3">
            <Key className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-semibold text-brand-text-primary">관리 프로그램 (자동입력)</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">프로그램 종류</label>
              <select name="rpa_program_type" value={settings.rpa_program_type} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none">
                <option value="">선택 안 함</option>
                <option value="flowernt">FlowerNT</option>
                <option value="roseweb">Roseweb</option>
                <option value="etc">기타</option>
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">웹 주소</label>
              <input type="url" name="rpa_program_url" placeholder="https://www.flowernt.com"
                value={settings.rpa_program_url ?? ''} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">아이디</label>
              <input type="text" name="rpa_login_id" placeholder="로그인 아이디"
                value={settings.rpa_login_id ?? ''} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
            </div>
            <div>
              <label className="text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <Key className="h-3.5 w-3.5 text-brand-text-muted" />새 비밀번호
                <PwBadge set={settings.has_rpa_login_password} />
              </label>
              <input type="password" placeholder="수정할 때만 입력"
                value={rpaLoginPassword} onChange={(e) => setRpaLoginPassword(e.target.value)}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">RPA 사용</label>
              <select name="rpa_enabled" value={settings.rpa_enabled} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none">
                <option value="Y">사용</option>
                <option value="N">미사용</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">자동 등록</label>
              <select name="rpa_auto_submit" value={settings.rpa_auto_submit} onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none">
                <option value="Y">등록까지 자동</option>
                <option value="N">채우기만</option>
              </select>
            </div>
          </div>
        </div>

        {/* 섹션 4: 알림 */}
        <div className="glass-panel rounded-xl p-6 shadow-xl space-y-6">
          <div className="flex items-center gap-2 border-b border-brand-border pb-3">
            <Bell className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-semibold text-brand-text-primary">개인화 알림 보고 및 피드백 설정</h2>
          </div>
          <div className="space-y-6">
            <div className="flex items-center gap-4 bg-brand-bg/30 p-4 border border-brand-border/60 rounded-lg">
              <label className="text-sm font-semibold text-brand-text-primary">실시간 수집/RPA 처리 알림 수신 여부</label>
              <select name="use_notification" value={settings.use_notification} onChange={handleInputChange}
                className="bg-brand-card border border-brand-border text-brand-text-primary text-sm rounded-lg px-3 py-1.5 transition outline-none">
                <option value="Y">🟢 사용함 (권장)</option>
                <option value="N">🔴 사용 안 함</option>
              </select>
            </div>
            {settings.use_notification === 'Y' && (
              <div className="grid grid-cols-1 gap-6">
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">알림 보고 수신 사장님 핸드폰 번호</label>
                  <input type="text" name="notification_phone_number" placeholder="비워둘 시 꽃가게 대표 번호로 발송"
                    value={settings.notification_phone_number ?? ''} onChange={handleInputChange}
                    className="w-full md:w-1/2 bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none" />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div>
                    <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">RPA 전산 입력 성공 보고 문자 템플릿</label>
                    <textarea name="rpa_success_message" rows={3} value={settings.rpa_success_message} onChange={handleInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none resize-y" />
                    <span className="text-[10px] text-brand-text-muted mt-1.5 block">※ 변수 사용: `{'{channel}'}` (수집 채널명 치환), `{'{count}'}` (주문 개수 치환)</span>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">RPA 수동입력 필요 안내 문자 템플릿</label>
                    <textarea name="rpa_manual_message" rows={3} value={settings.rpa_manual_message} onChange={handleInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none resize-y" />
                    <span className="text-[10px] text-brand-text-muted mt-1.5 block">※ 관리 프로그램 미구동 시 백업만 생성됨(수동입력 필요). 변수: `{'{channel}'}`, `{'{count}'}`</span>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">RPA 전산 입력 실패 경고 문자 템플릿</label>
                    <textarea name="rpa_fail_message" rows={3} value={settings.rpa_fail_message} onChange={handleInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none resize-y" />
                    <span className="text-[10px] text-brand-text-muted mt-1.5 block">※ 변수 사용: `{'{channel}'}` (수집 채널명 치환)</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end pt-4">
          <button type="submit" disabled={saving}
            className="flex items-center gap-2 px-6 py-3 bg-brand-primary hover:bg-brand-primary-hover disabled:bg-brand-text-muted text-white text-sm font-semibold rounded-lg shadow-lg hover:shadow-brand-primary/20 transition cursor-pointer">
            {saving ? <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-white"></div> : <Save className="h-4 w-4" />}
            <span>설정 정보 저장하기</span>
          </button>
        </div>
      </form>
    </div>
  );
}
