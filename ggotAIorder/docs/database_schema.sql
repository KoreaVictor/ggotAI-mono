-- ==========================================
-- ggotAIorder Supabase Database Schema DDL
-- Created: 2026-06-01
-- Description: PRD 요구사항을 100% 만족하는 4대 기본 테이블 스키마 정의
-- ==========================================

-- 1. member_info (기존 테이블 수정 / 회원정보 및 꽃가게 마스터 테이블)
CREATE TABLE IF NOT EXISTS member_info (
    id SERIAL PRIMARY KEY,                         -- 고유 KEY값 (다른 테이블의 shop_key가 됨)
    username VARCHAR(50) NOT NULL UNIQUE,          -- 로그인 아이디
    password VARCHAR(255) NOT NULL,                -- 비밀번호
    shop_name VARCHAR(50) NOT NULL,                -- 꽃집이름
    representative_name VARCHAR(50) NOT NULL,      -- 대표자 성명
    landline_number VARCHAR(20) DEFAULT NULL,      -- 가게 일반전화 번호
    mobile_number VARCHAR(20) NOT NULL,            -- 대표 사장님 핸드폰 번호 (알림 안전장치용)
    email VARCHAR(100) DEFAULT NULL,               -- 이메일 주소
    address VARCHAR(255) DEFAULT NULL,             -- 주소
    address_detail VARCHAR(50) DEFAULT NULL,       -- 상세주소
    is_approved CHAR(1) DEFAULT 'N',               -- 회원가입 승인 여부 ('Y' 또는 'N')
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW())
);

-- 2. server_call_history (기존 테이블 수정 / 비정형 주문 채널별 수집 이력 테이블)
CREATE TABLE IF NOT EXISTS server_call_history (
    id SERIAL PRIMARY KEY,                         -- 고유 ID (자동 증가)
    channel_order VARCHAR(20) DEFAULT '기타',      -- 주문 수집 채널 ('핸드폰', '가게전화', '쇼핑몰', '인터라넷', '가게음성', '기타')
    channel_classification VARCHAR(255) NOT NULL, -- 채널별 상세 정보 (전화번호, 쇼핑몰 주소, 인트라넷 주소 등)
    shop_key INT NOT NULL,                         -- 꽃가게 고유 KEY (member_info 테이블의 id와 매핑)
    shop_name VARCHAR(50) NOT NULL,                -- 꽃가게 이름
    customer_phone_number VARCHAR(20) DEFAULT '',  -- 전화를 건 '고객'의 전화번호 (쇼핑몰/인터라넷은 공백 문자)
    customer_name VARCHAR(50) DEFAULT '신규',       -- 고객명 (전화번호부 연동명, 없을 시 '신규')
    call_date DATE NOT NULL,                       -- 통화/수집 날짜 (YYYY-MM-DD)
    call_time TIME NOT NULL,                       -- 통화/수집 시간 (HH:mm:ss)
    duration_seconds INT DEFAULT 0,                -- 통화 시간(초 단위, 텍스트 채널은 0)
    audio_file_name VARCHAR(255) DEFAULT NULL,     -- 서버 스토리지에 저장된 음성 파일명
    stt_text TEXT DEFAULT NULL,                    -- Whisper가 변환한 비정형 주문 텍스트 원본 (스크래핑 원문)
    is_order CHAR(1) DEFAULT 'N',                  -- Gemini가 판별한 최종 주문 여부 ('Y' 또는 'N')
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL, -- 파이프라인 종결(Y/N) 시각. NULL=미처리(catch-up 대상)
    process_attempts INT NOT NULL DEFAULT 0,            -- 처리 시도 횟수(영구 실패 행의 무한 재시도 차단용)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()),
    FOREIGN KEY (shop_key) REFERENCES member_info(id) ON DELETE CASCADE
);

-- 3. order_details (신규 생성 / AI 정형화 완료 최종 주문 데이터 테이블)
CREATE TABLE IF NOT EXISTS order_details (
    id SERIAL PRIMARY KEY,                         -- 고유 ID (자동 증가)
    call_history_id INT NOT NULL,                  -- 수집 채널 이력 매핑 외래키
    shop_key INT NOT NULL,                         -- 꽃가게 고유 KEY
    shop_name VARCHAR(50) NOT NULL,                -- 꽃가게 이름
    customer_name VARCHAR(50) DEFAULT '신규',       -- 고객명
    customer_phone_number VARCHAR(20) NOT NULL,    -- 고객전화번호
    product_name VARCHAR(150) NOT NULL,            -- 상품명
    quantity INT DEFAULT 1,                        -- 수량
    price INT DEFAULT 0,                           -- 가격
    delivery_at TIMESTAMP WITH TIME ZONE NOT NULL, -- 배달일시 (파싱된 ISO 시각, 불명확 시 센티넬)
    delivery_at_text VARCHAR(100) DEFAULT NULL,    -- 배달일시 원본 문구 (말한 그대로, 예: '내일 오후 3시')
    delivery_place VARCHAR(255) NOT NULL,          -- 배달장소 (인증 배송지)
    receiver_name VARCHAR(50) NOT NULL,            -- 받는사람 이름
    receiver_phone_number VARCHAR(20) NOT NULL,    -- 받는사람 전화번호
    ribbon_sender TEXT,                            -- 리본문구_보내는사람
    ribbon_congratulations TEXT,                   -- 리본문구_경조사어
    card_message TEXT,                             -- 카드메세지 내용
    rpa_status VARCHAR(20) DEFAULT 'ready',        -- RPA 처리 상태 ('ready', 'success', 'manual'=미구동→백업/수동입력, 'fail')
    rpa_attempts INTEGER NOT NULL DEFAULT 0,       -- manual 자동재시도 횟수(상한 retry.RPA_MAX_ATTEMPTS 초과 시 수동입력으로 남김)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()),
    FOREIGN KEY (call_history_id) REFERENCES server_call_history(id) ON DELETE CASCADE
);

-- 4. setting_info (신규 생성 / 꽃집별 주문 수집 환경 및 계정 정보 테이블)
CREATE TABLE IF NOT EXISTS setting_info (
    id SERIAL PRIMARY KEY,
    shop_key INT NOT NULL UNIQUE,                        -- 꽃가게 고유 KEY (회원정보와 1:1 매핑)
    use_notification CHAR(1) DEFAULT 'Y',                -- 알림톡/문자 발송 여부 ('Y' 또는 'N')
    notification_phone_number VARCHAR(20) DEFAULT NULL,  -- 알림을 수신할 사장님 핸드폰 번호 (NULL일 경우 member_info의 mobile_number 조회)
    rpa_success_message TEXT DEFAULT '{channel} 주문 {count}건 꽃가게 관리 프로그램에 입력 완료했습니다.', -- 성공 알림 문구
    rpa_manual_message TEXT DEFAULT '[ggotAI] {channel} 주문 {count}건 접수 — 관리 프로그램에 직접 입력해 주세요.', -- 백업(수동입력 필요) 안내 문구
    rpa_fail_message TEXT DEFAULT '[ggotAI 경고] {channel} 주문 자동 입력 실패! 수동 확인 바랍니다.', -- 실패 경고 알림 문구
    order_hp_1 VARCHAR(20) NOT NULL,                     -- 주문핸드폰1 (자동로그인용 기기 식별)
    order_hp_2 VARCHAR(20) DEFAULT NULL,                 -- 주문핸드폰2
    order_landline_1 VARCHAR(20) DEFAULT NULL,           -- 주문일반전화1
    order_landline_2 VARCHAR(20) DEFAULT NULL,           -- 주문일반전화2
    shopping_mall_url VARCHAR(255) DEFAULT NULL,         -- 쇼핑몰 관리자 페이지 주소
    shopping_mall_id VARCHAR(50) DEFAULT NULL,           -- 쇼핑몰 아이디
    shopping_mall_password VARCHAR(255) DEFAULT NULL,    -- 쇼핑몰 패스워드 (프론트 단에서 대칭키 암호화 저장)
    intranet_url VARCHAR(255) DEFAULT NULL,              -- 타지역 연합 인트라넷 주소
    intranet_id VARCHAR(50) DEFAULT NULL,                -- 인트라넷 아이디
    intranet_password VARCHAR(255) DEFAULT NULL,         -- 인트라넷 패스워드 (프론트 단에서 대칭키 암호화 저장)
    shopping_mall_check_interval INT DEFAULT 10,         -- 쇼핑몰 확인 정기 폴링 주기 (분 단위)
    intranet_check_interval INT DEFAULT 30,              -- 인트라넷 확인 정기 폴링 주기 (분 단위)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()),
    FOREIGN KEY (shop_key) REFERENCES member_info(id) ON DELETE CASCADE
);

-- 인덱스 추가 (조회 성능 최적화 및 외래키 조회 속도 강화)
CREATE INDEX IF NOT EXISTS idx_call_history_shop ON server_call_history(shop_key);
CREATE INDEX IF NOT EXISTS idx_order_details_history ON order_details(call_history_id);
CREATE INDEX IF NOT EXISTS idx_order_details_shop ON order_details(shop_key);
