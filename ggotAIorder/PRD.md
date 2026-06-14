[PRD] ggotAIorder 제품 요구사항 문서 (Product Requirement Document)
1. 프로젝트 개요 (Project Overview)

프로그램 이름: ggotAIorder   
PDF


한줄 설명: 다중 채널(가게전화, 핸드폰, 가게음성, 쇼핑몰, 인터라넷)로부터 수신된 비정형 주문을 실시간 감지·분석하여, 정형화된 데이터로 변환 후 꽃집 관리 프로그램에 자동으로 입력(RPA)하는 윈도우 백그라운드 서비스   
PDF


개발 유형: 윈도우 기반 독립 백그라운드 서비스 및 가벼운 백엔드 API (Python Web Framework 연동)   
PDF
+ 3

개발 난이도: 상 (High)


이유: Supabase Realtime 웹소켓 구독, 외부 Webhook 수신 API 구동, 로컬 경량 STT 및 LLM 파이프라인 제어, Headless 브라우저 스크래핑, asyncio.Lock 기반 RPA 순차 동기화 및 엑셀 백업 예외 처리가 결합된 고도의 자동화 제어 시스템임.  
PDF
+ 2

2. 사용자 시나리오 (User Scenario)

누가 (Who): 1인 또는 소규모 꽃가게를 운영하며 현장 작업(꽃다발 제작, 분갈이, 배달 등)과 다중 채널 주문 접수를 동시에 혼자 처리해야 하는 사장님   
PDF
+ 1


언제 (When): * 매장에 손님이 와서 말로 주문할 때   
PDF
+ 1

작업 도중 스마트폰이나 가게 일반전화로 주문 통화가 올 때   
PDF
+ 1

정기적으로 쇼핑몰이나 타지역 인터라넷을 통해 전산 주문이 들어올 때   
PDF

왜 (Why): * 기존에는 주문이 올 때마다 하던 일을 멈추고 필기구를 찾아 수첩에 받아 적어야 했고, 짬이 날 때 컴퓨터를 켜서 전산 프로그램에 다시 수동으로 입력해야 했음.

이중 전산 작업으로 인한 시간 낭비 및 오기입 리스크를 제거하고, "사장님은 어떤 채널로 주문이 오든 현장 작업에만 집중하고, 시스템이 백단에서 실시간으로 주문을 전산에 알아서 입력해 준다"는 완벽한 작업 독립성을 확보하기 위함임.  
PDF

3. 핵심 기능 목록 (Core Features)
F1. 가게 전화 Webhook 수신 및 처리: 인터넷전화(VoIP) CTI 인프라와 연동하여, 통화 종료 즉시 통신사 서버가 보내는 음성 파일 및 발신자 정보(Webhook POST)를 대기·수신하는 API 엔드포인트 기능   
PDF

F2. 핸드폰/가게음성 실시간 감시 (Realtime 구독): Supabase Realtime 웹소켓 채널을 상시 가동하여, server_call_history 테이블에 신규 음성 데이터가 추가(INSERT)되는 순간을 실시간 포착하는 기능   
PDF
+ 3

F3. 쇼핑몰 주문 자동 연동: 주문 발생 시 발송되는 이메일(SMTP) 알림 인터셉트 파싱 또는 공식 주문 수집 API를 통해 정형 데이터를 다이렉트로 안전하게 수집하는 기능   
PDF

F4. 인터라넷 채널 자동 크롤링 (Playwright): 타지역 꽃집 인터라넷 시스템에 Headless 브라우저로 주기적 자동 로그인 및 목록 감시(Polling)를 수행하여 신규 주문 내역을 스크래핑하는 기능   
PDF
+ 4

F5. 오픈소스 경량 STT 가동: 수신된 비정형 음성 파일을 텍스트 원문 문장으로 변환하는 로컬 엔진 기능 (faster-whisper 기반)   
PDF

F6. Gemini API 기반 주문 추출 및 필터링: * 변환된 텍스트에서 11가지 핵심 주문서 항목을 JSON 형태로 자동 추출하는 기능   
PDF
+ 2

추출 결과 중 공백 항목이 3개 이상일 경우 꽃 주문이 아닌 것으로 판별(is_order = 'N')하고 서버 임시 음성 파일을 즉시 삭제하는 예외 필터링 기능   
PDF
+ 2

F7. 싱글턴 RPA 동기화 큐: 여러 채널에서 주문이 동시에 밀려들어도 윈도우 마우스/키보드 제어가 꼬이지 않도록 asyncio.Lock()을 통해 단 하나의 RPA 로봇만 순차적으로 실행시키는 제어 기능   
PDF
+ 2

F8. 관리 프로그램 미구동 시 예외 비상 처리: PC 내에 꽃집 업무 관리 프로그램 창이 꺼져 있을 경우 프로세스를 중단하지 않고, 자동으로 엑셀(.xlsx) 파일과 텍스트 인수증 영수증을 생성하여 디스크에 보존하는 백업 기능   
PDF
+ 1

F9. 개인화 결과 보고 알림 발송: RPA 처리가 끝나면 setting_info를 조회하여 사용자가 설정한 성공/실패 문구 내의 {channel}과 {count} 변수를 실시간 치환 후 사장님 핸드폰 번호로 카카오 알림톡 또는 문자를 발송하는 기능   
PDF

F10. Windows Service 독립 구동 및 트레이 상주: 포그라운드 프로그램과 분리되어 윈도우 부팅 시 자동 시작되며, 트레이 아이콘 double-click 감지 시 관리 UI(ggotAIya)를 호출하는 백그라운드 관리 기능   
PDF
+ 3

4. 기술 스펙 (Technical Stack)
언어 (Language): Python 3.11+


API 웹 프레임워크: FastAPI (가게전화 Webhook 수신용)   
PDF
+ 1


윈도우 서비스 관리: pywin32 (Windows Service 등록 및 제어용)   
PDF


트레이 상주 UI: pystray, Pillow (시스템 트레이 아이콘 상주 및 이벤트 핸들링)   
PDF


데이터베이스 및 인프라: Supabase (Cloud DB 및 스토리지)   
PDF
+ 3


실시간 이벤트 감시: Supabase Realtime (웹소켓 기반 인서트 감시)   
PDF
+ 4


STT (음성 인식): faster-whisper (C++ 기반 경량 고속 STT 엔진)   
PDF


LLM (주문 정형화): Google Gemini API (google-generativeai SDK)   
PDF


웹 자동화 수집: Playwright (Headless 브라우저 모드 구동)   
PDF


스케줄러: APScheduler (정기 크롤링 폴링 주기 제어)   
PDF


RPA 제어 및 동기화: asyncio (asyncio.Lock() 기반 순차 락 제어)   
PDF
+ 1


엑셀 백업: openpyxl (비상 대피용 엑셀 생성 기능)   
PDF

5. 화면 구성 (UI Components)
UC1. 윈도우 작업 표시줄 트레이 아이콘 및 메뉴:


상주 아이콘: 윈도우 우측 하단 트레이 영역에 ggotAI 브랜드 로고 아이콘 상주.  
PDF


마우스 더블클릭 이벤트: 아이콘 더블클릭 시 관리용 UI 프로그램(ggotAlya)을 가동하여 상황판 화면을 즉시 팝업.  
PDF

우클릭 콘텍스트 메뉴: [상황판 열기], [주문수집 상태] (🟢 주문 수집 중 / 🔴 주문 수집 중지), [ggotAIorder 정보] 출력.

UC2. 시스템 서비스 관리 통합 인터페이스 (화면 없는 제어부):

본 프로그램 내부에는 독립된 버튼 화면이 없으며, 모든 제어는 포그라운드 앱(ggotAlya) 상단의 [주문수집 중지] / [주문수집 시작] 버튼과 매핑되어 제어됨.  
PDF


net stop ggotAIorder 수신 시 ➔ 수집 루프 일시 정지 및 아이콘 빨간색 원 변경.  
PDF


net start ggotAIorder 수신 시 ➔ 수집 루프 재가동 및 아이콘 녹색 원 변경.  
PDF

6. 상세 기능 명세 (Functional Specifications)
6-1. [가게 전화 수집 모듈] VoIP Webhook 수신 엔진

FastAPI 인프라를 통해 /api/v1/gate-phone/upload POST 엔드포인트를 상시 리스닝함.  
PDF
+ 1

통신사로부터 통화 종료 웹훅(Multipart Form)이 인입되면 매개변수(file, caller_number, call_duration, user_phone_number)를 수신함.  
PDF
+ 1

수신된 음성 파일은 고유 ID를 부여하여 Supabase 스토리지 버킷 경로에 일차적으로 임시 적재함.  
PDF
+ 1


server_call_history 테이블에 첫 행(INSERT)을 생성하며, channel_order는 '가게전화'로 마킹함.  
PDF
+ 1

행 생성이 완료되면 곧바로 6-4 AI 데이터 정형화 파이프라인을 비동기로 호출함.  
PDF

6-2. [핸드폰/가게음성 수집 모듈] Supabase Realtime 감시 엔진
프로그램 구동 시 supabase.channel()을 통해 public.server_call_history 테이블의 INSERT 이벤트를 24시간 실시간 구독함.  
PDF
+ 2

스마트폰 앱 채널(ggotAIhp)에 의해 신규 행이 추가되면 실시간 payload가 수집 엔진 콜백 함수(on_new_call_received)로 즉시 유입됨.  
PDF
+ 4

데이터 객체에서 고유 ID(id)와 업로드된 음성 파일 이름(audio_file_name)을 안전하게 추출하여 곧바로 6-4 AI 데이터 정형화 파이프라인을 호출함.  
PDF
+ 2

6-3. [인터라넷 수집 모듈] 정기 폴링 크롤러 엔진 (Playwright)

APScheduler를 통해 setting_info 테이블의 주기에 따라 크롤링 루프를 실행함.  
PDF


Playwright Headless 모드로 인터라넷 사이트에 자동 로그인 세션을 획득함.  
PDF
+ 1

신규 주문 목록 페이지에서 주문 번호를 추출한 뒤, 우리 DB와 교차 검증하여 중복 수집을 방지함.  
PDF

신규 주문 발견 시 상세 페이지에 진입하여 11가지 핵심 정보를 긁어옴.  
PDF
+ 1

긁어온 원본 텍스트는 server_call_history의 stt_text 필드에 다이렉트 저장함. (audio_file_name은 'INTRANET_CRAWLED')   
PDF

AI 단계를 완전히 패스하고 즉시 order_details 테이블에 rpa_status='ready' 상태로 최종 정형 데이터를 직접 인서트함.  
PDF
+ 1


예외 처리: HTML 구조 변경으로 인한 크롤링 에러가 연속 3회 이상 발생하면 사장님 핸드폰으로 비상 알림 문구를 즉시 전송함.  
PDF
+ 1

6-4. [AI 데이터 정형화 파이프라인 모듈] STT 및 Gemini 연동 엔진

STT 단계: 음성 파일을 faster-whisper 로컬 엔진에 입력하여 문자열로 변환하고, 해당 건의 server_call_history.stt_text 필드에 즉시 업데이트함.  
PDF
+ 2


Gemini LLM 단계: 변환된 stt_text 원문을 Prompt 템플릿과 결합하여 Gemini API에 주입하고, 구조화된 11가지 표준 주문서 양식 JSON 객체로 리턴받음.  
PDF
+ 2


꽃 주문 여부 판별 규칙: Gemini가 리턴한 JSON 구조체에서 11가지 주문서 항목 중 값이 비어있는 항목(None 또는 공백)이 3개 이상일 경우, 시스템은 꽃 주문이 아닌 것으로 자동 판별(is_order = 'N')함. 이 경우 서버 및 로컬에 임시 저장된 음성 파일을 즉시 강제 삭제하고 프로세스를 마감함.  
PDF
+ 4

꽃 주문이 맞다면(is_order = 'Y'), 분석된 JSON 데이터를 order_details 테이블에 인서트하며 이때 rpa_status = 'ready'로 설정함.  
PDF
+ 1

6-5. [자동 전산 입력 모듈] 싱글턴 순차 RPA 제어 엔진

동기화 락킹: 다중 채널 충돌을 막기 위해 asyncio.Lock() 매커니즘을 진입점에 걸어 단 하나의 RPA 인스턴스만 실행되도록 순차 큐 제어를 수행함.  
PDF
+ 1


프로그램 미구동 예외 처리: 꽃집 업무 관리 프로그램의 창 제목(Window Title)을 찾지 못할 경우 프로세스를 터뜨리지 않고, 수집된 데이터를 바탕으로 로컬 폴더에 엑셀(.xlsx) 파일과 텍스트 인수증 영수증 파일을 자동 생성하여 백업함.  
PDF
+ 1

프로그램 창이 정상 작동 중이라면, 각 정형 데이터 필드 값을 클립보드 복사 및 Tab키 매크로 제어를 통해 전산 프로그램에 자동 주입함.  
PDF

입력 처리가 정상 완료되면 rpa_status = 'success', 에러 발생 시에는 'fail'로 마킹함.  
PDF
+ 1

6-6. [알림 보고 모듈] 개인화 알림 스케설러 엔진
RPA 모듈 동작 마감 후 setting_info의 use_notification 필드를 조회함. 'N'이면 알림 없이 즉시 프로세스 종료.  
PDF

'Y' 상태라면 알림 수신 번호를 확정함. 일차적으로 setting_info의 notification_phone_number를 조회하고, 비어있다면(NULL) 기본 안전장치로 member_info 테이블의 mobile_number를 지정함.  
PDF

DB에 저장된 문자열 템플릿 원본(rpa_success_message 또는 rpa_fail_message)을 읽어옴.  
PDF

문자열 내부의 {channel} 변수는 수집 채널 이름으로 치환하고, {count} 변수는 처리된 주문 건수로 실시간 교체하는 가공 함수를 구동함.  
PDF

최종 가공 완료된 메시지를 카카오 알림톡 또는 문자 발송 API 인프라로 토스하여 사장님 단말기로 실시간 보고서를 전송함.  
PDF

7. 디자인 가이드 (Design Guide)

트레이 아이콘 포맷: .ico 또는 투명도가 포함된 고해상도 .png 파일   
PDF

해상도 규격: 16x16 픽셀 및 32x32 픽셀 대응

기본 디자인 심볼: ggotAI 브랜드를 상징하는 이쁜 로봇 형태 적용

상태별 색상 시스템:

🟢 활성화 상태 (On): 상황판 작동 표시에 '녹색 원(Green Circle)' 적용.  
PDF

🔴 비활성화 상태 (Off): 상황판 작동 표시에 '빨간색 원(Red Circle)' 적용.  
PDF

⚠️ 경고 및 에러 상태 (Error): 상황판 해당 채널 글씨를 '빨간색 볼드(Red Bold)' 텍스트로 강조.

8. 제약 사항 (Constraints)
8-1. OS 및 실행 권한 제약: Windows OS 환경 전용 서비스로 개발되어야 하며, 시스템 SCM 제어 및 전산 프로그램 UI 돔 컨트롤을 위해 반드시 '윈도우 관리자 권한(Administrator Privileges)'으로 실행되어야 함.  
PDF

8-2. 데이터베이스 및 스토리지 동기화 제약: supabase-py 실시간 웹소켓 구독을 위해, Supabase 대시보드 내 server_call_history 테이블의 Realtime 소스 활성화(Replication) 설정이 선행되어야 함.  
PDF

8-3. AI 파이프라인 및 연산 자원 제약: 매장 PC의 자원 점유율을 최소화하기 위해 STT 가동 시 무조건 faster-whisper C++ 경량화 엔진을 사용해야 함.  
PDF

8-4. 웹 스크래핑 및 자동화(RPA) 제약: 다중 채널 진입점 충돌을 원천 차단하기 위해 파이썬 비동기 프레임워크의 asyncio.Lock()을 사용하여 RPA 진입점을 완벽한 싱글턴 순차 처리 구조로 제어해야 함.  
PDF
+ 1

8-5. Supabase 데이터베이스 테이블 빌드 제약 (4개 테이블 명세 포함):
AI는 데이터베이스 모델 클래스 및 SQL 스키마를 생성할 때 다음 4대 테이블의 신규/수정 구조 및 데이터 타입을 완벽하게 준수하여 스크립트를 작성해야 한다.  
PDF

① server_call_history (기존 테이블 수정)   
PDF

SQL
CREATE TABLE server_call_history (
    id SERIAL PRIMARY KEY,                         -- 고유 ID (자동 증가) [cite: 962, 963]
    channel_order VARCHAR(20) DEFAULT '기타',      -- 주문 수집 채널 ('핸드폰', '가게전화', '쇼핑몰', '인터라넷', '가게음성', '기타') [cite: 966]
    channel_classification VARCHAR(255) NOT NULL, -- 채널별 상세 정보 (전화번호, 쇼핑몰 주소, 인트라넷 주소 등) [cite: 967]
    shop_key INT NOT NULL,                         -- 꽃가게 고유 KEY (member_info 테이블의 id와 매핑) [cite: 968, 969]
    shop_name VARCHAR(50) NOT NULL,                -- 꽃가게 이름 [cite: 970, 971]
    customer_phone_number VARCHAR(20) DEFAULT '',  -- 전화를 건 '고객'의 전화번호 (쇼핑몰/인터라넷은 공백 문자) [cite: 972]
    customer_name VARCHAR(50) DEFAULT '신규',       -- 고객명 (전화번호부 연동명, 없을 시 '신규') [cite: 973]
    call_date DATE NOT NULL,                       -- 통화/수집 날짜 (YYYY-MM-DD) [cite: 974, 975]
    call_time TIME NOT NULL,                       -- 통화/수집 시간 (HH:mm:ss) [cite: 976, 977]
    duration_seconds INT DEFAULT 0,                -- 통화 시간(초 단위, 텍스트 채널은 0) [cite: 978, 979]
    audio_file_name VARCHAR(255) DEFAULT NULL,     -- 서버 스토리지에 저장된 음성 파일명 [cite: 980, 981]
    stt_text TEXT DEFAULT NULL,                    -- Whisper가 변환한 비정형 주문 텍스트 원본 (스크래핑 원문) [cite: 983, 984]
    is_order CHAR(1) DEFAULT 'N',                  -- Gemini가 판별한 최종 주문 여부 ('Y' 또는 'N') [cite: 985, 986]
    created_at TIMESTAMP DEFAULT NOW(),            -- 데이터 생성 일시 [cite: 987, 988]
    FOREIGN KEY (shop_key) REFERENCES member_info(id) ON DELETE CASCADE [cite: 989]
);
② order_details (★ 신규 생성)   
PDF

SQL
CREATE TABLE order_details (
    id SERIAL PRIMARY KEY,                         -- 고유 ID (자동 증가) [cite: 993]
    call_history_id INT NOT NULL,                  -- 수집 채널 이력 매핑 외래키 [cite: 994, 995]
    shop_key INT NOT NULL,                         -- 꽃가게 고유 KEY [cite: 996, 997]
    shop_name VARCHAR(50) NOT NULL,                -- 꽃가게 이름 [cite: 998, 999]
    customer_name VARCHAR(50) DEFAULT '신규',       -- 고객명 [cite: 1000, 1001]
    customer_phone_number VARCHAR(20) NOT NULL,    -- 고객전화번호 [cite: 1002, 1003]
    product_name VARCHAR(150) NOT NULL,            -- 상품명 [cite: 1004, 1005]
    quantity INT DEFAULT 1,                        -- 수량 [cite: 1006, 1007]
    price INT DEFAULT 0,                           -- 가격 [cite: 1008, 1009]
    delivery_at TIMESTAMP NOT NULL,                -- 배달일시 [cite: 1010, 1011]
    delivery_place VARCHAR(255) NOT NULL,          -- 배달장소 [cite: 1012, 1013]
    receiver_name VARCHAR(50) NOT NULL,            -- 받는사람 이름 [cite: 1014, 1015]
    receiver_phone_number VARCHAR(20) NOT NULL,    -- 받는사람 전화번호 [cite: 1016, 1017]
    ribbon_sender TEXT,                            -- 리본문구_보내는사람 [cite: 1018, 1019]
    ribbon_congratulations TEXT,                   -- 리본문구 경조사어 [cite: 1020, 1021]
    card_message TEXT,                             -- 카드메세지 [cite: 1022, 1023]
    rpa_status VARCHAR(20) DEFAULT 'ready',        -- RPA 처리 상태 ('ready', 'success', 'fail') 
    created_at TIMESTAMP DEFAULT NOW(),            -- 데이터 생성 일시 [cite: 1025]
    FOREIGN KEY (call_history_id) REFERENCES server_call_history(id) ON DELETE CASCADE [cite: 1027]
);
③ setting_info (★ 신규 생성)   
PDF

SQL
CREATE TABLE setting_info (
    id SERIAL PRIMARY KEY,
    shop_key INT NOT NULL UNIQUE,                        -- 꽃가게 고유 KEY (회원정보와 1:1 매핑) [cite: 1030, 1033]
    use_notification CHAR(1) DEFAULT 'Y',                -- 알림톡/문자 발송 여부 ('Y' 또는 'N') [cite: 1032, 1034]
    notification_phone_number VARCHAR(20) DEFAULT NULL,  -- 알림을 수신할 사장님 핸드폰 번호 [cite: 1035]
    rpa_success_message TEXT DEFAULT '{channel} 주문 {count}건 꽃가게 관리 프로그램에 입력 완료했습니다.', -- 성공 문구 [cite: 1036]
    rpa_fail_message TEXT DEFAULT '[ggotAI 경고] {channel} 주문 자동 입력 실패! 수동 확인 바랍니다.', -- 실패 경고 [cite: 1037, 1038]
    order_hp_1 VARCHAR(20) NOT NULL,                     -- 주문핸드폰1 (자동로그인용 기기 식별) [cite: 1040, 1041]
    order_hp_2 VARCHAR(20) DEFAULT NULL,                 -- 주문핸드폰2 [cite: 1042, 1043]
    order_landline_1 VARCHAR(20) DEFAULT NULL,           -- 주문일반전화1 [cite: 1044, 1045]
    order_landline_2 VARCHAR(20) DEFAULT NULL,           -- 주문일반전화2 [cite: 1046, 1047]
    shopping_mall_url VARCHAR(255) DEFAULT NULL,         -- 쇼핑몰 관리자주소 [cite: 1049, 1050]
    shopping_mall_id VARCHAR(50) DEFAULT NULL,           -- 쇼핑몰 아이디 [cite: 1051, 1052]
    shopping_mall_password VARCHAR(255) DEFAULT NULL,    -- 쇼핑몰 패스워드 (암호화 저장) [cite: 1054]
    intranet_url VARCHAR(255) DEFAULT NULL,              -- 인트라넷주소 [cite: 1053, 1057]
    intranet_id VARCHAR(50) DEFAULT NULL,                -- 인트라넷 아이디 [cite: 1055, 1058]
    intranet_password VARCHAR(255) DEFAULT NULL,         -- 인트라넷 패스워드 (암호화 저장) [cite: 1056, 1059]
    shopping_mall_check_interval INT DEFAULT 10,         -- 쇼핑몰 확인 간격 (분 단위) [cite: 1060]
    intranet_check_interval INT DEFAULT 30,              -- 인트라넷 확인 간격 (분 단위) [cite: 1061, 1062]
    created_at TIMESTAMP DEFAULT NOW()                   -- 생성 일시 [cite: 1063]
);
④ member_info (기존 테이블 수정)   
PDF

SQL
CREATE TABLE member_info (
    id SERIAL PRIMARY KEY,                         -- 고유 KEY값 (다른 테이블의 shop_key가 됨) [cite: 1067, 1068]
    username VARCHAR(50) NOT NULL UNIQUE,          -- 수동 아이디 [cite: 1069, 1070]
    password VARCHAR(255) NOT NULL,                -- 비밀번호 [cite: 1071, 1072]
    shop_name VARCHAR(50) NOT NULL,                -- 꽃집이름 [cite: 1073, 1074]
    representative_name VARCHAR(50) NOT NULL,      -- 대표자 [cite: 1075, 1076]
    landline_number VARCHAR(20) DEFAULT NULL,      -- 가게전화 [cite: 1077, 1078]
    mobile_number VARCHAR(20) NOT NULL,            -- 대표 핸드폰 번호 [cite: 1079, 1080]
    email VARCHAR(100) DEFAULT NULL,               -- 이메일 [cite: 1081, 1082]
    address VARCHAR(255) DEFAULT NULL,             -- 주소 [cite: 1083, 1084]
    address_detail VARCHAR(50) DEFAULT NULL,       -- 상세주소 [cite: 1085, 1086]
    is_approved CHAR(1) DEFAULT 'N',               -- 회원가입 승인 여부 ('Y' 또는 'N') [cite: 1087, 1088]
    created_at TIMESTAMP DEFAULT NOW()             -- 생성 일시 [cite: 1089]
);