import heroImg from '../assets/hero.png';

export function HomeView({ onLogin, onSignup }: { onLogin: () => void; onSignup: () => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center p-10 gap-6">
      <img src={heroImg} alt="ggotAI 마스코트" className="w-40 h-40 object-contain opacity-90" />
      <div>
        <div className="font-display font-bold text-2xl text-brand-text-primary">ggotAI(꽃아이)</div>
        <div className="text-brand-text-secondary mt-2">24시간 든든한 우리가게 AI 직원</div>
      </div>
      <div className="flex gap-3">
        <button
          onClick={onLogin}
          className="px-6 py-2.5 rounded-lg bg-brand-primary text-white font-semibold text-sm shadow-lg shadow-brand-primary/20 hover:opacity-90 transition"
        >
          로그인
        </button>
        <button
          onClick={onSignup}
          className="px-6 py-2.5 rounded-lg border border-brand-border text-brand-text-secondary font-semibold text-sm hover:bg-brand-card-hover transition"
        >
          회원가입
        </button>
      </div>
    </div>
  );
}
