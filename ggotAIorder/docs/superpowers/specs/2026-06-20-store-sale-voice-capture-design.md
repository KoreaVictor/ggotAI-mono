# 매장판매 음성수집 (가게음성 채널) — 설계

- 작성일: 2026-06-20
- 대상: ggotAIhp(안드로이드) + Supabase `upload-call` 엣지함수
- 범위: **Phase 1 — "매장판매" 버튼 탭 녹음 수집**. 음성호출("꽃아이야 매장판매 입력해줘")은 Phase 2로 분리.

## 1. 배경 / 문제

`가게음성` 채널은 하류(처리·표시·RPA)가 모두 배선돼 있으나 **수집(server_call_history INSERT) 경로가 없다**. 현재 인입은 핸드폰(`upload-call`), 가게전화(`/api/v1/gate-phone/upload`), 인터라넷(크롤러)뿐이다.

목표: 사장님이 매장에서 직접 받은 주문(전화 아닌 대면/즉석 주문 등)을 **음성으로 말하면** 핸드폰과 동일한 파이프라인으로 수집·전산입력한다.

핵심 통찰: 핸드폰과 가게음성은 본질적으로 **"음성 → STT → Gemini 추출 → order_details → RPA"** 동일 파이프라인이다. 따라서 수집 경로도 핸드폰(`upload-call`)을 재사용하고 **채널만 태깅**한다.

## 2. 사용자 흐름 (Phase 1)

1. 사장님이 ggotAIhp 메인 화면에서 **"매장판매"** 버튼을 탭한다.
2. 녹음 화면이 열리고 즉시 녹음을 시작한다(큰 ● 녹음중 / ■ 종료 버튼 + 경과시간).
3. 사장님이 주문 내용을 음성으로 말한다.
4. 종료 규칙:
   - **탭 종료(기본)**: ■ 버튼을 누르면 즉시 종료·전송.
   - **무음 자동종료(안전망)**: 말이 끝나고 **5초** 무음이 지속되면 자동 종료·전송(탭을 깜빡한 경우 대비).
   - **최대 길이(최후 안전장치)**: **2분** 도달 시 자동 종료.
   - **취소(너무 짧음/무음)**: 녹음 길이 < 1.5초이거나 유효 발화가 감지되지 않으면 전송하지 않고 "녹음이 짧아 취소되었습니다" 안내.
5. 종료 즉시 **확인 절차 없이 전송**(바쁜 매장 우선). 성공 시 TTS "매장판매 주문이 접수되었습니다."
6. 이후 STT→Gemini→RPA는 기존 파이프라인이 처리하고, ggotAIya 상황판 `가게음성` 카드/피드에 표시된다.

기본값(무음 5초 / 최대 2분 / 최소 1.5초)은 조정 가능한 상수로 둔다.

## 3. 아키텍처 / 컴포넌트

### 3.1 안드로이드 (ggotAIhp)

| 컴포넌트 | 역할 | 신규/변경 |
|---|---|---|
| `MainActivity` 매장판매 버튼 | 녹음 화면 진입 | 변경 |
| 녹음 화면(액티비티 또는 다이얼로그) | ●/■ 버튼, 경과시간, 취소 | 신규 |
| `StoreSaleRecorder` | `MediaRecorder`(AAC/.m4a) 시작/종료 + 진폭 폴링 기반 무음감지 + 길이상한 | 신규 |
| `RecordingStopDecider` (순수 로직) | (경과시간, 최근 무음지속, 최대상한) → 종료/취소 사유 판정 — **단위테스트 대상** | 신규 |
| `CallHistory` 엔티티/DAO | `channelOrder` 컬럼 추가(기본 `"핸드폰"`), 매장판매는 `"가게음성"` | 변경(Room v3→v4) |
| `UploadManager` | 업로드 시 `channelOrder` 전달 | 변경 |
| `ApiService`/`RetrofitClient` | `upload-call` 멀티파트에 `channel_order` 파트 추가 | 변경 |
| `AndroidManifest` + 런타임 권한 | `RECORD_AUDIO` 추가·요청 | 변경 |

설계 원칙:
- **기존 통화녹음 흐름(삼성 녹음파일 탐색)은 그대로 둔다.** 매장판매는 별도의 인앱 녹음 경로이며, 산출물(오디오 파일 + `CallHistory`)을 만든 뒤부터는 **기존 업로드/재전송 경로를 재사용**한다(오프라인 자동 재전송, 401 승인취소 처리 등 무상속 재구현 없음).
- 녹음 포맷은 AAC/.m4a(삼성 통화녹음과 동일 계열) — 서버 STT(Groq/whisper)가 그대로 처리.
- `StoreSaleRecorder`는 안드로이드 API에 의존하므로, **종료 판정 로직만 `RecordingStopDecider` 순수 함수로 분리**해 JVM 단위테스트한다.

### 3.2 서버 (Supabase `upload-call` 엣지함수) — 접근 ①

- 멀티파트에 **선택적 `channel_order`** 필드 수신.
- 화이트리스트 `{'핸드폰','가게음성'}`. 없거나 미허용 값이면 **기본 `'핸드폰'`**(기존 ggotAIhp 무손상, 하위호환).
- INSERT 시 해당 `channel_order` 사용. 매장판매는 `customer_phone_number=''`(발신번호 없음), `channel_classification=user_phone_number`(기기) 유지.
- 인증(기기번호 verify), Storage 적재, `server_call_history` INSERT 로직은 그대로 재사용.

### 3.3 백엔드 파이프라인 — 변경 없음

- 리스너가 이미 `가게음성`을 실시간 처리(`REALTIME_CHANNELS = {"핸드폰","가게음성"}`).
- RPA 매핑도 존재(`가게음성 → 매장`, `rpa/flowernt3/mapping.py`).
- 상황판 `가게음성` 카드/피드도 기존 그대로 동작.

## 4. 데이터 흐름

```
[사장님] 매장판매 탭 → 음성 주문 → 종료(탭 / 무음5초 / 최대2분)
   ↓ 앱: CallHistory(channelOrder='가게음성', 발신번호 없음) insert
   ↓ UploadManager → upload-call (channel_order='가게음성' + audio 멀티파트)
[엣지] 기기 인증 → Storage 적재 → server_call_history INSERT(channel_order='가게음성')
   ↓ Realtime 리스너(shop_key 필터)
[백엔드] STT(Groq) → Gemini 11필드 추출 → order_details(rpa_status='ready') → RPA 자동입력(FlowerNT3 '매장')
   ↓
[ggotAIya 상황판] '가게음성' 채널 카드 + 실시간 주문 피드
```

## 5. 인터페이스 변경 요약

- `upload-call` 멀티파트: `+ channel_order: string`(선택, 기본 `'핸드폰'`, 허용값 `핸드폰|가게음성`).
- `ApiService.uploadCall(...)`: `+ @Part("channel_order") channelOrder: RequestBody`.
- `CallHistory`: `+ channelOrder: String = "핸드폰"` (Room migration v3→v4, 기존 행 기본값 '핸드폰').
- `UploadManager.uploadOnce`: `history.channelOrder`를 멀티파트로 전달.

## 6. 에러 처리

- 마이크 권한 거부 → 권한 안내 후 녹음 중단(전송 없음).
- 녹음 파일 없음/너무 짧음/무음 → 전송 없이 취소 안내.
- 오프라인/업로드 실패/승인취소(401) → **기존 `UploadManager` 경로 재사용**: `markFailed` + 네트워크 복구 시 자동 재전송, 401은 수집 중단(`DeviceStatus.markRevoked`).
- 서버 미허용 `channel_order` → 거부하지 않고 기본 `'핸드폰'`로 안전 폴백.

## 7. 테스트 계획

- **안드로이드 단위(JVM)**: `RecordingStopDecider`(무음/상한/취소 판정), `CallHistory` 마이그레이션 v3→v4(기존 행 channelOrder='핸드폰' 보존), `UploadManager`가 channelOrder 전달.
- **엣지함수**: `channel_order` 미전송→`핸드폰`, `가게음성` 반영, 미허용값→폴백, 발신번호 빈값 처리.
- **백엔드**: 기존 `가게음성` 리스너/파이프라인 테스트로 커버(추가 회귀 확인).
- **수기 E2E**: 실기기에서 매장판매 녹음→상황판 피드·`order_details`·RPA 입력 확인.

## 8. 비목표 (Phase 1)

- 음성호출("꽃아이야 매장판매 입력해줘") 상시청취 = **Phase 2**(별도 스펙).
- 인앱 주문 편집/확인 단계 없음(즉시 전송).
- STT/Gemini/RPA 로직 변경 없음.

## 9. 의존성 / 위험

- `RECORD_AUDIO` 런타임 권한 거부 시 기능 불가 → 최초 진입 시 안내.
- 매장 소음 환경의 STT 정확도는 기존 핸드폰 채널과 동일 수준(별도 개선은 범위 외).
- Room 마이그레이션은 데이터 보존(파괴적 마이그레이션 금지) — 기존 통화 이력 무손상.
