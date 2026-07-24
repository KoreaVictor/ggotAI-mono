import { defineConfig } from 'vitest/config';

// crypto/authenticate 는 순수 TS(JSX 없음) → node 환경으로 충분.
export default defineConfig({
  test: {
    environment: 'node',
    // 엣지 함수의 순수 검증 로직도 여기서 함께 돌린다. 엣지 함수는 Deno 런타임이라
    // 별도 테스트 러너가 없는데, Deno 비의존 모듈로 떼어두면 vitest 로 검증 가능하다.
    include: [
      'src/**/*.{test,spec}.{ts,tsx}',
      '../../supabase/functions/**/*.{test,spec}.ts',
    ],
  },
});
