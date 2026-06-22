-- order_details.sang_divi: AI(Gemini) 추출 상품분류 보관 컬럼
-- 파이프라인(extractor)이 STT 전체 맥락으로 FlowerNT 상품분류를 분류해 저장하고,
-- RPA(flowernt3.mapping.resolve_sang_divi)가 이 값을 우선 사용한다. 값이 없거나
-- 유효 옵션이 아니면 RPA가 기존 상품명 키워드 규칙(product_to_sang_divi)으로 폴백한다.
-- 따라서 nullable 이며 기존 행(NULL)은 자동으로 키워드 폴백 → 무중단·무퇴행.
-- 유효값: 축하화환/화분/쌀화환/근조화환/동양란/서양란/생화/과일바구니/축하오브제/근조오브제/기타

alter table order_details
  add column if not exists sang_divi varchar(20) default null;
