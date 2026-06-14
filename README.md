# ggotAI 모노레포

꽃집 주문 자동화 제품. 세 실행체가 공유 Supabase 프로젝트(DB)로만 통신한다.

| 경로 | 내용 | 스택 |
|---|---|---|
| `ggotAIorder/backend` | 주문 처리 파이프라인(STT→Gemini→주문→RPA) | Python |
| `ggotAIorder/frontend` | 사장님 대시보드(ggotAIya) | React/TS/Vite |
| `ggotAIhp/android` | 통화 수집 앱(녹음·TTS·Supabase INSERT) | Kotlin |
| `supabase/` | DB 계약 단일 출처(마이그레이션·엣지함수·생성타입) | Supabase |

## 스키마 변경 흐름

`supabase/migrations`에 마이그레이션 추가 → 타입 재생성(`frontend`의 `npm run gen:types`)
→ 각 앱 모델 수정(order=Python dataclass, hp=Kotlin data class) → 한 PR → 통합 CI 검증.

> 자동 반영은 불가(언어별 모델). 모노레포는 "한 곳에서 정의하고, 빠뜨리면 CI가 차단"을 보장한다.

## 이력

order·hp 각 repo의 커밋 이력을 git subtree(read-tree --prefix) 병합으로 보존했다.
설계/계획: `ggotAIorder/docs/superpowers/specs/2026-06-14-monorepo-integration-design.md`,
`ggotAIorder/docs/superpowers/plans/2026-06-14-monorepo-integration.md`.
