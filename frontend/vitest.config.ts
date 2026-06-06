import { defineConfig } from 'vitest/config';

// crypto/authenticate 는 순수 TS(JSX 없음) → node 환경으로 충분.
export default defineConfig({
  test: {
    environment: 'node',
  },
});
