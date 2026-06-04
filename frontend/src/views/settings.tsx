import React, { useState, useEffect } from 'react';
import { supabase } from '../supabase';
import { encryptPassword } from '../utils/crypto';
import { Save, Shield, Bell, Globe, Key, AlertTriangle, CheckCircle2 } from 'lucide-react';

interface SettingData {
  id?: number;
  shop_key: number;
  use_notification: string;
  notification_phone_number: string | null;
  rpa_success_message: string;
  rpa_fail_message: string;
  order_hp_1: string;
  order_hp_2: string | null;
  order_landline_1: string | null;
  order_landline_2: string | null;
  shopping_mall_url: string | null;
  shopping_mall_id: string | null;
  intranet_url: string | null;
  intranet_id: string | null;
  shopping_mall_check_interval: number;
  intranet_check_interval: number;
}

export function SettingsView() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // 1:1 매핑할 고유 shop_key (기본값 1로 셋업)
  const defaultShopKey = 1;

  // DB 상태 저장
  const [settings, setSettings] = useState<SettingData>({
    shop_key: defaultShopKey,
    use_notification: 'Y',
    notification_phone_number: '',
    rpa_success_message: '{channel} 주문 {count}건 꽃가게 관리 프로그램에 입력 완료했습니다.',
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
  });

  // 비밀번호 입력 상태 (보안 상 DB의 기존 값은 암호화되어 로드되므로, 신규 비밀번호 수정 시에만 암호화 저장 처리)
  const [shoppingMallPassword, setShoppingMallPassword] = useState('');
  const [intranetPassword, setIntranetPassword] = useState('');

  // 설정 로드
  useEffect(() => {
    async function loadSettings() {
      try {
        setLoading(true);
        const { data, error } = await supabase
          .from('setting_info')
          .select('*')
          .eq('shop_key', defaultShopKey)
          .single();

        if (error) {
          if (error.code === 'PGRST116') {
            console.log('설정 데이터가 없습니다. 기본 설정을 사용합니다.');
          } else {
            throw error;
          }
        } else if (data) {
          setSettings({
            ...data,
            notification_phone_number: data.notification_phone_number || '',
            order_hp_2: data.order_hp_2 || '',
            order_landline_1: data.order_landline_1 || '',
            order_landline_2: data.order_landline_2 || '',
            shopping_mall_url: data.shopping_mall_url || '',
            shopping_mall_id: data.shopping_mall_id || '',
            intranet_url: data.intranet_url || '',
            intranet_id: data.intranet_id || '',
          });
        }
      } catch (err: any) {
        setErrorMsg('설정을 불러오는 중 오류가 발생했습니다: ' + err.message);
      } finally {
        setLoading(false);
      }
    }

    loadSettings();
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setSettings((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  // 설정 저장
  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSuccessMsg('');
    setErrorMsg('');

    try {
      // 1. 저장할 데이터 객체 빌드
      const updateData: any = {
        shop_key: settings.shop_key,
        use_notification: settings.use_notification,
        notification_phone_number: settings.notification_phone_number || null,
        rpa_success_message: settings.rpa_success_message,
        rpa_fail_message: settings.rpa_fail_message,
        order_hp_1: settings.order_hp_1,
        order_hp_2: settings.order_hp_2 || null,
        order_landline_1: settings.order_landline_1 || null,
        order_landline_2: settings.order_landline_2 || null,
        shopping_mall_url: settings.shopping_mall_url || null,
        shopping_mall_id: settings.shopping_mall_id || null,
        intranet_url: settings.intranet_url || null,
        intranet_id: settings.intranet_id || null,
        shopping_mall_check_interval: Number(settings.shopping_mall_check_interval),
        intranet_check_interval: Number(settings.intranet_check_interval),
      };

      // 2. 비밀번호를 새로 작성한 경우에만 암호화하여 업서트 데이터에 주입
      if (shoppingMallPassword.trim()) {
        updateData.shopping_mall_password = encryptPassword(shoppingMallPassword.trim());
      }
      if (intranetPassword.trim()) {
        updateData.intranet_password = encryptPassword(intranetPassword.trim());
      }

      // 3. Supabase upsert 실행
      const { error } = await supabase
        .from('setting_info')
        .upsert(updateData, { onConflict: 'shop_key' });

      if (error) throw error;

      setSuccessMsg('주문 수집 환경설정이 안전하게 저장되었습니다!');
      // 입력 폼 비밀번호 비우기 (보안)
      setShoppingMallPassword('');
      setIntranetPassword('');
    } catch (err: any) {
      console.error(err);
      setErrorMsg('설정 저장 중 오류가 발생했습니다: ' + err.message);
    } finally {
      setSaving(false);
    }
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
      {/* 타이틀 헤더 */}
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
        
        {/* 섹션 1: 주문 수신 기기 설정 */}
        <div className="glass-panel rounded-xl p-6 shadow-xl space-y-6">
          <div className="flex items-center gap-2 border-b border-brand-border pb-3">
            <Shield className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-semibold text-brand-text-primary">수신 기기 식별 설정</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 핸드폰 번호 1 (필수)</label>
              <input
                type="text"
                name="order_hp_1"
                required
                placeholder="예: 010-1234-5678"
                value={settings.order_hp_1}
                onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 핸드폰 번호 2</label>
              <input
                type="text"
                name="order_hp_2"
                placeholder="예: 010-9876-5432"
                value={settings.order_hp_2 || ''}
                onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 일반전화 번호 1</label>
              <input
                type="text"
                name="order_landline_1"
                placeholder="예: 02-123-4567"
                value={settings.order_landline_1 || ''}
                onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 수신 일반전화 번호 2</label>
              <input
                type="text"
                name="order_landline_2"
                placeholder="예: 02-987-6543"
                value={settings.order_landline_2 || ''}
                onChange={handleInputChange}
                className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
              />
            </div>
          </div>
        </div>

        {/* 섹션 2: 외부 채널 자동 연동 설정 (쇼핑몰 및 인트라넷) */}
        <div className="glass-panel rounded-xl p-6 shadow-xl space-y-6">
          <div className="flex items-center gap-2 border-b border-brand-border pb-3">
            <Globe className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-semibold text-brand-text-primary">온라인 채널 연동 설정</h2>
          </div>
          
          <div className="space-y-6">
            {/* 쇼핑몰 설정 */}
            <div className="border-b border-brand-border/40 pb-6 space-y-4">
              <h3 className="text-sm font-semibold text-brand-primary flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-primary"></span>
                꽃가게 공식 쇼핑몰
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-3">
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">쇼핑몰 관리자 로그인 주소 (URL)</label>
                  <input
                    type="url"
                    name="shopping_mall_url"
                    placeholder="https://admin.myshop.com"
                    value={settings.shopping_mall_url || ''}
                    onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">로그인 ID</label>
                  <input
                    type="text"
                    name="shopping_mall_id"
                    placeholder="쇼핑몰 아이디"
                    value={settings.shopping_mall_id || ''}
                    onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2 flex items-center gap-1">
                    <Key className="h-3.5 w-3.5 text-brand-text-muted" />
                    새 비밀번호 (보안 적용)
                  </label>
                  <input
                    type="password"
                    placeholder="수정할 때만 입력"
                    value={shoppingMallPassword}
                    onChange={(e) => setShoppingMallPassword(e.target.value)}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 확인 점검 간격 (분)</label>
                  <input
                    type="number"
                    name="shopping_mall_check_interval"
                    min="1"
                    max="120"
                    value={settings.shopping_mall_check_interval}
                    onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
                  />
                </div>
              </div>
            </div>

            {/* 인트라넷 설정 */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-brand-primary flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-primary"></span>
                화원 연합 인트라넷
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-3">
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">인트라넷 로그인 주소 (URL)</label>
                  <input
                    type="url"
                    name="intranet_url"
                    placeholder="https://intranet.flower-association.com"
                    value={settings.intranet_url || ''}
                    onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">로그인 ID</label>
                  <input
                    type="text"
                    name="intranet_id"
                    placeholder="인트라넷 아이디"
                    value={settings.intranet_id || ''}
                    onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2 flex items-center gap-1">
                    <Key className="h-3.5 w-3.5 text-brand-text-muted" />
                    새 비밀번호 (보안 적용)
                  </label>
                  <input
                    type="password"
                    placeholder="수정할 때만 입력"
                    value={intranetPassword}
                    onChange={(e) => setIntranetPassword(e.target.value)}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">주문 확인 점검 간격 (분)</label>
                  <input
                    type="number"
                    name="intranet_check_interval"
                    min="1"
                    max="120"
                    value={settings.intranet_check_interval}
                    onChange={handleInputChange}
                    className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
                  />
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* 섹션 3: 카카오 알림톡/문자 피드백 설정 */}
        <div className="glass-panel rounded-xl p-6 shadow-xl space-y-6">
          <div className="flex items-center gap-2 border-b border-brand-border pb-3">
            <Bell className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-semibold text-brand-text-primary">개인화 알림 보고 및 피드백 설정</h2>
          </div>
          
          <div className="space-y-6">
            <div className="flex items-center gap-4 bg-brand-bg/30 p-4 border border-brand-border/60 rounded-lg">
              <label className="text-sm font-semibold text-brand-text-primary">실시간 수집/RPA 처리 알림 수신 여부</label>
              <select
                name="use_notification"
                value={settings.use_notification}
                onChange={handleInputChange}
                className="bg-brand-card border border-brand-border text-brand-text-primary text-sm rounded-lg px-3 py-1.5 transition outline-none"
              >
                <option value="Y">🟢 사용함 (권장)</option>
                <option value="N">🔴 사용 안 함</option>
              </select>
            </div>

            {settings.use_notification === 'Y' && (
              <div className="grid grid-cols-1 gap-6">
                <div>
                  <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">알림 보고 수신 사장님 핸드폰 번호</label>
                  <input
                    type="text"
                    name="notification_phone_number"
                    placeholder="비워둘 시 꽃가게 대표 번호로 발송"
                    value={settings.notification_phone_number || ''}
                    onChange={handleInputChange}
                    className="w-full md:w-1/2 bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none"
                  />
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">
                      RPA 전산 입력 성공 보고 문자 템플릿
                    </label>
                    <textarea
                      name="rpa_success_message"
                      rows={3}
                      value={settings.rpa_success_message}
                      onChange={handleInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none resize-y"
                    />
                    <span className="text-[10px] text-brand-text-muted mt-1.5 block">
                      ※ 변수 사용: `{'{channel}'}` (수집 채널명 치환), `{'{count}'}` (주문 개수 치환)
                    </span>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-brand-text-secondary uppercase tracking-wider mb-2">
                      RPA 전산 입력 실패 경고 문자 템플릿
                    </label>
                    <textarea
                      name="rpa_fail_message"
                      rows={3}
                      value={settings.rpa_fail_message}
                      onChange={handleInputChange}
                      className="w-full bg-brand-bg/50 border border-brand-border focus:border-brand-primary-hover focus:ring-1 focus:ring-brand-primary rounded-lg px-4 py-2.5 text-sm text-brand-text-primary transition outline-none resize-y"
                    />
                    <span className="text-[10px] text-brand-text-muted mt-1.5 block">
                      ※ 변수 사용: `{'{channel}'}` (수집 채널명 치환)
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 저장 제출 버튼 영역 */}
        <div className="flex justify-end pt-4">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-6 py-3 bg-brand-primary hover:bg-brand-primary-hover disabled:bg-brand-text-muted text-white text-sm font-semibold rounded-lg shadow-lg hover:shadow-brand-primary/20 transition cursor-pointer"
          >
            {saving ? (
              <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-white"></div>
            ) : (
              <Save className="h-4 w-4" />
            )}
            <span>설정 정보 저장하기</span>
          </button>
        </div>

      </form>
    </div>
  );
}
