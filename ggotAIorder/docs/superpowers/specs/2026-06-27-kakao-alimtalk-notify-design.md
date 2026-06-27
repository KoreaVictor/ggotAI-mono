# 카카오톡 알림톡(iwinv) 발송 — 설계

작성일: 2026-06-27

## 목표

RPA가 FlowerNT에 주문을 저장 성공하면 꽃가게 사장님 카카오톡으로
"주문접수 N건" 알림을 발송한다. 성공/수동입력필요(manual)/실패(fail) 3가지
RPA 결과를 각각 알림으로 보낸다.

## 배경 / 현재 상태

- 발송 수단: **iwinv 알림톡** (건당 5.3~6.5원). 솔라피·카카오 메모 API는 거부됨(비용/토큰관리).
- 카카오 채널 비즈니스 인증 **승인 완료**(2026-06-27).
- 남은 선행 절차(iwinv 콘솔): 메시지 서비스 신청 → 발신프로필(@채널) 연결 →
  템플릿 등록·검수(2~3영업일) → 승인 후 `templateCode` 확보.
- 템플릿 범위: success/manual/fail **3개 모두 검수 요청**. SMS 대체발송은 사용 안 함.

### 기존 코드 (확인됨)

호출 체인:
`rpa/singleton_macro.py::_default_notify` → `notifier/sms_sender.py::send()`
→ `notifier/provider.py::NotificationProvider.send_message()`

- `send()`가 이미 처리: `setting_info.use_notification` 체크, 수신번호 결정
  (`notification_phone_number ?? member_info.mobile_number`), outcome 분기
  (success/manual/fail → rpa_success/manual/fail_message), `{channel}`/`{count}` 렌더.
- `provider.send_message(to, text)`는 **자유 텍스트** 계약. `HttpNotificationProvider`는 골격.
- `singleton_macro`는 주문 1건당 `count=1`로 호출.

### iwinv 발송 API (확인됨)

- 엔드포인트: `POST https://biz.service.iwinv.kr/api/send/`
- 헤더: `Content-Type: application/json;charset=UTF-8`, `AUTH: base64(API Key)`
- body 필수: `templateCode`, `list`(수신자 배열, 최대 1000) — 각 항목 `{ phone, templateParam }`
- **변수 전달 방식: 렌더된 텍스트가 아니라 변수값을 전달**, 서버가 템플릿의 `#{항목}`에 매칭.
- SMS 대체발송: `reSend`(Y/N), `resendType`, `resendContent` — 본 설계는 `reSend="N"`.

> 미확정: 발신프로필이 계정에 귀속되어 senderKey를 body로 안 넘겨도 되는지 여부는
> 구현 착수 시 실제 API 응답으로 확정한다(필요 시 `IWINV_SENDER_KEY` env 추가).

## 결정: 인터페이스 확장 (접근법 A)

`NotificationProvider` 계약을 다음으로 확장한다:

```python
def send_message(
    self, to: str, text: str, *,
    template_code: str | None = None,
    variables: dict[str, str] | None = None,
) -> None: ...
```

- `HttpNotificationProvider`(레거시): `text`만 사용, 새 키워드 인자는 무시.
- `KakaoIwinvProvider`(신규): `template_code` + `variables` 사용, `text`는 사용 안 함.

거부한 대안: B) 별도 `send_template()` 메서드 — `send()`가 provider 종류를 분기해야 해 추상화가 샘.
C) `send(Message)` 객체 통일 — 현 규모엔 과설계(YAGNI).

## 컴포넌트 구조

```
notifier/
  provider.py
    NotificationProvider (Protocol)   ← send_message(to, text, *, template_code, variables)
    HttpNotificationProvider          ← 기존 골격 유지 (text만 사용)
    KakaoIwinvProvider      [신규]    ← template_code + variables → iwinv /api/send/ 호출
    make_provider()         [신규]    ← env(NOTIFY_PROVIDER)로 provider 선택 팩토리
  sms_sender.py
    send()                            ← outcome→template_code 해석 + variables dict 구성 추가
  repository.py                       ← 변경 없음
```

- `KakaoIwinvProvider`는 한 가지 책임: `to`/`template_code`/`variables`로 iwinv 호출.
  `IWINV_API_KEY` 미설정 시 `RuntimeError`.
- `make_provider()`가 `send()`의 기본 provider 생성을 담당
  (`NOTIFY_PROVIDER=iwinv` → iwinv, 그 외 → `HttpNotificationProvider`).

## 데이터 흐름

```
RPA 저장 성공 (singleton_macro)
 → _default_notify(order, outcome="success")
 → notifier_send(shop_key, channel, count=1, outcome="success")
 → sms_sender.send(...):
      1. repo.get_settings(shop_key)
      2. use_notification != "Y"           → 스킵
      3. recipient 결정, 없으면             → 스킵
      4. template_code = _template_code_for(outcome)   # 신규: env에서 outcome별 코드
      5. template_code 없음                 → 스킵(로그)  # success-only 단계 안전장치
      6. variables = {"건수": str(count)}   # 신규
      7. text = render_template(...)        # 레거시/로그용 유지
      8. provider.send_message(recipient, text,
                               template_code=template_code, variables=variables)
 → KakaoIwinvProvider:
      POST /api/send/  { templateCode, list:[{phone, templateParam:{"건수":"1"}}], reSend:"N" }
      2xx & 응답 성공코드 확인 → OK / 아니면 raise
```

`variables` 키(`"건수"`)는 iwinv 템플릿의 `#{건수}` 이름과 **정확히 일치**해야 한다(계약점).

## 환경설정(env)

| env | 값 | 비고 |
|---|---|---|
| `NOTIFY_PROVIDER` | `iwinv` | 미설정/`http`면 기존 Http 골격 |
| `IWINV_API_KEY` | iwinv API 인증키 | 헤더 `AUTH = base64(이 값)` |
| `IWINV_TEMPLATE_CODE_SUCCESS` | 승인된 성공 템플릿 코드 | 먼저 확보 |
| `IWINV_TEMPLATE_CODE_MANUAL` | manual 템플릿 코드 | 승인 후, 없으면 스킵 |
| `IWINV_TEMPLATE_CODE_FAIL` | fail 템플릿 코드 | 승인 후, 없으면 스킵 |

(필요 시 `IWINV_SENDER_KEY` — 구현 착수 시 API로 확정)

## 템플릿 변수 계약 (승인 후 변경 불가 — 확정됨)

| outcome | iwinv 템플릿 문구 | 변수 | templateParam |
|---|---|---|---|
| success | `주문접수 #{건수}건` | `건수` | `{"건수":"1"}` |
| manual | `[주문] #{건수}건 — 관리 프로그램에 직접 입력해 주세요` | `건수` | `{"건수":"1"}` |
| fail | `[주문] 자동등록 실패 #{건수}건 — 확인 필요` | `건수` | `{"건수":"1"}` |

- 변수 이름은 **`건수`로 통일**(코드 dict 키와 일치).
- `count=1` 고정이지만 변수로 두어 향후 묶음발송 대비.
- `channel`은 MVP 템플릿에서 제외(검수 단순화). 필요 시 `#{채널}`로 후속 추가.

## 에러 처리

원칙: **알림 실패가 RPA 본류를 막지 않는다.**

| 상황 | 처리 |
|---|---|
| `IWINV_API_KEY` 미설정 | provider `RuntimeError` → `send()` try/except 로그, RPA 정상 진행 |
| outcome에 template_code 없음 | 발송 시도 안 함, info 로그 후 스킵 |
| iwinv 2xx 아님 / 실패코드 | `send_message` raise → `send()`가 `logger.exception`, `False` |
| 네트워크 타임아웃 | httpx `timeout=10.0`, 예외 동일 처리 |
| 수신번호/use_notification 문제 | 기존 로직 유지(스킵+경고) |

- 전화번호는 기존 `_mask()`로 마스킹 로그. iwinv 응답 본문은 실패 시에만 로그.
- 재시도 없음(MVP).

## 테스트 (httpx 목, 실발송 없음)

1. `KakaoIwinvProvider.send_message`
   - `AUTH` 헤더가 `base64(API_KEY)`
   - body `templateCode`, `list[0].phone`, `list[0].templateParam == {"건수":"1"}`, `reSend=="N"`
   - 2xx 실패코드 응답 시 raise
   - `IWINV_API_KEY` 미설정 시 `RuntimeError`
2. `sms_sender.send` (가짜 provider 주입)
   - outcome=success → 올바른 template_code/variables로 호출
   - template_code 없는 outcome → 호출 안 됨, `False`
   - `use_notification=N` / 수신번호 없음 → 기존 스킵 유지
3. `make_provider()` — `NOTIFY_PROVIDER=iwinv`→iwinv, 그 외→Http

라이브 검증(템플릿 승인 후 별도): 본인 번호로 success 1건 실발송 → 카톡 수신 + 로그 `알림 발송 성공` 확인.

## 범위 밖 (YAGNI)

- SMS 대체발송, 발송 재시도/큐, channel 변수, 묶음(count>1) 발송 UI, 발신프로필 자동등록.
