# ggotAIhp 병렬 개발 태스크 목록 (Task List)

> 최종 갱신: 2026-06-10 · 코드 위치: `master` (origin/master 동기화 완료)

## 진행 현황 요약

| 단계 | 내용 | 상태 |
|------|------|------|
| 1 | 프로젝트 환경 구성 및 공통 인터페이스 | ✅ 완료 |
| 2 | 핵심 기능 (기기인증·통화감지·로컬DB) | ✅ 완료 |
| 3 | 연동 및 고도화 (업로드·재전송·UI) | ✅ 완료 |
| 4 | 통합 테스트 및 디버깅 | 🔄 진행 중 — 장기 안정성 필드 테스트만 남음 |
| 5 | DB 구조 전면 개편 (3-클라이언트) | ✅ 완료 |
| 6 | 자동 재전송 워커 | ✅ 완료 |

**남은 작업:** 4단계 "사장님 실기기 장기 안정성 필드 테스트"(실사용 관찰)뿐. 그 외 모든 개발·검증 항목 완료.

범례: `[x]` 완료 · `[/]` 진행 중 · `[ ]` 미착수

---

- `[x]` **1단계: 프로젝트 환경 구성 및 공통 인터페이스 정의**
  - `[x]` [Front] 안드로이드 프로젝트 셋업 (AntiGravity)
    - `[x]` API 29 타겟으로 프로젝트 생성
    - `[x]` Retrofit, Room DB, WorkManager 등 필수 라이브러리 의존성 추가
  - `[x]` [Back] 백엔드 프로젝트 및 DB 셋업 (Claude Code)
    - `[x]` 백엔드 서버 환경 구축 (Supabase: ggotAIhp 프로젝트 ACTIVE)
    - `[x]` `member_info`, `server_call_history` 테이블 생성 (※ 5단계에서 신규 스키마로 개편됨)
  - `[x]` [Common] API 인터페이스 최종 확정 — Mock 교환 단계는 생략, 4단계 실데이터 연동 테스트로 대체 검증 완료

- `[x]` **2단계: 핵심 기능 병렬 개발**
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

- `[x]` **3단계: 연동 및 고도화**
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

- `[/]` **4단계: 통합 테스트 및 디버깅**
  - `[x]` 프론트엔드-백엔드 간 실제 데이터 연동 테스트
  - `[x]` 통화 녹음 파일(삼성 기본 녹음) 스캔 및 서버 전송 안정성 검증
  - `[x]` 실기기(Galaxy Note 10, SM-N971N) 빌드·설치·실행 검증 — gradlew 래퍼 복구 + Studio JBR로 `assembleDebug` 성공, adb 설치 후 `MainActivity` 정상 진입
  - `[x]` **인증 버그 발견·해결**: 기기 SIM `01058921670`이 신규 스키마 `member_info`에 없어 `verify-device` 401. id=19(test/테스트꽃집, 기존 `010-0000-0000` 더미)의 `mobile_number`를 `01058921670`으로 변경 → verify-device 200(shop_key=19)·get-settings 200(기본 'Y') 확인
  - `[/]` 사장님 실제 기기 및 실무 환경에서의 **장기 안정성 필드 테스트** (실사용 관찰 — 진행 중)

- `[x]` **5단계: DB 구조 전면 개편 반영** (2026-06-10, 설계 출처: `ggotAIhp.pptx`)
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

- `[x]` **6단계: 자동 재전송 워커** (2026-06-10, 설계: `docs/superpowers/specs/2026-06-10-auto-resend-worker-design.md`, 계획: `docs/superpowers/plans/2026-06-10-auto-resend-worker.md`)
  - `[x]` `ResendPolicy` (상한 10회 → 영구실패 결정) — JVM 단위테스트 3건 통과
  - `[x]` Room v1→v2 마이그레이션(`retry_count` 컬럼, `sync_status=2`=영구실패) — 실기기 업그레이드 설치로 검증(92행 보존, user_version=2)
  - `[x]` `CallHistoryDao.getRetryable` (미전송·실패·상한미달 필터) — 인메모리 계측테스트 통과
  - `[x]` `UploadManager.uploadOnce` 추출 + `ResendWorker`(15분 주기 / `NetworkType.CONNECTED` / `KEEP`) + `MainActivity` 등록 + `ResendActivity` 수동 재전송 리셋
  - `[x]` **실기기 E2E 검증**: 기존 실패 82건 자동 재전송 → 전부 `sync_status=1`, 서버 `server_call_history`(shop_key=19) 적재 확인, `Worker result SUCCESS`

- `[x]` **7단계: 고객 번호·이름 수집 수정 (CallLog)** (2026-06-11, 설계: `docs/superpowers/specs/2026-06-10-customer-number-capture-design.md`, 계획: `docs/superpowers/plans/2026-06-10-customer-number-capture.md`)
  - `[x]` 막다른 길 `EXTRA_INCOMING_NUMBER`(Android 10+ 일반앱 null) 의존 제거 → `CallSyncWorker`가 `CallLogReader`로 최근 통화 조회
  - `[x]` `CustomerResolver`(번호/이름 결정 순수함수) — JVM 단위테스트 5건 통과
  - `[x]` `CallLogEntry`/`CallLogReader`(최근 10분 이내 통화, `READ_CALL_LOG` 방어적 확인) 추가, `CallReceiver` 예약 단순화
  - `[x]` **실기기 E2E 검증**: 저장 연락처와 실통화 → 로컬 `call_history` `phone_number=01049534339`/`customer_name=여현동`, 서버 `server_call_history`(shop_key=19) 신규 행 `id=110` 동일 적재 + 오디오 Storage 업로드(545KB) 확인 (기존 `Unknown`/`신규` 버그 해결)

- `[x]` **8단계: 통화 직후 오프라인 시 헛된 '전송 실패' 음성 제거** (2026-06-11)
  - `[x]` `NetworkUtil.isOnline`(검증된 INTERNET 네트워크 판단) 추가, `ACCESS_NETWORK_STATE` 권한 추가
  - `[x]` `UploadManager`: 통화 직후(VoLTE 직후 IMS-only 순간 등) 오프라인이면 즉시 업로드 보류 → **실패 음성 미발생**, `errorCode=OFFLINE`로 재전송 대상 유지 + 망 복구 즉시 일회성 CONNECTED ResendWorker 예약. 업로드 시도 후 실패도 오프라인이면 음성 생략.
  - `[x]` `ResendWorker`: 일회성(재연결)·주기 워커 동시 실행 시 중복 업로드 방지 위해 프로세스 Mutex로 직렬화 (서버 중복방지가 비원자적 pre-check라 경쟁에 취약)
  - `[x]` **실기기 E2E 검증**: WiFi+데이터 OFF 상태 실통화 → 캡처 정상·음성 미발생·보류(`id=107`), 재연결+앱진입 시 자동 업로드 성공, 서버 신규 행 **1건만**(`id=115`, 중복 없음) 확인

- `[x]` **9단계: 서버 중복 적재 원천 차단 (UNIQUE 인덱스)** (2026-06-11)
  - `[x]` `server_call_history`에 부분 UNIQUE 인덱스 `uq_server_call_history_call` 추가 — `(shop_key, customer_phone_number, call_date, call_time) NULLS NOT DISTINCT WHERE audio_file_name IS NOT NULL` (마이그레이션 `20260611000000_server_call_unique_index.sql`). 시드 더미(audio 없는 행) 비파괴 제외
  - `[x]` `upload-call`: 비원자적 pre-check를 통과한 동시 요청이 UNIQUE 위반(23505) 시 멱등 성공 처리하도록 보강 후 재배포(v4, verify_jwt 유지)
  - `[x]` **검증**: 원시 중복 INSERT → 23505 거부 확인 · 함수 정상 업로드(200) · 동일/동시 요청에도 tuple당 서버 행 1건만 생성 확인 (테스트 데이터·스토리지 정리 완료)

- `[x]` **10단계: CallSyncWorker 오디오 길이 추출 타임아웃 가드** (2026-06-11)
  - `[x]` 배경: 실기기 검증 중 `MediaMetadataRetriever`가 일시적 스토리지 I/O 스톨로 워커를 수 분간 블록(D상태)하는 현상 관찰(기존 재시도 루프는 "반환"을 전제라 hang은 못 막음). 자동 복구는 됐으나 통화 직후 업로드가 지연.
  - `[x]` `getAudioDuration`을 단일 스레드 Executor + `Future.get(10s)` 패턴으로 변경 — 추출이 시간 내 안 끝나면 0초로 진행해 통화 저장·업로드를 지연 없이 계속(멈춘 네이티브 스레드는 스톨 해소/프로세스 종료 시 정리). 정상 경로는 별도 스레드에서 동일 동작.
  - `[x]` **실기기 E2E 검증**: 정상 통화 → 길이 추출(17초, 별도 스레드) 정상·`DB 저장 id=113`·업로드 성공, 서버 `id=125` 동일 적재(무회귀)

- `[x]` **11단계: 완전 종료 버튼** (2026-06-11)
  - `[x]` 메인 툴바에 종료 아이콘(`btnExit`) 추가 + 영향 고지 확인 다이얼로그
  - `[x]` 완전 종료: `CallReceiver`(매니페스트 수신기) 컴포넌트 비활성화 + WorkManager 전체 취소(영속화 대기) + `finishAndRemoveTask`. 재실행 시 `onCreate`에서 수신기 재활성화 + 주기 워커 재등록으로 복구
  - `[x]` **실기기 E2E 검증(adb UI 자동화)**: 종료 → `disabledComponents`에 CallReceiver·런처 복귀 확인 / 재실행 → 수신기 재활성화·주기 워커(잡 #34) 재등록 확인

- `[x]` **12단계: 배터리 최적화 제외 안내** (2026-06-11)
  - `[x]` `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` 권한 추가
  - `[x]` `MainActivity` 진입 시 `PowerManager.isIgnoringBatteryOptimizations`로 미제외면 안내 다이얼로그 → [설정 열기]는 `ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` 시스템 화면 호출(미지원 시 최적화 목록으로 폴백). 이미 제외면 미표시(반복 안내 없음)
  - `[x]` **실기기 E2E 검증(adb UI 자동화)**: 미제외 시 안내 다이얼로그 표시 확인 · "설정 열기" → 시스템 `RequestIgnoreBatteryOptimizations` 호출(logcat) 확인 · 화이트리스트 등록 시 다이얼로그 미표시 확인
