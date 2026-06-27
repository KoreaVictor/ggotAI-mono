# 카카오톡 알림톡(iwinv) 발송 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** RPA가 FlowerNT 저장 성공(및 manual/fail) 시 사장님 카카오톡으로 "주문접수 N건" 알림톡을 iwinv API로 발송한다.

**Architecture:** 기존 `notifier.NotificationProvider` 계약을 키워드 인자(`template_code`, `variables`)로 확장(접근법 A)하고, `KakaoIwinvProvider`를 추가한다. `sms_sender.send()`가 outcome→templateCode(env)를 해석하고 변수 dict를 만들어 provider에 넘긴다. provider 선택은 `make_provider()` 팩토리가 `NOTIFY_PROVIDER` env로 결정한다.

**Tech Stack:** Python 3.13, httpx, pytest(asyncio_mode=auto), 편집설치(egg-info).

## Global Constraints

- 알림 실패는 RPA 본류를 막지 않는다 — provider 예외는 `send()`의 try/except가 흡수하고 `False` 반환.
- iwinv 발송 API: `POST https://biz.service.iwinv.kr/api/send/`, 헤더 `AUTH = base64(IWINV_API_KEY)`, `Content-Type: application/json;charset=UTF-8`.
- 요청 body: `{ "templateCode": <code>, "reSend": "N", "list": [{ "phone": <숫자만>, "templateParam": <변수dict> }] }`.
- 응답 성공 판정: HTTP 2xx **그리고** JSON `code == 200` **그리고** `fail == 0`.
- 알림톡 변수 이름은 `건수`로 통일. 모든 outcome의 `templateParam == {"건수": str(count)}`.
- 전화번호 로그는 기존 `_mask()`로 마스킹.
- 테스트는 httpx 목으로만(실발송 금지 — templateCode 미승인 단계).
- 테스트 실행: 작업 디렉터리 `backend`에서 `.venv/Scripts/python.exe -m pytest`.
- env: `NOTIFY_PROVIDER`, `IWINV_API_KEY`, `IWINV_TEMPLATE_CODE_SUCCESS|MANUAL|FAIL`.

---

## File Structure

- Modify `backend/src/ggotaiorder/notifier/provider.py` — Protocol 시그니처 확장, `HttpNotificationProvider` 시그니처 확장, `_only_digits()` 추가, `KakaoIwinvProvider` 추가, `make_provider()` 추가.
- Modify `backend/src/ggotaiorder/notifier/sms_sender.py` — outcome→template_code 해석, `variables` 구성, template_code 없을 때 스킵, 기본 provider를 `make_provider()`로.
- Modify `backend/tests/test_notifier.py` — `FakeProvider`가 새 kwargs 수용하도록 갱신, send() 신규 동작 테스트 추가.
- Create `backend/tests/test_notifier_iwinv.py` — `KakaoIwinvProvider` + `make_provider()` 테스트.

---

### Task 1: Provider 계약 확장 + 전화번호 헬퍼

**Files:**
- Modify: `backend/src/ggotaiorder/notifier/provider.py`
- Test: `backend/tests/test_notifier_iwinv.py` (신규)

**Interfaces:**
- Consumes: 없음
- Produces:
  - `NotificationProvider.send_message(self, to: str, text: str, *, template_code: str | None = None, variables: dict[str, str] | None = None) -> None`
  - `HttpNotificationProvider.send_message(...)` 동일 시그니처, `text`만 사용
  - `_only_digits(value: str) -> str` (provider.py 모듈 함수)

- [ ] **Step 1: Write the failing test**

`backend/tests/test_notifier_iwinv.py` 생성:

```python
import base64

import httpx
import pytest

from ggotaiorder.notifier import provider as provider_mod
from ggotaiorder.notifier.provider import (
    HttpNotificationProvider,
    _only_digits,
)


def test_only_digits_strips_non_numeric():
    assert _only_digits("010-1111-2222") == "01011112222"
    assert _only_digits("+82 10 1234 5678") == "821012345678"


def test_http_provider_accepts_new_kwargs_and_uses_text(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setenv("NOTIFY_API_URL", "https://example.test/send")
    monkeypatch.setenv("NOTIFY_API_KEY", "k")
    monkeypatch.setattr(provider_mod.httpx, "post", fake_post)

    HttpNotificationProvider().send_message(
        "010-1111-2222", "본문", template_code="T1", variables={"건수": "1"}
    )
    assert captured["json"] == {"to": "010-1111-2222", "text": "본문"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_notifier_iwinv.py -v` (cwd: `backend`)
Expected: FAIL — `ImportError: cannot import name '_only_digits'`

- [ ] **Step 3: Write minimal implementation**

`provider.py` 상단 import에 추가: `import base64`. Protocol과 Http provider 시그니처를 확장하고 헬퍼를 추가한다.

```python
class NotificationProvider(Protocol):
    """단일 메시지 발송 계약."""

    def send_message(
        self,
        to: str,
        text: str,
        *,
        template_code: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> None: ...


def _only_digits(value: str) -> str:
    """전화번호 등에서 숫자만 추출."""
    return "".join(ch for ch in value if ch.isdigit())
```

`HttpNotificationProvider.send_message`를 다음으로 교체:

```python
    def send_message(
        self,
        to: str,
        text: str,
        *,
        template_code: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> None:
        api_url = os.getenv("NOTIFY_API_URL")
        api_key = os.getenv("NOTIFY_API_KEY")
        if not api_url or not api_key:
            raise RuntimeError("NOTIFY_API_URL/NOTIFY_API_KEY 미설정 — 발송 불가")
        resp = httpx.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"to": to, "text": text},
            timeout=10.0,
        )
        resp.raise_for_status()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_notifier_iwinv.py -v` (cwd: `backend`)
Expected: PASS (2 passed)

- [ ] **Step 5: Run existing notifier suite (regression)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_notifier.py -v` (cwd: `backend`)
Expected: PASS (기존 13 테스트 그대로 통과 — send()가 아직 새 kwargs를 안 넘기므로 영향 없음)

- [ ] **Step 6: Commit**

```bash
git add backend/src/ggotaiorder/notifier/provider.py backend/tests/test_notifier_iwinv.py
git commit -m "feat(notify): provider 계약에 template_code/variables 확장 + _only_digits"
```

---

### Task 2: KakaoIwinvProvider

**Files:**
- Modify: `backend/src/ggotaiorder/notifier/provider.py`
- Test: `backend/tests/test_notifier_iwinv.py`

**Interfaces:**
- Consumes: `_only_digits`, `NotificationProvider` 계약 (Task 1)
- Produces:
  - `class KakaoIwinvProvider` with class attr `requires_template_code = True`, class attr `API_URL = "https://biz.service.iwinv.kr/api/send/"`, and `send_message(self, to, text, *, template_code=None, variables=None) -> None`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_notifier_iwinv.py`에 추가:

```python
from ggotaiorder.notifier.provider import KakaoIwinvProvider


def _ok_response(url, code=200, fail=0):
    return httpx.Response(
        200,
        json={"code": code, "message": "ok", "success": 1, "fail": fail},
        request=httpx.Request("POST", url),
    )


def test_iwinv_builds_request_and_auth_header(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _ok_response(url)

    monkeypatch.setenv("IWINV_API_KEY", "secret-key")
    monkeypatch.setattr(provider_mod.httpx, "post", fake_post)

    KakaoIwinvProvider().send_message(
        "010-1111-2222", "본문무시", template_code="TPL_OK", variables={"건수": "1"}
    )

    assert captured["url"] == "https://biz.service.iwinv.kr/api/send/"
    assert captured["headers"]["AUTH"] == base64.b64encode(b"secret-key").decode("ascii")
    assert captured["json"]["templateCode"] == "TPL_OK"
    assert captured["json"]["reSend"] == "N"
    assert captured["json"]["list"] == [
        {"phone": "01011112222", "templateParam": {"건수": "1"}}
    ]


def test_iwinv_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("IWINV_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="IWINV_API_KEY"):
        KakaoIwinvProvider().send_message(
            "010-1111-2222", "x", template_code="T", variables={"건수": "1"}
        )


def test_iwinv_raises_when_template_code_missing(monkeypatch):
    monkeypatch.setenv("IWINV_API_KEY", "secret-key")
    with pytest.raises(RuntimeError, match="template_code"):
        KakaoIwinvProvider().send_message(
            "010-1111-2222", "x", template_code=None, variables={"건수": "1"}
        )


def test_iwinv_raises_on_non_200_code(monkeypatch):
    monkeypatch.setenv("IWINV_API_KEY", "secret-key")
    monkeypatch.setattr(
        provider_mod.httpx,
        "post",
        lambda url, headers=None, json=None, timeout=None: _ok_response(url, code=400),
    )
    with pytest.raises(RuntimeError, match="iwinv"):
        KakaoIwinvProvider().send_message(
            "010-1111-2222", "x", template_code="T", variables={"건수": "1"}
        )


def test_iwinv_raises_when_fail_count_nonzero(monkeypatch):
    monkeypatch.setenv("IWINV_API_KEY", "secret-key")
    monkeypatch.setattr(
        provider_mod.httpx,
        "post",
        lambda url, headers=None, json=None, timeout=None: _ok_response(url, fail=1),
    )
    with pytest.raises(RuntimeError, match="iwinv"):
        KakaoIwinvProvider().send_message(
            "010-1111-2222", "x", template_code="T", variables={"건수": "1"}
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_notifier_iwinv.py -k iwinv -v` (cwd: `backend`)
Expected: FAIL — `ImportError: cannot import name 'KakaoIwinvProvider'`

- [ ] **Step 3: Write minimal implementation**

`provider.py`에 클래스 추가:

```python
class KakaoIwinvProvider:
    """iwinv 알림톡 발송 제공사.

    승인된 templateCode + 변수값(templateParam)으로 카카오 알림톡을 보낸다.
    SMS 대체발송은 사용하지 않는다(reSend="N").
    """

    API_URL = "https://biz.service.iwinv.kr/api/send/"
    requires_template_code = True

    def send_message(
        self,
        to: str,
        text: str,
        *,
        template_code: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> None:
        api_key = os.getenv("IWINV_API_KEY")
        if not api_key:
            raise RuntimeError("IWINV_API_KEY 미설정 — 발송 불가")
        if not template_code:
            raise RuntimeError("template_code 없음 — 알림톡 발송 불가")

        auth = base64.b64encode(api_key.encode("utf-8")).decode("ascii")
        payload = {
            "templateCode": template_code,
            "reSend": "N",
            "list": [{"phone": _only_digits(to), "templateParam": variables or {}}],
        }
        resp = httpx.post(
            self.API_URL,
            headers={"AUTH": auth, "Content-Type": "application/json;charset=UTF-8"},
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200 or data.get("fail", 0):
            raise RuntimeError(f"iwinv 발송 실패: {data}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_notifier_iwinv.py -k iwinv -v` (cwd: `backend`)
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/src/ggotaiorder/notifier/provider.py backend/tests/test_notifier_iwinv.py
git commit -m "feat(notify): KakaoIwinvProvider — iwinv 알림톡 발송 구현"
```

---

### Task 3: make_provider() 팩토리

**Files:**
- Modify: `backend/src/ggotaiorder/notifier/provider.py`
- Test: `backend/tests/test_notifier_iwinv.py`

**Interfaces:**
- Consumes: `HttpNotificationProvider`, `KakaoIwinvProvider`
- Produces: `make_provider() -> NotificationProvider`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_notifier_iwinv.py`에 추가:

```python
from ggotaiorder.notifier.provider import make_provider


def test_make_provider_returns_iwinv_when_configured(monkeypatch):
    monkeypatch.setenv("NOTIFY_PROVIDER", "iwinv")
    assert isinstance(make_provider(), KakaoIwinvProvider)


def test_make_provider_defaults_to_http(monkeypatch):
    monkeypatch.delenv("NOTIFY_PROVIDER", raising=False)
    assert isinstance(make_provider(), HttpNotificationProvider)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_notifier_iwinv.py -k make_provider -v` (cwd: `backend`)
Expected: FAIL — `ImportError: cannot import name 'make_provider'`

- [ ] **Step 3: Write minimal implementation**

`provider.py` 끝에 추가:

```python
def make_provider() -> NotificationProvider:
    """env(NOTIFY_PROVIDER)로 발송 제공사를 선택한다."""
    if os.getenv("NOTIFY_PROVIDER", "").lower() == "iwinv":
        return KakaoIwinvProvider()
    return HttpNotificationProvider()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_notifier_iwinv.py -k make_provider -v` (cwd: `backend`)
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/src/ggotaiorder/notifier/provider.py backend/tests/test_notifier_iwinv.py
git commit -m "feat(notify): make_provider() — NOTIFY_PROVIDER env 기반 제공사 선택"
```

---

### Task 4: sms_sender.send() 배선 (outcome→templateCode + variables + 스킵)

**Files:**
- Modify: `backend/src/ggotaiorder/notifier/sms_sender.py`
- Test: `backend/tests/test_notifier.py`

**Interfaces:**
- Consumes: `make_provider` (Task 3), provider의 `requires_template_code` 속성(Task 2), `send_message(to, text, *, template_code, variables)` (Task 1)
- Produces: `send()` 동작 — outcome별 env templateCode를 읽어 `variables={"건수": str(count)}`와 함께 provider에 전달. provider가 `requires_template_code`이고 templateCode가 없으면 발송 스킵 후 `False`.

- [ ] **Step 1: Update FakeProvider then write failing tests**

`backend/tests/test_notifier.py`의 `FakeProvider`를 다음으로 교체(새 kwargs 수용 + 기록):

```python
class FakeProvider:
    requires_template_code = False

    def __init__(self, raises=False, requires_template_code=False):
        self.sent = []
        self.calls = []
        self._raises = raises
        self.requires_template_code = requires_template_code

    def send_message(self, to, text, *, template_code=None, variables=None):
        if self._raises:
            raise RuntimeError("provider down")
        self.sent.append((to, text))
        self.calls.append(
            {"to": to, "text": text, "template_code": template_code, "variables": variables}
        )
```

같은 파일에 신규 테스트 추가:

```python
async def test_success_passes_template_code_and_variables(monkeypatch):
    monkeypatch.setenv("IWINV_TEMPLATE_CODE_SUCCESS", "TPL_SUCCESS")
    repo = FakeRepo(_settings())
    provider = FakeProvider(requires_template_code=True)
    result = await send(2, "가게전화", 1, "success", repo=repo, provider=provider)
    assert result is True
    assert provider.calls[0]["template_code"] == "TPL_SUCCESS"
    assert provider.calls[0]["variables"] == {"건수": "1"}


async def test_template_provider_skips_when_code_missing(monkeypatch):
    monkeypatch.delenv("IWINV_TEMPLATE_CODE_FAIL", raising=False)
    repo = FakeRepo(_settings())
    provider = FakeProvider(requires_template_code=True)
    result = await send(2, "가게전화", 1, "fail", repo=repo, provider=provider)
    assert result is False
    assert provider.sent == []


async def test_freetext_provider_ignores_missing_template_code(monkeypatch):
    monkeypatch.delenv("IWINV_TEMPLATE_CODE_SUCCESS", raising=False)
    repo = FakeRepo(_settings())
    provider = FakeProvider(requires_template_code=False)
    result = await send(2, "가게전화", 1, "success", repo=repo, provider=provider)
    assert result is True
    assert provider.sent == [("010-1111-2222", "가게전화 주문 1건 입력 완료")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_notifier.py -k "template_code or template_provider or freetext" -v` (cwd: `backend`)
Expected: FAIL — `test_success_passes_template_code_and_variables`는 `template_code` is None, `test_template_provider_skips_when_code_missing`는 result True(스킵 미구현)

- [ ] **Step 3: Write minimal implementation**

`sms_sender.py` 수정. import 상단에 `import os` 추가, provider import를 `make_provider` 포함하도록 변경:

```python
from ggotaiorder.notifier.provider import NotificationProvider, make_provider
```

outcome→env 매핑과 헬퍼를 `_template_for` 근처에 추가:

```python
# outcome → iwinv 템플릿 코드 env 이름.
_TEMPLATE_CODE_ENV = {
    _OUTCOME_SUCCESS: "IWINV_TEMPLATE_CODE_SUCCESS",
    _OUTCOME_MANUAL: "IWINV_TEMPLATE_CODE_MANUAL",
    _OUTCOME_FAIL: "IWINV_TEMPLATE_CODE_FAIL",
}


def _template_code_for(outcome: str) -> str | None:
    """outcome에 해당하는 승인된 알림톡 templateCode(env)를 읽는다."""
    env_name = _TEMPLATE_CODE_ENV.get(outcome)
    return os.getenv(env_name) if env_name else None
```

`send()` 안에서 기본 provider 생성을 교체:

```python
    repo = repo or SupabaseNotifierRepository()
    provider = provider or make_provider()
```

그리고 `text` 렌더 직후, `provider.send_message` 호출부를 다음으로 교체:

```python
    template = _template_for(settings, outcome)
    text = render_template(template, channel, count)
    if not text.strip():
        logger.warning("빈 메시지 — 발송 스킵 shop_key=%s", shop_key)
        return False

    template_code = _template_code_for(outcome)
    variables = {"건수": str(count)}
    if getattr(provider, "requires_template_code", False) and not template_code:
        logger.info(
            "알림톡 templateCode 없음(outcome=%s) — 발송 스킵 shop_key=%s",
            outcome,
            shop_key,
        )
        return False

    try:
        await asyncio.to_thread(
            provider.send_message,
            recipient,
            text,
            template_code=template_code,
            variables=variables,
        )
    except Exception:
        logger.exception("알림 발송 실패 shop_key=%s to=%s", shop_key, _mask(recipient))
        return False
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_notifier.py -k "template_code or template_provider or freetext" -v` (cwd: `backend`)
Expected: PASS (3 passed)

- [ ] **Step 5: Run full notifier suites (regression)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_notifier.py tests/test_notifier_iwinv.py -v` (cwd: `backend`)
Expected: PASS (기존 13 + 신규 전부 통과)

- [ ] **Step 6: Commit**

```bash
git add backend/src/ggotaiorder/notifier/sms_sender.py backend/tests/test_notifier.py
git commit -m "feat(notify): send()에서 outcome별 templateCode 해석·변수 전달·미승인 스킵"
```

---

## 배포·운영 (구현 후, 코드 외 단계 — 자동화 불가)

1. iwinv 콘솔에서 success/manual/fail 템플릿 3개 검수 요청 → 승인 후 templateCode 확보.
2. 운영 PC `.env`에 `NOTIFY_PROVIDER=iwinv`, `IWINV_API_KEY`, `IWINV_TEMPLATE_CODE_SUCCESS|MANUAL|FAIL` 설정.
3. 백엔드 재시작: `Stop-ScheduledTask -TaskName ggotAIorder; Start-ScheduledTask -TaskName ggotAIorder`.
4. 라이브 검증: 본인 번호로 success 1건 실발송 → 카톡 수신 + 로그 `알림 발송 성공` 확인.
5. `setting_info.rpa_success/manual/fail_message`가 비어 있지 않은지 확인(빈 문자열이면 `text.strip()` 게이트에서 스킵됨).

## 범위 밖 (YAGNI)

SMS 대체발송, 발송 재시도/큐, `채널` 변수, 묶음(count>1) 발송, 발신프로필 자동등록.
