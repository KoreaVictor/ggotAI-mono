# ggotAIorder 프론트엔드-백엔드 병렬 개발 구현 계획서 (Web-Based GUI 반영)

본 문서는 `ggotAIorder` 제품 요구사항 문서(PRD)를 바탕으로, 프론트엔드(안티그래비티)와 백엔드(클로드코드)가 상호 간섭 없이 동시에 안정적으로 개발을 진행할 수 있도록 아키텍처를 설계하고 역할을 분담하며, 인터페이스 규격을 정의하기 위해 작성되었습니다. 

특히 사장님의 피드백을 반영하여, **프론트엔드 UI를 웹 기반 데스크톱 애플리케이션(React + Vite + Electron) 스택으로 변경**하고, **Supabase 접속 정보 및 암호화 방식에 대한 합의**를 완료하여 계획에 정식으로 반영하였습니다.

---

## 사용자 검토 완료 사항 (User Review Confirmed)

> [!IMPORTANT]
> **1. 프론트엔드 UI 기술 스택: Vite + React (TypeScript) + Electron**
> - 사장님께서 웹 기반 SW를 개발하고 계신 생태계에 발맞추어, 프론트엔드 상황판 UI(`ggotAIya`)를 **React + Vite + TypeScript** 및 **Electron** 기반으로 구축합니다.
> - 높은 웹 개발 생산성과 미려한 UI 라이브러리(Tailwind CSS, Radix UI 등)를 적극적으로 활용할 수 있습니다.
> - 최종 배포 시에는 `electron-builder`를 사용하여 일반 사용자가 손쉽게 더블 클릭하여 설치/실행할 수 있는 단일 윈도우 실행 파일(`.exe`) 또는 무설치형(Portable) 패키지로 빌드해 드립니다.

> [!NOTE]
> **2. 웹 기반 프론트엔드에서의 OS 제어 및 IPC 브릿지**
> - React 웹 뷰(렌더러 프로세스)는 보안상 직접 OS 쉘 명령을 구동할 수 없습니다.
> - 따라서 Electron의 **메인 프로세스(Node.js 환경)**에 서비스 제어 함수를 위임하고, **Preload 스크립트의 `contextBridge`**를 통해 안전한 통로(IPC Channel)를 개설합니다.
> - 웹 UI에서 [주문수집 중지/시작] 클릭 ➔ 메인 프로세스로 IPC 메시지 전송 ➔ 메인 프로세스가 `child_process.exec`를 통해 관리자 권한으로 `net start ggotAIorder` / `net stop ggotAIorder` 구동.

> [!WARNING]
> **3. Supabase 접속 정보 및 대칭키 암호화 합의 적용**
> - 양측이 동일한 Supabase DB 인스턴스를 사용합니다.
> - 쇼핑몰/인트라넷 연동용 패스워드는 프론트엔드 웹 UI 단에서 `crypto-js` 라이브러리의 AES-256 알고리즘을 사용해 암호화한 뒤 Supabase DB(`setting_info`)에 삽입합니다.
> - 백엔드는 파이썬의 `cryptography` 라이브러리를 이용하여 동일한 대칭키로 안전하게 복호화하여 크롤러에 대입합니다. 이 비밀 키는 양측의 `.env` 환경 변수 파일에 동일하게 지정됩니다.

---

## 제안된 폴더 구조 및 개발 범위 분할

```text
c:\ggotAI\ggotAIorder\
├── PRD.md                       # 제품 요구사항 문서
├── docs/                        # 공통 설계 및 인터페이스 명세 문서 폴더
│   ├── database_schema.sql      # Supabase DDL SQL 및 초기 데이터
│   └── ipc_specification.md     # 프론트-백엔드 간 프로세스 제어 규격
├── frontend/                    # [안티그래비티 영역] 웹 기반 포그라운드 UI (ggotAIya)
│   ├── package.json             # 의존성 모듈 (electron, react, vite, typescript, supabase, crypto-js 등)
│   ├── vite.config.ts           # Vite 빌드 설정
│   ├── tailwind.config.js       # Tailwind CSS 디자인 토큰 설정
│   ├── src/
│   │   ├── main/                # Electron 메인 프로세스 (Node.js)
│   │   │   ├── index.ts         # 메인 프로세스 진입점 (IPC 수신 및 net start/stop 제어)
│   │   │   └── preload.ts       # IPC 통신 브릿지 (React 렌더러에 window.api 노출)
│   │   └── renderer/            # React 렌더러 프로세스 (Web UI)
│   │       ├── src/
│   │       │   ├── main.tsx     # React 진입점
│   │       │   ├── App.tsx      # 라우팅 및 테마 적용
│   │       │   ├── components/  # 공통 카드, 버튼 위젯
│   │       │   ├── views/       # 상황판 대시보드, 주문수집 설정, 주문 이력 그리드 화면
│   │       │   └── index.css    # Tailwind 및 프리미엄 다크모드 스타일링
│   └── README.md                # Node 패키지 실행 및 빌드 가이드
└── backend/                     # [클로드코드 영역] 백그라운드 서비스 및 트레이 엔진 (ggotAIorder)
    ├── src/                     # Windows Service & Core 엔진 소스 코드
    │   ├── service.py           # pywin32 기반 Windows Service 래퍼
    │   ├── tray.py              # pystray 기반 시스템 트레이 아이콘 및 컨텍스트 메뉴
    │   ├── api/                 # FastAPI (가게전화 Webhook 수신 API 엔드포인트)
    │   ├── realtime/            # Supabase Realtime 구독 및 콜백 처리
    │   ├── pipeline/            # faster-whisper STT & Gemini LLM 파이프라인
    │   ├── scraper/             # Playwright 기반 쇼핑몰/인트라넷 크롤러
    │   ├── rpa/                 # asyncio.Lock 기반 싱글턴 키보드/마우스 RPA 매크로
    │   └── notifier/            # 카카오 알림톡/문자 발송 API 연동
    ├── requirements.txt         # 백엔드 의존성 패키지 목록
    └── README.md                # 서비스 등록 및 실행 가이드
```

---

## 제안된 변경 사항 (Proposed Changes)

### [공통 설계 문서 및 환경 구성]
#### [NEW] database_schema.sql
- PRD 명세서 내 4개 테이블(`server_call_history`, `order_details`, `setting_info`, `member_info`)의 DDL SQL 정의.

#### [NEW] ipc_specification.md
- Electron 렌더러와 메인 간의 IPC 채널 명세 (`service:start`, `service:stop`, `service:status` 등) 및 윈도우 OS 서비스 매핑 규격 정의.

---

### [프론트엔드 컴포넌트 - ggotAIya] (안티그래비티 담당 - React + Electron)
프리미엄 반응형 레이아웃과 감각적인 다크 모드를 기본 탑재하여, 고급스러운 관리용 웹 대시보드를 제공합니다.

#### [NEW] frontend/package.json
- `react`, `react-dom`, `@supabase/supabase-js`, `crypto-js` (대칭키 암호화), `electron`, `vite`, `electron-builder` 등 의존성 라이브러리 및 빌드 스크립트 구성.

#### [NEW] frontend/src/main/index.ts
- 윈도우가 활성화되면 화면을 팝업하고, 윈도우 닫기(X) 시 트레이 서비스에 영향을 주지 않고 UI 창만 숨김(Hide) 처리.
- React 렌더러의 IPC 호출을 수신하여 `child_process.exec`로 윈도우 관리자 권한을 활용한 `net start/stop ggotAIorder` 명령어 호출 핸들링.

#### [NEW] frontend/src/main/preload.ts
- `contextBridge.exposeInMainWorld`를 사용해 React 컴포넌트에 안전한 시스템 제어 API(`window.electronAPI.controlService(cmd)`)를 바인딩.

#### [NEW] frontend/src/renderer/src/views/dashboard.tsx
- 실시간 상황판 웹 UI. 수집 채널별 구동 상태(🟢/🔴/⚠️)를 미려한 네온 글로우(Neon Glow) 효과의 원형 위젯으로 표시.
- 실시간 주문 수집 데이터의 최신 카드가 슬라이드 인(Slide-in) 애니메이션과 함께 목록에 실시간 갱신되는 프론트엔드 피드 구현.

#### [NEW] frontend/src/renderer/src/views/settings.tsx
- 주문 수집 설정 웹 UI. 알림톡 여부, 문자 템플릿, 쇼핑몰/인트라넷 연동 계정 입력 폼.
- 패스워드 입력 시 `crypto-js`를 활용해 대칭키로 즉시 암호화한 뒤 Supabase DB로 인서트하는 보안 폼 설계.

#### [NEW] frontend/src/renderer/src/views/order_list.tsx
- `order_details` 테이블과 실시간 연동되는 고성능 데이터 테이블 그리드. 
- 필터링, 정렬, 페이징 지원 및 특정 행 클릭 시 상세 모달(Modal) 팝업 제공. 수동 편집 및 RPA 재수행(`rpa_status='ready'`) 트리거 구현.

---

### [백엔드 컴포넌트 - ggotAIorder] (클로드코드 담당)
(백엔드 구성은 기존과 동일하며, 프론트엔드가 암호화하여 저장한 DB 비밀번호를 복호화해 사용하고, 서비스 시작/종료 시그널에 완벽히 대응하도록 구성합니다.)

---

## 검증 계획 (Verification Plan)

### 자동화 테스트 (Automated Tests)
- **Electron IPC 보안 검증**: 비인가된 메인 명령어 호출 차단 검증.
- **암호화/복호화 교차 검증**: React에서 `crypto-js`로 암호화한 문자열을 Python의 `cryptography` 라이브러리가 오류 없이 깨끗하게 복호화해 내는지 로컬 검증 스크립트 작성 및 수행.

### 수동 검증 (Manual Verification)
- **데스크톱 앱 패키징**: `npm run build` 및 `electron-builder`를 구동하여 최종 `.exe` 실행 파일이 에러 없이 무결하게 패키징되는지 확인.
- **윈도우 서비스 관리자 권한 연동**: 웹 UI 상단 [수집 시작/중지] 버튼 클릭 시 OS 서비스 상태가 🟢/🔴로 토글되는지 실제 윈도우 환경에서 연동 수동 검증.
