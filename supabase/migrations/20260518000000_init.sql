CREATE TABLE IF NOT EXISTS member_info (
    id                      SERIAL PRIMARY KEY,
    shop_name               VARCHAR(100) NOT NULL,
    representative_name     VARCHAR(50)  NOT NULL,
    landline_number         VARCHAR(20),
    mobile_1                VARCHAR(20)  NOT NULL UNIQUE,
    mobile_2                VARCHAR(20)  DEFAULT NULL,
    mobile_3                VARCHAR(20)  DEFAULT NULL,
    mobile_4                VARCHAR(20)  DEFAULT NULL,
    mobile_5                VARCHAR(20)  DEFAULT NULL,
    business_number         VARCHAR(50),
    address                 VARCHAR(255),
    is_approved             CHAR(1)      DEFAULT 'N',
    is_subscribed           CHAR(1)      DEFAULT 'N',
    subscription_type       VARCHAR(20)  DEFAULT NULL,
    free_trial_start_date   DATE,
    current_free_trial_days INT          DEFAULT 0,
    email                   VARCHAR(100),
    created_at              TIMESTAMP    DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS server_call_history (
    id                  SERIAL PRIMARY KEY,
    user_phone_number   VARCHAR(20)  NOT NULL,
    shop_name           VARCHAR(100) NOT NULL,
    phone_number        VARCHAR(20)  NOT NULL,
    customer_name       VARCHAR(50)  DEFAULT '신규',
    call_date           DATE         NOT NULL,
    call_time           TIME         NOT NULL,
    duration_seconds    INT,
    audio_file_name     VARCHAR(255) NOT NULL,
    stt_text            TEXT         DEFAULT NULL,
    is_order            CHAR(1)      DEFAULT 'N',
    created_at          TIMESTAMP    DEFAULT NOW()
);
