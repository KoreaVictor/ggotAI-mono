# ggotAIhp 병렬 개발 태스크 목록 (Task List)

- `[x]` 1단계: 프로젝트 환경 구성 및 공통 인터페이스 정의
  - `[x]` [Front] 안드로이드 프로젝트 셋업 (AntiGravity)
    - `[x]` API 29 타겟으로 프로젝트 생성
    - `[x]` Retrofit, Room DB, WorkManager 등 필수 라이브러리 의존성 추가
  - `[x]` [Back] 백엔드 프로젝트 및 DB 셋업 (Claude Code)
    - `[x]` 백엔드 서버 환경 구축 (Supabase: ggotAIhp 프로젝트 ACTIVE)
    - `[x]` `member_info`, `server_call_history` 테이블 생성 (※ 5단계에서 신규 스키마로 개편됨)
  - `[ ]` [Common] API 인터페이스 최종 확정 (Mock 데이터 교환 테스트)

- `[/]` 2단계: 핵심 기능 병렬 개발
  - `[x]` [Front] 단말기 식별 및 자동 인증 로직 구현
    - `[x]` `READ_PHONE_NUMBERS` 권한 요청 및 처리
    - `[x]` 시스템 유심(USIM) 전화번호 자동 추출 로직 작성
    - `[x]` 기기 인증 API 연동
  - `[x]` [Back] 기기 인증 API 구현
    - `[x]` `GET /api/v1/auth/verify-device` 엔드포인트 구현 (Edge Function ACTIVE)
    - `[x]` DB 조회 및 인증 성공/실패 응답 처리
  - `[x]` [Front] 백그라운드 통화 감지 및 음성 파일 스캔 연동 구현
    - `[x]` `BroadcastReceiver`로 통화 종료 상태 감지 구현
    - `[x]` `MediaRecorder` 제거 및 `MANAGE_EXTERNAL_STORAGE` 권한 획득
    - `[x]` 삼성 스마트폰 기본 통화 녹음 파일 광역 스캔 및 `WorkManager` 기반 안전한 백그라운드 연동 구현
    - `[x]` `READ_CONTACTS` 권한을 이용한 기기 주소록 조회 및 고객명 자동 기입
  - `[x]` [Front] 로컬 DB(Room) 연동 및 로컬 히스토리 관리
    - `[x]` `call_history` 테이블 Room Entity 및 DAO 작성

- `[x]` 3단계: 연동 및 고도화
  - `[x]` [Front] 서버 업로드 및 재전송 메커니즘, TTS 실패 알림 구현
    - `[x]` 녹음 완료 즉시 오디오 파일 업로드 API 호출 로직 작성
    - `[x]` 3회 재시도 메커니즘 및 최종 실패 시 TTS 음성 출력 구현
  - `[x]` [Back] 통화 내역 및 오디오 파일 수신 API 구현
    - `[x]` `POST /api/v1/calls/upload` 엔드포인트 구현 (Edge Function ACTIVE)
    - `[x]` 파일 스토리지 저장 및 `server_call_history` DB 적재 (audio-files 버킷 생성 완료)
  - `[x]` [Front] 조회/검색 UI 및 오디오 재생 기능 구현
    - `[x]` `MainActivity` 기획서 맞춤형 상단 UI(조회/셋팅 버튼, 상태 아이콘) 개편
    - `[x]` 기본 앱바 숨김 처리 및 환경설정(`SettingsActivity`) 연동 On/Off 기능 구현
    - `[x]` `SearchActivity` 현황 및 필터 UI 작성
    - `[x]` 실패 건 수동 재전송 화면(`ResendActivity`) 및 연타 방지 로직 구현

- `[/]` 4단계: 통합 테스트 및 디버깅
  - `[x]` 프론트엔드-백엔드 간 실제 데이터 연동 테스트 (완료)
  - `[x]` 통화 녹음 파일(삼성 기본 녹음) 스캔 및 서버 전송 안정성 검증 (완료)
  - `[/]` 사장님 실제 기기 및 실무 환경에서의 장기 안정성 필드 테스트
    - `[x]` 실기기(Galaxy Note 10, SM-N971N) 빌드·설치·실행 검증 — 캐시 gradle 8.4 + Studio JBR로 `assembleDebug` 성공, adb 설치 후 `MainActivity` 정상 진입
    - `[x]` **인증 버그 발견·해결**: 기기 SIM `01058921670`이 신규 스키마 `member_info`에 없어 `verify-device` 401. id=19(test/테스트꽃집, 기존 `010-0000-0000` 더미)의 `mobile_number`를 `01058921670`으로 변경 → verify-device 200(shop_key=19)·get-settings 200(기본 'Y') 확인

- `[x]` 6단계: 자동 재전송 워커 (2026-06-10, 설계: `docs/superpowers/specs/2026-06-10-auto-resend-worker-design.md`)
  - `[x]` `ResendPolicy`(상한 10회/영구실패 결정) — JVM 단위테스트 3건 통과
  - `[x]` Room v1→v2 마이그레이션(`retry_count` 컬럼) — 실기기 업그레이드 설치로 검증(92행 보존, user_version=2)
  - `[x]` `CallHistoryDao.getRetryable` — 인메모리 계측테스트 통과
  - `[x]` `UploadManager.uploadOnce` 추출 + `ResendWorker`(15분 주기/NetworkType.CONNECTED/KEEP) + `MainActivity` 등록 + `ResendActivity` 리셋
  - `[x]` **실기기 E2E 검증**: 기존 실패 82건 자동 재전송 → 전부 `sync_status=1`, 서버 `server_call_history`(shop_key=19) 적재 확인, `Worker result SUCCESS`

- `[x]` 5단계: DB 구조 전면 개편 반영 (2026-06-10, 설계 출처: `ggotAIhp.pptx`)
  - `[x]` [Back] 라이브 DB 점검 및 신규 스키마 확인 (3-클라이언트 구조: ggotAIhp/ggotAIorder/ggotAIya)
    - `[x]` `member_info`: `mobile_1~5` → 단일 `mobile_number`, `username`/`password`/`address_detail` 추가
    - `[x]` `server_call_history`: 연결키 `user_phone_number` → `shop_key`(FK member_info.id), `phone_number` → `customer_phone_number`, `channel_order`/`channel_classification` 신설
    - `[x]` 신규 테이블 확인: `order_details`, `setting_info`, `phone_verification` (앱은 order_details/phone_verification 미사용)
  - `[x]` [Back] Edge Function 신규 스키마 정합 수정 및 배포
    - `[x]` `verify-device`: `mobile_number` 조회로 변경, 응답에 `shop_key` 추가
    - `[x]` `upload-call`: `mobile_number`→`shop_key` 식별 후 `channel_order='핸드폰'`/`channel_classification=기기번호`/`customer_phone_number`로 적재 (중복체크·롤백도 `shop_key` 기준)
    - `[x]` `delete-call`: `mobile_number` 조회 + `shop_key` 기준 삭제
    - `[x]` init 마이그레이션을 신규 5개 테이블 스키마로 재작성
    - `[x]` 3개 함수 배포 후 시드꽃집(id=8)으로 verify→upload→delete 전 과정 검증 완료
  - `[x]` [Front] Android 앱 호환성 확인 — 함수가 `mobile_number→shop_key` 내부 변환하여 **앱 무수정 호환**
  - `[x]` [Back/Front] `setting_info` 읽기 연동 — 알림 동작 제어 (use_notification SSOT)
    - `[x]` 신규 Edge Function `get-settings` (mobile_number→shop_key→setting_info, 행 없으면 기본 'Y') 구현·배포
    - `[x]` 라이브 검증: 기본값('Y')/미승인(401)/`'N'` 행 경로 전부 통과
    - `[x]` Android: `ApiService.getSettings` + `MainActivity` 진입 시 캐시(`USE_NOTIFICATION`), `UploadManager` TTS 알림 게이팅 (※ 2026-06-10 실기기 빌드·실행 검증 완료)
