# [PRD] ggotAIhp 제품 요구사항 문서

## 1. 프로젝트 개요 (Project Overview)

* **앱 이름:** ggotAIhp
* **한줄 설명:** 고객과의 통화가 종료되는 즉시 녹음 파일을 자체 백엔드 서버로 전송하여 꽃 주문 처리를 자동화하는 안드로이드 앱
* **개발 유형:** 안드로이드 네이티브 가벼운 앱 (차후 iOS 확장 고려)
* **개발 난이도:** **중상 (Medium-High)**
* *사유: 안드로이드 최신 OS의 백그라운드 구동 제약, 백그라운드 오디오 녹음 처리와 더불어 유심(USIM) 통화 권한을 이용한 기기 전화번호 자동 추출 및 서버 실시간 인증 인터셉트 흐름을 단단하게 구축해야 함.*



---

## 2. 사용자 시나리오 (User Scenario)

* **누가 (Who):** 1인 또는 소규모 꽃가게를 운영하며 핸드폰으로 직접 주문 전화를 접수하는 사장님
* **언제 (When):** 꽃다발 제작, 분갈이, 포장, 배달 준비 등으로 인해 손을 자유롭게 쓰기 어렵고 바쁘게 움직이는 도중 주문 전화를 받을 때
* **왜 (Why):** * 기존에는 통화 도중 하던 일을 멈추고 필기구를 찾아 주문 내용을 수첩에 메모해야 했음.
* 본 앱을 통해 **별도의 아이디/비밀번호 로그인 절차도 없이, 오직 통화만 종료하면 AI가 기기를 식별하여 알아서 녹음하고 서버로 올려 정리해 주는** 번거로움 제로의 업무 환경을 구현하기 위함임.



---

## 3. 핵심 기능 목록 (Core Features)

* F1. 기기 전화번호 기반 자동 인증 (로그인 대체): 앱 실행 시 사용자의 개입 없이 핸드폰 자체 번호를 추출하여 서버 회원 정보와 대조 후 자동 로그인 승인 처리함.


* F2. 미등록 기기 차단 및 앱 강제 종료: 서버에 등록되지 않은 핸드폰 번호일 경우 경고 메시지를 노출하고 앱을 안전하게 자동 종료함.


* F3. 백그라운드 통화 녹음 및 파일 관리: 앱이 대기 상태일 때 통화 시작/종료를 감지하여 자동으로 오디오를 녹음하고 디스크에 저장함.


* F4. 서버 자동 전송 및 재시도 매커니즘: 통화 종료 즉시 서버로 업로드를 시도하며, 실패 시 최대 3회까지 연속 재전송을 시도함.


* F5. 로컬 히스토리 데이터베이스 관리: 규격화된 포맷에 맞춰 데이터베이스 이력을 생성하고 누적함.


* F6. 전송 실패 처리 및 TTS 음성 알림: 최종 실패 시 에러 로그를 남기고, 사장님이 즉시 인지할 수 있도록 커스텀 실패 문구를 음성(TTS)으로 읽어줌.


* F7. 실시간 전화 수신 현황 및 필터 조회 UI: 당일 수신 현황 요약 및 기간·상태별 필터 검색 기능, 앱 내 음성 다시 듣기 기능을 제공함.


* F8. 수동 재전송 및 에러 로그 확인: 실패 행 클릭 시 상세 에러 내용을 확인하고 사장님이 직접 수동으로 재전송할 수 있는 UI를 제공함.


* F9. 환경 설정 및 앱 제어: 서버 정상 연결 상태(ON/OFF)를 표시하고, 원격 서버 주소 확인 및 실패 음성 메시지 문구를 개인화 설정할 수 있음.



---

## 4. 기술 스펙 (Technical Specifications)

### 1) 개발 플랫폼 및 언어

* **OS 버전:** Android 10 (API Level 29) 이상 target
* **개발 언어:** Kotlin
* **비동기 아키텍처:** Kotlin Coroutines

### 2) 기기 식별 및 자동 로그인 권한 스펙 (★ 인증 체계 전면 수정)

* **필수 보안 권한:** `READ_PHONE_NUMBERS` 및 `READ_PHONE_STATE`
* *이유: 로그인 화면 진입 시 사용자 조작 없이 시스템 유심(USIM) 칩셋으로부터 단말기 고유 전화번호를 안전하게 자동 추출하기 위함.*


* 
**구현 매커니즘:** 앱 구동 즉시 폰 번호를 확인하고, 백엔드의 인증 API를 호출하여 조회된 번호가 서버 DB의 핸드폰 번호군(`mobile_1` ~ `mobile_5`) 중 하나에 포함되어 있는지 교차 검증함.



### 3) 통화 제어, 오디오 및 네트워크 스펙

* **통화 상태 감지:** `BroadcastReceiver` + `TelephonyManager` + `Foreground Service` (상단바 알림 필수)
* **오디오 엔진:** `MediaRecorder` (AudioSource.**`MIC`** 사용 필수, 파일 포맷: **`WAV`** 또는 **`MP3`**)
* **로컬 DB & 동기화:** Jetpack **Room DB** + Jetpack **WorkManager** (네트워크 복구 시 자동 동기화용)
* **네트워크 통신:** Retrofit2 + OkHttp3 (`multipart/form-data` 구성, 연결/읽기/쓰기 타임아웃 각 **30초 이상** 설정 필수)
* **음성 출력:** 안드로이드 순정 `TextToSpeech (TTS)` API
* **파일 네이밍 규칙:** `[사용자전화번호]_[고객전화번호]_[날짜(YYYYMMDD)]_[시간(HHmmss)].wav`
* **규격화된 에러 코드:** `NET_TIMEOUT` (시간초과), `SERVER_500` (서버오류), `FILE_NOT_FOUND` (파일누락), `AUTH_ERR` (기기 미인증), `APP_KILLED` (비정상종료)

### 4) 데이터 모델 (Schema)

#### [스마트폰 로컬 DB] `call_history` 테이블

```sql
CREATE TABLE call_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    [cite_start]user_phone_number TEXT NOT NULL,  -- 자동으로 추출되어 고정된 핸드폰 자체 번호 [cite: 119]
    [cite_start]call_date TEXT NOT NULL,          -- YYYY-MM-DD [cite: 119]
    [cite_start]call_time TEXT NOT NULL,          -- HH:mm:ss [cite: 119]
    [cite_start]phone_number TEXT NOT NULL,       -- 전화를 건 '고객'의 번호 (하이픈 포함) [cite: 119]
    [cite_start]customer_name TEXT DEFAULT '신규', -- 핸드폰 연락처 연동명 [cite: 119]
    [cite_start]transfer_status TEXT NOT NULL,    -- '전송중', '성공', '실패' [cite: 119]
    [cite_start]audio_file_name TEXT NOT NULL,    -- 저장된 파일명 [cite: 119]
    audio_file_path TEXT NOT NULL,    -- 스마트폰 내 절대경로
    [cite_start]duration_seconds INTEGER,         -- 통화 시간(초) [cite: 119]
    [cite_start]error_code TEXT,                  -- 에러 코드 [cite: 119]
    [cite_start]error_message TEXT,               -- 에러 내용 [cite: 119]
    sync_status INTEGER DEFAULT 0     -- 서버 동기화 여부 (0: 미동기화, 1: 완료)
);

```

#### [서버 DB] 1. 회원관리 및 인증 테이블 (`member_info`) (★ 신규 추가)

설계서 6페이지와 12페이지의 요구사항을 반영하여, 한 명의 대표(꽃집)가 최대 5개의 핸드폰 번호(직원 및 관리자 기기)를 등록하여 앱을 동시 구동할 수 있도록 설계했습니다.

```sql
CREATE TABLE member_info (
    id INT AUTO_INCREMENT PRIMARY KEY,
    [cite_start]shop_name VARCHAR(100) NOT NULL,            -- 꽃집명 [cite: 161]
    [cite_start]representative_name VARCHAR(50) NOT NULL,   -- 대표자이름 [cite: 161]
    [cite_start]landline_number VARCHAR(20),                -- 가게 전화번호 (가게Tel) [cite: 161, 321]
    
    -- 단말기 자동인증을 위한 다중 핸드폰 매핑 필드
    [cite_start]mobile_1 VARCHAR(20) NOT NULL UNIQUE,       -- 핸드폰1 (대표 기기 번호) [cite: 161]
    [cite_start]mobile_2 VARCHAR(20) DEFAULT NULL,          -- 핸드폰2 [cite: 161]
    [cite_start]mobile_3 VARCHAR(20) DEFAULT NULL,          -- 핸드폰3 [cite: 161]
    [cite_start]mobile_4 VARCHAR(20) DEFAULT NULL,          -- 핸드폰4 [cite: 161]
    [cite_start]mobile_5 VARCHAR(20) DEFAULT NULL,          -- 핸드폰5 [cite: 161]
    
    [cite_start]business_number VARCHAR(50),                -- 사업자번호 [cite: 161]
    [cite_start]address VARCHAR(255),                       -- 주소 [cite: 161]
    [cite_start]is_approved CHAR(1) DEFAULT 'N',            -- 회원가입승인여부 ('Y' 또는 'N') [cite: 161]
    [cite_start]is_subscribed CHAR(1) DEFAULT 'N',          -- 정기구독여부 ('Y' 또는 'N') [cite: 322]
    [cite_start]subscription_type VARCHAR(20) DEFAULT NULL, -- 정기구독상품종류 ('3개월', '6개월', '12개월') [cite: 161]
    [cite_start]free_trial_start_date DATE,                 -- 무료사용시작일자 [cite: 161]
    [cite_start]current_free_trial_days INT DEFAULT 0,      -- 현재무료사용기간 [cite: 322]
    [cite_start]email VARCHAR(100),                         -- 이메일 [cite: 161]
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

```

#### [서버 DB] 2. 통화 이력 수신 테이블 (`server_call_history`)

```sql
CREATE TABLE server_call_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_phone_number VARCHAR(20) NOT NULL, -- 데이터를 보낸 스마트폰의 번호 (출처 식별용)
    [cite_start]shop_name VARCHAR(100) NOT NULL,        -- 꽃가게 이름 [cite: 190]
    [cite_start]phone_number VARCHAR(20) NOT NULL,      -- 전화를 건 '고객'의 번호 [cite: 168]
    [cite_start]customer_name VARCHAR(50) DEFAULT '신규',-- 고객명 (앱 연동) [cite: 205, 206]
    call_date DATE NOT NULL,                -- 통화 날짜 (YYYY-MM-DD)
    call_time TIME NOT NULL,                -- 통화 시간 (HH:mm:ss)
    duration_seconds INT,                   -- 통화 시간(초)
    audio_file_name VARCHAR(255) NOT NULL,  -- 서버에 저장된 음성 파일명
    
    -- 1단계 앱 전송 테스트 시에는 사용하지 않고 NULL 상태 유지 (차후 2단계 연동용)
    [cite_start]stt_text TEXT DEFAULT NULL,             -- Whisper 변환 텍스트 [cite: 16]
    [cite_start]is_order CHAR(1) DEFAULT 'N',           -- FoaSys 주문 여부 판별 ('Y' 또는 'N') [cite: 18]
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_phone_number) REFERENCES member_info(mobile_1) -- 상호 유기적 매핑을 위한 제약 설정
);

```

---

## 5. 화면 구성 (Screen Composition)

* 
**화면 1. 로그인 및 기기 인증 화면 (`LoginActivity`):** * 아이디/비밀번호 입력 창 및 찾기 링크를 전면 **삭제**합니다.


* 중앙에는 초기 로고 문구인 `"꽃가게의 행복한 변화 ggotAI"`가 노출됩니다.


* 상단 레이아웃에 시스템이 추출한 **[핸드폰 번호: 010-XXXX-XXXX]** 가 텍스트 뷰로 노출됩니다.


* 인증 실패 시 아래에 붉은색 경고 메시지인 `"이 핸드폰은 사용할 수 없습니다."`가 표기되며, 그 아래 정중앙에 큰 **`[확인]`** 버튼 하나만 배치됩니다.




* 
**화면 2. 전화 수신 현황 (메인, `MainActivity`):** 로그인 시 통과된 단말 번호와 매칭된 '꽃가게 이름(예: 서울플라워)'을 상단 헤더에 표기하고 서버 연결 인디케이터를 배치함. 금일 날짜의 전체 통화 테이블을 노출함.


* 
**화면 3. 전화 수신 조회 화면 (`SearchActivity`):** [전체/성공/실패] 필터 라디오 버튼과 달력 선택기 제공. 돋보기 클릭 시 조건 검색 작동.


* 
**화면 4. 전송실패건 재전송 화면 (`ResendActivity`):** 실패 행 클릭 시 띄워지는 상세 팝업 창. 대상자 정보, 현재 상태('전송준비'➔'전송중'➔'전송실패'), 상세 에러 로그 출력 및 최하단에 큰 크기의 **`[재전송]`** 버튼 배치.


* 
**화면 5. 환경설정 화면 (`SettingsActivity`):** [로그아웃] 버튼 및 연동된 백엔드 서버 주소 필드(수정 불가 Read Only) 배치. '전송실패 음성 메세지' 커스텀 입력창 제공.



---

## 6. 상세 기능 명세 (Detailed Functional Specifications)

* **6-1. 앱 기동 시 기기 추출 자동 인증 프로세스 (★ 로그인 로직 대체):**
1. 앱이 실행되면 Splash/Login 화면에서 안드로이드 시스템에 `READ_PHONE_NUMBERS` 권한 승인 여부를 검사함.
2. 권한이 승인되어 있다면 시스템 API를 호출하여 단말기의 유심(USIM) 전화번호를 자동으로 긁어와 화면 텍스트 뷰에 채워 넣음.


3. 추출된 핸드폰 번호를 파라미터로 실시간 서버 인증 API(`GET /api/v1/auth/verify-device?phone=...`)를 전송함.
4. 
**[인증 성공]:** 서버 `member_info` 테이블의 핸드폰 열(1~5) 중 일치하는 데이터가 있고, 승인 여부(`is_approved`)가 'Y'인 경우 즉시 인증 통과 ➔ 매칭된 `shop_name` 정보를 가지고 `MainActivity`(메인 화면)로 자동 진입함.


5. 
**[인증 실패]:** 등록된 번호가 없거나 승인이 'N'인 경우, 화면에 `"이 핸드폰은 사용할 수 없습니다."` 경고 문구를 가시화하고 하단에 `[확인]` 버튼을 노출함. 사장님이 `[확인]` 버튼을 클릭하면 앱 프로세스를 즉시 완전 종료(`finishAndRemoveTask()`)함.




* **6-2. 백그라운드 통화 감지 및 자동 녹음 흐름:**
* 통화 상태 변경 방송을 수신하면 상대방 번호를 확보하고, 포그라운드 서비스를 실행하여 지정된 파일 네이밍 규칙으로 `MediaRecorder` 녹음을 시작함.


* 통화 종료 시 녹음을 중단하고 파일 저장 후 안드로이드 `ContentResolver`로 기기 연락처를 조회함. 매칭명이 있으면 '고객명'에, 없으면 '신규'로 지정해 Room DB에 이력을 적재함 (`transfer_status='전송중'`, `sync_status=0`).




* **6-3. 통화 종료 후 즉시 전송 및 자동 재시도 로직:**
* 저장이 끝난 즉시 백그라운드 코루틴 스코프에서 서버 API 업로드를 호출함. 성공 시 즉시 `transfer_status='성공'`, `sync_status=1`로 업데이트함.


* 실패 시 즉시 2초 대기 후 재시도하며 총 3회 반복함. 최종 실패 시 상태를 '실패'로 꺾고 규격 에러 코드를 바인딩한 뒤 순정 TTS API를 구동해 설정된 음성 경고 메시지를 스피커로 출력함.




* **6-4. 수동 재전송 및 중복 전송 차단 로직:**
* 사장님이 실패 항목 터치 시 에러 내역을 바인딩하여 재전송 팝업을 활성화함. `[재전송]` 버튼을 터치하는 즉시 **`button.isEnabled = false`** 처리를 수행하여 연타로 인한 중복 전송을 원천 차단함. 성공 수신 시 UI를 검은색 '성공' 텍스트로 즉각 변경함.




* **6-5. 유령 상태 방지 및 백그라운드 자동 동기화:**
* 앱 최초 구동 시 Room DB를 스캔하여 '전송중'인 행이 존재하면 모두 `transfer_status='실패'`, `error_code='APP_KILLED'`로 강제 초기화함. 인터넷 연결 정상 전환 감지 시 `WorkManager`가 동기화되지 않은(`sync_status=0`) 항목을 순차 조회하여 서버로 자동 업로드 처리함.



---

## 7. 디자인 가이드 (Design Guide)

* **컬러 시스템 의미 지정:**
* 
**Status Green (`#00C853`):** 서버 정상 연결 표시 인디케이터 테두리/내부 색상 


* 
**Status Red (`#D50000`):** 서버 연결 에러 인디케이터 및 목록의 **'실패' 텍스트 컬러** 


* 
**Text Black (`#212121`):** 기본 본문 텍스트 및 전송 **'성공' 상태 텍스트 컬러** 


* 
**Background Gray (`#E0E0E0`):** 환경설정 내 서버 주소창 등 **Read Only 입력 필드**의 배경 채우기 색상 




* **컴포넌트 구조화:**
* 목록의 각 행(Row)은 명확한 구분선을 지니며, 고객 번호 영역은 '고객명'을 16sp로 크게 노출하고 그 하단에 '전화번호'를 12sp 회색조로 작게 얹는 2줄 구성을 취함. 맨 우측 '듣기' 컬럼에는 범용 볼륨 아이콘 버튼을 배치함.





---

## 8. 제약 사항 (Constraints)

* **안드로이드 단독 개발 및 하드웨어 제약:** 백그라운드 오디오 가로채기가 불가능한 iOS는 대상에서 완전히 제외함. 기기 식별을 무조건 자동으로 처리하도록 스펙이 강화됨에 따라, **공단말기(유심이 없는 폰)이거나 개통 상태가 불완전하여 단말기 내부 정보에서 본인 번호 추출이 불가능한 기기(일부 구형 알뜰폰 칩셋)의 경우, 기기 인증 단계를 통과할 수 없어 앱 사용이 불가능하다**는 하드웨어적 제약 사항을 명시함.
* **배포 및 심사 정책 제약 (구글 플레이 스토어 배포 배제):** 일반 전화 앱이 아님에도 기기 인증을 위한 유심 접근 권한(`READ_PHONE_NUMBERS`)과 백그라운드 통화 로그 권한을 동시에 사용하는 앱은 최신 구글 스토어 정책상 등록 심사 통과가 원천 불가능함. 따라서 본 프로젝트는 **스토어 출시를 완전히 배제하고 사장님들의 단말기에 APK 파일을 다이렉트로 수동 설치(사이드로드)하는 구동 환경을 전제**로 설계함.
* **스마트폰 저장 공간 보존 제약:** 기기 내부 디스크 용량 과부하를 방지하기 위해, 서버 전송이 완전히 완료된 성공 건(`sync_status = 1`)의 실제 음성 소스 파일(.wav)은 파일 생성일 기준 7일이 경과하면 백그라운드에서 자동 영구 삭제되도록 로직을 제한함.
