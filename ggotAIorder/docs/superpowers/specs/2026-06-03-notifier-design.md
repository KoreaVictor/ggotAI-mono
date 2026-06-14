# notifier (개인화 알림 발송) 실구현 설계서

작성일: 2026-06-03
범위: `notifier/sms_sender.py` 스텁을 실구현으로 — 설정 조회 → 수신번호 결정 → 템플릿 치환 → 제공사 추상화 발송. 실 발송(제공사 계정)은 연기.
기준 브랜치: master (PR #4 머지 완료), 작업 브랜치 `feature/notifier`.

---

## 1. 목표와 범위

PRD 6-6/F9(개인화 결과 보고 알림)를 구현한다. RPA 처리 후 `setting_info`를 조회해 알림 발송 여부·수신번호·템플릿을 결정하고, `{channel}`/`{count}`를 치환해 발송한다.

- **포함(실로직, 오프라인 테스트)**: `use_notification` 판별, 수신번호 결정(notification_phone_number ?? member_info.mobile_number), 성공/실패 템플릿 선택·치환, 제공사 추상화 발송, 결과 로깅(이력).
- **연기(라이브/체크리스트)**: 실제 알림톡/문자 발송 — 메시징 제공사 계정·API 키·승인된 알림톡 템플릿 필요.
- **비범위**: 알림 이력 전용 DB 테이블(스키마 변경 필요), rpa→notifier 실제 배선(rpa 증분), scraper.

## 2. send() 시그니처 재설계

현재 스텁 `send(channel, count, success)`는 shop 컨텍스트가 없어 설정/수신번호/템플릿을 조회할 수 없다. 다음으로 변경한다:

```python
async def send(shop_key: int, channel: str, count: int, success: bool,
               *, repo: NotifierRepository | None = None,
               provider: NotificationProvider | None = None) -> bool
```
반환값은 "실제 발송했는지" 여부. repo/provider 미지정 시 Supabase/HTTP 구현 기본 생성(테스트는 fake 주입).

## 3. 모듈 분해

```
backend/src/ggotaiorder/notifier/
├─ sms_sender.py   # render_template(유지) + send() 오케스트레이션
├─ repository.py   # NotificationSettings(dataclass) + NotifierRepository(Protocol) + SupabaseNotifierRepository
└─ provider.py     # NotificationProvider(Protocol) + HttpNotificationProvider(골격)
```

### 3.1 repository.py
```python
@dataclass
class NotificationSettings:
    use_notification: str                      # 'Y' / 'N'
    notification_phone_number: Optional[str]
    rpa_success_message: str
    rpa_fail_message: str
    fallback_mobile: Optional[str]             # member_info.mobile_number

class NotifierRepository(Protocol):
    def get_settings(self, shop_key: int) -> Optional[NotificationSettings]: ...
```
`SupabaseNotifierRepository.get_settings`: `setting_info`(shop_key로 조회: use_notification, notification_phone_number, rpa_success_message, rpa_fail_message) + `member_info`(id=shop_key: mobile_number) 조회해 `NotificationSettings` 구성. 설정 행이 없으면 None.

### 3.2 provider.py
```python
class NotificationProvider(Protocol):
    def send_message(self, to: str, text: str) -> None: ...
```
`HttpNotificationProvider`: env(`NOTIFY_API_URL`, `NOTIFY_API_KEY`) 기반 httpx POST 골격. 실 발송은 제공사 계약·승인 템플릿 필요 → 라이브 체크리스트. 단위테스트는 fake provider로 대체(이 구현은 라이브 영역, 단위테스트 안 함).

### 3.3 sms_sender.py
- `render_template(template, channel, count) -> str` (기존 유지: `{channel}`/`{count}` 치환).
- `send(...)` 흐름(아래 4절).

## 4. 데이터 흐름 — send()

1. `settings = await asyncio.to_thread(repo.get_settings, shop_key)`. None → 경고 로그, `return False`.
2. `settings.use_notification != "Y"` → 정보 로그(스킵), `return False`.
3. 수신번호 `recipient = settings.notification_phone_number or settings.fallback_mobile`. 비어있으면 경고 로그, `return False`.
4. 템플릿 = `settings.rpa_success_message if success else settings.rpa_fail_message`.
5. `text = render_template(template, channel, count)`.
6. `await asyncio.to_thread(provider.send_message, recipient, text)`. 예외 발생 시 `logger.exception` 후 `return False`(파이프라인 비중단).
7. 성공: 이력 로깅(수신번호 마스킹, 예: 뒤 4자리만) 후 `return True`.

## 5. 에러 처리 / 비동기

- `send`는 async. 블로킹 호출(repo 조회·provider 발송)은 `asyncio.to_thread`로 오프로드(이벤트 루프 비블로킹).
- 어떤 실패(설정 없음·수신번호 없음·provider 예외)도 예외를 전파하지 않고 `False` 반환 + 로깅. 알림 실패가 주문 처리를 막지 않도록.

## 6. 이력 기록

4-테이블 스키마에 알림 전용 테이블이 없으므로, 이번 증분은 **로그 기반 이력**(발송 성공/실패를 `logger`로 기록, 수신번호는 뒤 4자리만 노출). 전용 DB 테이블은 후속(스키마 변경 + Supabase 마이그레이션 필요).

## 7. 테스트 (오프라인 결정적)

`test_notifier.py` — fake repo + fake provider(`send_message` 호출 기록):
- use_notification 'N' → provider 미호출, `False`.
- 'Y' + notification_phone_number 설정 → provider가 그 번호 + 렌더된 성공 텍스트로 호출, `True`.
- 'Y' + notification_phone_number None → fallback_mobile 사용.
- success=False → rpa_fail_message 사용.
- 수신번호 전무(둘 다 None) → 미발송, `False`.
- settings None → 미발송, `False`.
- provider.send_message 예외 → 잡아서 `False`.
- `render_template` 기존 동작(스모크 유지).
- 기존 53 passed 회귀 유지. 비동기 테스트는 `asyncio_mode="auto"`.

`provider.py`의 `HttpNotificationProvider`는 라이브 영역(import 확인만, 단위테스트 안 함).

## 8. 라이브 구동 체크리스트 (제공사 준비 시)

1. 메시징 제공사 계정/ API 키 발급(SMS) + (알림톡 시) 발신프로필·승인된 템플릿 등록.
2. `.env`에 `NOTIFY_API_URL`/`NOTIFY_API_KEY` 등 설정, `HttpNotificationProvider`를 해당 제공사 규격에 맞춰 완성.
3. `setting_info.use_notification='Y'` + 수신번호 설정 후 테스트 발송 확인.
4. (후속) rpa 처리 완료 → `notifier.send(shop_key, channel, count, success)` 실제 호출 배선.

## 9. 비범위(후속)

- 실 제공사 연동 완성·승인 템플릿, 알림 이력 DB 테이블.
- rpa→notifier 배선(rpa 증분), scraper(Playwright).
