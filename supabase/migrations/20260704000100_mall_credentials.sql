-- 스마트스토어(및 향후 쿠팡) 커머스API 연동: 자격증명 테이블 + order_details 발주확인 컬럼.
-- 설계서 2026-07-04-smartstore-commerce-api-design.md §6.

CREATE TABLE IF NOT EXISTS mall_credentials (
    id SERIAL PRIMARY KEY,
    shop_key INT NOT NULL,
    provider VARCHAR(20) NOT NULL,             -- 'smartstore' | 'coupang'
    client_id VARCHAR(255) NOT NULL,
    enc_client_secret TEXT NOT NULL,           -- core.crypto AES 암호문(iv_hex:ct_b64)
    extra JSONB DEFAULT '{}'::jsonb,           -- store_id 등 provider별 부가정보
    cursor TIMESTAMPTZ DEFAULT NULL,           -- last-changed 조회 커서
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(shop_key, provider),
    FOREIGN KEY (shop_key) REFERENCES member_info(id) ON DELETE CASCADE
);

ALTER TABLE order_details
    ADD COLUMN IF NOT EXISTS mall_ack_status VARCHAR(20) DEFAULT NULL,  -- NULL=비쇼핑몰, 'pending'|'confirmed'|'skipped'
    ADD COLUMN IF NOT EXISTS mall_ack_attempts INT DEFAULT 0;           -- 발주확인 재시도 카운트(상한용)
