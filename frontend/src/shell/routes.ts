// 셸 라우트 식별자 (로그인 전 5 + 로그인 후 4). App.tsx·TopHeader 공유.
export type Route =
  | 'home'
  | 'login'
  | 'signup'
  | 'findId'
  | 'findPw'
  | 'dashboard'
  | 'orders'
  | 'settings'
  | 'mypage';
