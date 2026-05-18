# ggotAIhp 병렬 개발 태스크 목록 (Task List)

- `[x]` 1단계: 프로젝트 환경 구성 및 공통 인터페이스 정의
  - `[x]` [Front] 안드로이드 프로젝트 셋업 (AntiGravity)
    - `[x]` API 29 타겟으로 프로젝트 생성
    - `[x]` Retrofit, Room DB, WorkManager 등 필수 라이브러리 의존성 추가
  - `[x]` [Back] 백엔드 프로젝트 및 DB 셋업 (Claude Code)
    - `[x]` 백엔드 서버 환경 구축 (Supabase: ggotAIhp 프로젝트 ACTIVE)
    - `[x]` `member_info`, `server_call_history` 테이블 생성
  - `[ ]` [Common] API 인터페이스 최종 확정 (Mock 데이터 교환 테스트)

- `[/]` 2단계: 핵심 기능 병렬 개발
  - `[x]` [Front] 단말기 식별 및 자동 인증 로직 구현
    - `[x]` `READ_PHONE_NUMBERS` 권한 요청 및 처리
    - `[x]` 시스템 유심(USIM) 전화번호 자동 추출 로직 작성
    - `[x]` 기기 인증 API 연동
  - `[x]` [Back] 기기 인증 API 구현
    - `[x]` `GET /api/v1/auth/verify-device` 엔드포인트 구현 (Edge Function ACTIVE)
    - `[x]` DB 조회 및 인증 성공/실패 응답 처리
  - `[x]` [Front] 백그라운드 통화 감지 및 음성 녹음 기능 구현
    - `[x]` `BroadcastReceiver`로 통화 상태 감지 구현
    - `[x]` `MediaRecorder`를 활용한 오디오 녹음 및 파일 저장(WAV/MP3) 로직 구현
  - `[x]` [Front] 로컬 DB(Room) 연동 및 로컬 히스토리 관리
    - `[x]` `call_history` 테이블 Room Entity 및 DAO 작성

- `[/]` 3단계: 연동 및 고도화
  - `[x]` [Front] 서버 업로드 및 재전송 메커니즘, TTS 실패 알림 구현
    - `[x]` 녹음 완료 즉시 오디오 파일 업로드 API 호출 로직 작성
    - `[x]` 3회 재시도 메커니즘 및 최종 실패 시 TTS 음성 출력 구현
  - `[x]` [Back] 통화 내역 및 오디오 파일 수신 API 구현
    - `[x]` `POST /api/v1/calls/upload` 엔드포인트 구현 (Edge Function ACTIVE)
    - `[x]` 파일 스토리지 저장 및 `server_call_history` DB 적재 (audio-files 버킷 생성 완료)
  - `[x]` [Front] 조회/검색 UI 및 오디오 재생 기능 구현
    - `[x]` `MainActivity` 현황 UI 및 오디오 재생 구현
    - `[x]` `SearchActivity` 현황 및 필터 UI 작성
    - `[x]` 실패 건 수동 재전송 화면(`ResendActivity`) 및 연타 방지 로직 구현

- `[ ]` 4단계: 통합 테스트 및 디버깅
  - `[ ]` 프론트엔드-백엔드 간 실제 데이터 연동 테스트
  - `[ ]` 통화 녹음 파일 품질 및 서버 전송 안정성 검증
  - `[ ]` 사장님 실제 기기(APK 사이드로드) 1차 필드 테스트
