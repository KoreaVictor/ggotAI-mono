-- ggotAI 통합 스키마 (ggotAIhp / ggotAIorder / ggotAIya 공용)
-- 라이브 Supabase(suylrznbctrkbxbleapb) 현재 구조와 일치하도록 재작성.
-- 설계 출처: ggotAIhp.pptx (Slide 4~6).

-- 회원정보 (id 가 다른 테이블의 shop_key 가 됨)
CREATE TABLE IF NOT EXISTS member_info (
    id                          SERIAL PRIMARY KEY,
    username                    VARCHAR(50)  NOT NULL UNIQUE,           -- 아이디
    password                    VARCHAR(255) NOT NULL,                  -- 비밀번호
    shop_name                   VARCHAR(50)  NOT NULL,                  -- 꽃집 이름
    representative_name         VARCHAR(50)  NOT NULL,                  -- 대표자
    landline_number             VARCHAR(20)  DEFAULT NULL,              -- 가게전화
    mobile_number               VARCHAR(20)  NOT NULL,                  -- 대표 핸드폰 번호 (기기 인증 키)
    email                       VARCHAR(100) DEFAULT NULL,
    address                     VARCHAR(255) DEFAULT NULL,
    address_detail              VARCHAR(50)  DEFAULT NULL,
    is_approved                 CHAR(1)      DEFAULT 'N',               -- 회원가입 승인 여부 ('Y'/'N')
    created_at                  TIMESTAMPTZ  DEFAULT timezone('utc', now()),
    remember_token_hash         TEXT         DEFAULT NULL,
    remember_token_expires_at   TIMESTAMPTZ  DEFAULT NULL
);

-- 히스토리_서버 (모든 주문 채널의 수집 환경 정보)
CREATE TABLE IF NOT EXISTS server_call_history (
    id                      SERIAL PRIMARY KEY,
    channel_order           VARCHAR(20)  DEFAULT '기타',               -- '핸드폰','가게전화','쇼핑몰','인터라넷','가게음성','기타'
    channel_classification  VARCHAR(255) NOT NULL,                     -- 채널별 상세 정보 (핸드폰: 기기 번호 / 쇼핑몰: 주소 등)
    shop_key                INT          NOT NULL,                     -- member_info.id
    shop_name               VARCHAR(50)  NOT NULL,
    customer_phone_number   VARCHAR(20)  DEFAULT '',                   -- 전화를 건 고객 번호 (텍스트 채널은 공백)
    customer_name           VARCHAR(50)  DEFAULT '신규',
    call_date               DATE         NOT NULL,
    call_time               TIME         NOT NULL,
    duration_seconds        INT          DEFAULT 0,
    audio_file_name         VARCHAR(255) DEFAULT NULL,
    stt_text                TEXT         DEFAULT NULL,                  -- Whisper STT 원본
    is_order                CHAR(1)      DEFAULT 'N',                   -- Gemini 판별 주문 여부
    created_at              TIMESTAMPTZ  DEFAULT timezone('utc', now()),
    CONSTRAINT fk_sch_shop FOREIGN KEY (shop_key) REFERENCES member_info(id) ON DELETE CASCADE
);

-- 주문내역 (Gemini 표준화 결과, ggotAIorder/ggotAIya 사용)
CREATE TABLE IF NOT EXISTS order_details (
    id                      SERIAL PRIMARY KEY,
    call_history_id         INT          NOT NULL,                     -- server_call_history.id
    shop_key                INT          NOT NULL,
    shop_name               VARCHAR(50)  NOT NULL,
    customer_name           VARCHAR(50)  DEFAULT '신규',
    customer_phone_number   VARCHAR(20)  NOT NULL,
    product_name            VARCHAR(150) NOT NULL,
    quantity                INT          DEFAULT 1,
    price                   INT          DEFAULT 0,
    delivery_at             TIMESTAMPTZ  NOT NULL,
    delivery_place          VARCHAR(255) NOT NULL,
    receiver_name           VARCHAR(50)  NOT NULL,
    receiver_phone_number   VARCHAR(20)  NOT NULL,
    ribbon_sender           TEXT,
    ribbon_congratulations  TEXT,
    card_message            TEXT,
    rpa_status              VARCHAR(20)  DEFAULT 'ready',              -- 'ready','success','fail'
    created_at              TIMESTAMPTZ  DEFAULT timezone('utc', now()),
    CONSTRAINT fk_od_call FOREIGN KEY (call_history_id) REFERENCES server_call_history(id) ON DELETE CASCADE
);

-- 환경정보 (회원정보와 1:1)
CREATE TABLE IF NOT EXISTS setting_info (
    id                              SERIAL PRIMARY KEY,
    shop_key                        INT          NOT NULL UNIQUE,      -- member_info.id (1:1)
    use_notification                CHAR(1)      DEFAULT 'Y',
    notification_phone_number       VARCHAR(20)  DEFAULT NULL,
    rpa_success_message             TEXT         DEFAULT '{channel} 주문 {count}건 꽃가게 관리 프로그램에 입력 완료했습니다.',
    rpa_fail_message                TEXT         DEFAULT '[ggotAI 경고] {channel} 주문 자동 입력 실패! 수동 확인 바랍니다.',
    order_hp_1                      VARCHAR(20)  NOT NULL,
    order_hp_2                      VARCHAR(20)  DEFAULT NULL,
    order_landline_1                VARCHAR(20)  DEFAULT NULL,
    order_landline_2                VARCHAR(20)  DEFAULT NULL,
    shopping_mall_url               VARCHAR(255) DEFAULT NULL,
    shopping_mall_id                VARCHAR(50)  DEFAULT NULL,
    shopping_mall_password          VARCHAR(255) DEFAULT NULL,
    intranet_url                    VARCHAR(255) DEFAULT NULL,
    intranet_id                     VARCHAR(50)  DEFAULT NULL,
    intranet_password               VARCHAR(255) DEFAULT NULL,
    shopping_mall_check_interval    INT          DEFAULT 10,
    intranet_check_interval         INT          DEFAULT 30,
    created_at                      TIMESTAMPTZ  DEFAULT timezone('utc', now()),
    CONSTRAINT fk_si_shop FOREIGN KEY (shop_key) REFERENCES member_info(id) ON DELETE CASCADE
);

-- 문자 인증 (회원가입/번호인증)
CREATE TABLE IF NOT EXISTS phone_verification (
    id                  BIGSERIAL PRIMARY KEY,
    phone               TEXT        NOT NULL,
    purpose             TEXT        NOT NULL,
    code_hash           TEXT        NOT NULL,
    expires_at          TIMESTAMPTZ NOT NULL,
    attempts            INT         NOT NULL DEFAULT 0,
    verified            BOOLEAN     NOT NULL DEFAULT FALSE,
    token_hash          TEXT        DEFAULT NULL,
    token_expires_at    TIMESTAMPTZ DEFAULT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
