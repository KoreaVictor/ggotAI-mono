# ggotAIorder 개발 태스크 목록 (Task List) - Web-Based GUI 반영

프론트엔드(안티그래비티 - React + Electron)와 백엔드(클로드코드 - Windows Service)가 병렬로 작업을 수행하고 최종 통합을 이루기 위한 세부 진행 현황판입니다.

---

## 📅 Phase 1: 설계 및 공통 기반 구축
- [ ] 공통 데이터베이스 스펙 설정 및 Supabase 테이블 빌드 (`docs/database_schema.sql`)
- [ ] 프론트-백엔드 간 프로세스 제어 규격 및 Electron IPC 채널 정의 (`docs/ipc_specification.md`)
- [ ] 민감 설정 정보(비밀번호 등) 암호화 알고리즘(AES-256) 키 및 로컬 `.env` 환경 변수 구조 동기화

---

## 🎨 Phase 2: [프론트엔드] ggotAIya UI 개발 (안티그래비티 담당 - React + Electron)
- [ ] 프론트엔드 개발 프로젝트 환경 및 의존성 구성 (`frontend/package.json`, `tsconfig.json`)
- [ ] Electron 메인 프로세스 및 Preload 설계
  - [ ] `main/index.ts` 데스크톱 프로그램 실행 및 DPI, 크기 조정, 창 숨기기(트레이 연동대비) 처리
  - [ ] `main/preload.ts` contextBridge를 통한 안전한 IPC 채널 API 노출 (`window.electronAPI`)
  - [ ] 렌더러의 시작/중지 커맨드를 받아 윈도우 관리자 권한으로 `net start/stop ggotAIorder` 쉘 커맨드 실행 구현
- [ ] React 렌더러 UI 핵심 화면 개발 (Tailwind CSS 및 다크모드 적용)
  - [ ] 대시보드 화면 (`renderer/src/views/dashboard.tsx`)
    - [ ] 수집 채널별 실시간 구동 상태(🟢/🔴/⚠️) 표시 위젯 컴포넌트 개발 (네온 글로우 효과 적용)
    - [ ] 실시간으로 인입되는 최근 주문 수집 내역 카드 목록 및 페이드인 애니메이션 구현
    - [ ] 당일 누적 주문 수집 및 입력 성공 건수 통계 대시보드 구현
  - [ ] 주문 수집 설정 화면 (`renderer/src/views/settings.tsx`)
    - [ ] 알림톡/문자 발송 여부(Y/N) 토글 스위치 및 메시지 치환 템플릿 입력 폼 구현
    - [ ] 쇼핑몰/인트라넷 계정 정보 입력 및 `crypto-js`를 활용한 대칭키 AES-256 암호화 연동 처리
    - [ ] 수집 간격(분) 스핀 박스 컨트롤 구성 및 Supabase `setting_info` 테이블 반영 로직 구현
  - [ ] 주문 내역 관리 화면 (`renderer/src/views/order_list.tsx`)
    - [ ] `order_details` 데이터 그리드 테이블 뷰 및 필터링/정렬/페이지네이션 기능 구현
    - [ ] 특정 주문 행 클릭 시 상세 모달 팝업 제공 및 수동 수정 폼 구현
    - [ ] RPA 상태를 `'ready'`로 강제 전환해 재실행시키는 트리거 버튼 구현
- [ ] React + Electron 패키징 및 빌드 설정 (`electron-builder`)
  - [ ] 배포용 `.exe` 단일 바이너리 패키징 구성 확인

---

## ⚙️ Phase 3: [백엔드] ggotAIorder 핵심 엔진 개발 (클로드코드 담당)
- [ ] 백엔드 서비스 라이프사이클 및 트레이 아이콘 골격 구성 (`service.py`, `tray.py`)
- [ ] FastAPI Webhook 수신 엔드포인트 `/api/v1/gate-phone/upload` 구현 및 파일 스토리지 적재 로직 구축
- [ ] Supabase Realtime 감시 스레드 (`realtime/listener.py`)를 통해 `server_call_history` 테이블 실시간 INSERT 콜백 연동
- [ ] 경량 STT 및 Gemini API AI 주문 추출 파이프라인 개발 (`pipeline/engine.py`)
  - [ ] faster-whisper C++ 엔진 기반 음성-텍스트(STT) 변환 연동
  - [ ] Gemini API 프롬프트 작성 및 11개 정형 필드 JSON 출력 연동
  - [ ] 공백 필드 3개 이상 시 `is_order='N'` 판별 및 파일 자동 강제 삭제 예외 필터 구현
- [ ] Playwright 기반 인터라넷 정기 크롤러 (`scraper/crawler.py`)
  - [ ] APScheduler 스케줄링 연동 및 헤드리스 브라우저 로그인 세션 유지 로직 구현
  - [ ] `setting_info`에서 프론트가 암호화해 저장한 비밀번호를 파이썬 복호화 모듈을 통해 원래 값으로 복원하여 크롤러에 투입
  - [ ] 수집된 원문 `stt_text` 필드 기록 및 AI 필터 패스 후 바로 `order_details` (`rpa_status='ready'`) 삽입 로직 구현
  - [ ] 크롤링 3회 이상 실패 시 비상 알림 발송 연동 예외 처리
- [ ] asyncio.Lock 기반 싱글턴 RPA 엔진 및 비상 대피 백업 기능 개발 (`rpa/singleton_macro.py`)
  - [ ] 키보드/마우스 및 클립보드 기반 꽃집 업무 관리 프로그램 입력 매크로 구현
  - [ ] 관리 프로그램 미구동 감지 시 로컬 폴더 엑셀(.xlsx) 파일 및 텍스트 영수증 생성 로직 구현
  - [ ] 최종 RPA 성공/실패 여부에 따른 `rpa_status` 필드 업데이트 구현
- [ ] 알림톡/문자 발송기 구현 (`notifier/sms_sender.py`)
  - [ ] `setting_info` 설정에 따라 템플릿 문자열의 `{channel}`, `{count}` 실시간 변수 치환 구현
  - [ ] 카카오 알림톡/문자 API 연동 및 발송 성공 이력 기록

---

## 🔗 Phase 4: 통합 및 최종 검증 (공동 수행)
- [ ] 프론트엔드(`ggotAIya` React/Electron)와 백엔드(`ggotAIorder` Windows Service) 간의 Supabase DB 스키마 정합성 교차 테스트
- [ ] React UI의 [수집 중지] 버튼 클릭 -> Electron IPC -> 백엔드 윈도우 서비스가 정상 정지되고 트레이 아이콘이 🔴로 바뀌는지 OS 수준의 연동 수동 검증
- [ ] 모의 음성 파일 Webhook 전송 -> STT 변환 -> Gemini 분석 -> order_details 생성 -> 싱글턴 RPA 실행 -> 카카오 알림톡 발송의 E2E 시나리오 완성도 통합 검증
