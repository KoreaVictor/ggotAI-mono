function Stub({ title }: { title: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center p-10">
      <div className="text-brand-text-primary font-display font-bold text-xl mb-2">{title}</div>
      <div className="text-brand-text-muted text-sm">이 화면은 다음 단계(인증·계정, 서브프로젝트 B)에서 제공됩니다.</div>
    </div>
  );
}

export const SignupView = () => <Stub title="회원가입" />;
export const FindIdView = () => <Stub title="아이디 찾기" />;
export const FindPwView = () => <Stub title="비밀번호 찾기" />;
export const MyPageView = () => <Stub title="마이페이지" />;
