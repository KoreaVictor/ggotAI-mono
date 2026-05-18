# ggotAIhp 백엔드 설계 문서

**작성일:** 2026-05-18  
**프로젝트:** ggotAIhp (꽃가게 통화 자동화 앱 백엔드)  
**플랫폼:** Supabase (PostgreSQL + Edge Functions + Storage)  
**프로젝트 Ref:** `suylrznbctrkbxbleapb`

---

## 1. 아키텍처 개요

안드로이드 앱(프론트엔드)이 호출하는 RESTful API를 Supabase Edge Functions(Deno/TypeScript)로 구현한다. DB는 Supabase PostgreSQL, 오디오 파일 저장은 Supabase Storage를 사용한다. 별도 서버 인프라 없이 Supabase 단일 플랫폼으로 모든 백엔드 기능을 제공한다.

```
Android App
    │
    ├── GET  /functions/v1/verify-device   → Edge Function: verify-device
    │                                            └── member_info 테이블 조회
    │
    └── POST /functions/v1/upload-call     → Edge Function: upload-call
                                                ├── member_info 인증 검증
                                                ├── Supabase Storage (audio-files 버킷)
                                                └── server_call_history 테이블 INSERT
```

---

## 2. 데이터베이스 스키마

### 2-1. `member_info` 테이블

꽃가게 회원 정보 및 기기 인증용 테이블. 한 꽃가게당 최대 5개 핸드폰 번호 등록 가능.  
데이터 관리: Supabase 대시보드에서 직접 수동 입력/수정.

```sql
CREATE TABLE member_info (
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
```

**설계 결정:** `is_approved = 'Y'`인 경우에만 인증 통과. 관리자가 Supabase 대시보드에서 직접 승인.

### 2-2. `server_call_history` 테이블

앱에서 전송된 통화 이력 및 오디오 파일 메타데이터 저장 테이블.

```sql
CREATE TABLE server_call_history (
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
```

**설계 결정:** PRD의 `FOREIGN KEY (user_phone_number) REFERENCES member_info(mobile_1)` 제약은 적용하지 않는다. `user_phone_number`가 `mobile_2~5`에도 해당할 수 있어 DB 레벨 FK 제약이 구조적으로 불가능하다. 대신 `upload-call` Edge Function에서 애플리케이션 레벨 인증 검증으로 대체한다.

---

## 3. API 엔드포인트 명세

**Base URL:** `https://suylrznbctrkbxbleapb.supabase.co/functions/v1`

### 3-1. 기기 인증 API

```
GET /verify-device?phone={phone}
```

| 항목 | 내용 |
|---|---|
| 파라미터 | `phone` (String, Required): 하이픈 제외 숫자만 (예: `01012345678`) |
| 인증 필요 | 없음 |

**처리 로직:**
1. `phone`으로 `member_info`의 `mobile_1~5` 전체를 OR 조건으로 검색
2. 매칭 행의 `is_approved = 'Y'` 확인
3. 성공 시 `shop_name`, `representative_name` 반환

**응답 (200 OK - 성공):**
```json
{
  "status": "success",
  "data": {
    "shop_name": "서울플라워",
    "representative_name": "홍길동",
    "is_approved": "Y"
  }
}
```

**응답 (401 - 미등록/미승인):**
```json
{
  "status": "error",
  "error_code": "AUTH_ERR",
  "message": "등록되지 않거나 승인되지 않은 단말기입니다."
}
```

---

### 3-2. 통화 이력 및 녹음 파일 업로드 API

```
POST /upload-call
Content-Type: multipart/form-data
```

| 필드명 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `user_phone_number` | String | Y | 기기 자체 번호 (하이픈 제외) |
| `phone_number` | String | Y | 고객 번호 |
| `customer_name` | String | N | 고객명 (기본값: '신규') |
| `call_date` | String | Y | YYYY-MM-DD |
| `call_time` | String | Y | HH:mm:ss |
| `duration_seconds` | Integer | N | 통화 시간(초) |
| `audio_file` | File | Y | .wav 오디오 파일 |

**처리 로직:**
1. `user_phone_number`로 `member_info` 인증 검증 (미인증 시 401 반환)
2. `audio_file`을 Supabase Storage `audio-files` 버킷에 저장
   - 경로: `{user_phone_number}/{YYYYMM}/{파일명}.wav`
   - 파일명 규칙: `{user_phone}_{customer_phone}_{YYYYMMDD}_{HHmmss}.wav`
3. 메타데이터를 `server_call_history` 테이블에 INSERT
4. 성공 응답 반환

**응답 (200 OK - 성공):**
```json
{
  "status": "success",
  "message": "업로드 성공"
}
```

**응답 (500 - 서버 오류):**
```json
{
  "status": "error",
  "error_code": "SERVER_500",
  "message": "내부 서버 오류"
}
```

---

## 4. Supabase Storage 설정

- **버킷명:** `audio-files`
- **접근 정책:** 비공개(private) — 서명된 URL(Signed URL)로만 접근
- **파일 경로 구조:** `{user_phone_number}/{YYYYMM}/{파일명}.wav`
- **용도:** 안드로이드 앱의 음성 재생 시 서명 URL 발급하여 접근

---

## 5. 프로젝트 파일 구조

```
ggotAIhp/
├── supabase/
│   ├── functions/
│   │   ├── verify-device/
│   │   │   └── index.ts          # 기기 인증 Edge Function
│   │   └── upload-call/
│   │       └── index.ts          # 업로드 Edge Function
│   └── migrations/
│       └── 20260518000000_init.sql   # DB 테이블 생성 마이그레이션
├── .env                          # 실제 환경변수 (git 제외)
├── .env.example                  # 환경변수 템플릿
├── .mcp.json                     # Supabase MCP 설정
└── .gitignore
```

---

## 6. 에러 코드 규격

| 에러 코드 | HTTP 상태 | 설명 |
|---|---|---|
| `AUTH_ERR` | 401 | 미등록 또는 미승인 기기 |
| `SERVER_500` | 500 | 내부 서버 오류 |
| `FILE_NOT_FOUND` | 400 | 오디오 파일 누락 |

모든 응답은 `{ "status": "success"|"error", ... }` 포맷을 따른다.  
CORS 헤더: `Access-Control-Allow-Origin: *` (안드로이드 앱 요청 허용)

---

## 7. 미구현 범위 (2단계 예정)

- `stt_text`: Whisper STT 변환 (현재 NULL 유지)
- `is_order`: FoaSys 주문 여부 판별 (현재 'N' 고정)
- 관리자 API (`POST /admin/members`)
