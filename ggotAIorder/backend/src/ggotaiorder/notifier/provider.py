"""알림 발송 제공사 추상화.

NotificationProvider(Protocol)로 계약을 고정하고, 실제 발송은 제공사별 구현이 담당한다.
HttpNotificationProvider 는 골격이며 실 발송에는 제공사 계정·승인 템플릿이 필요하다(라이브 체크리스트).
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


def _only_digits(value: str) -> str:
    """전화번호 등에서 숫자만 추출."""
    return "".join(ch for ch in value if ch.isdigit())


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


class HttpNotificationProvider:
    """범용 HTTP 메시징 제공사 골격 (env 기반).

    NOTIFY_API_URL/NOTIFY_API_KEY 로 설정. 실제 페이로드 규격은 제공사에 맞춰
    완성해야 한다(라이브 체크리스트). 미설정 시 RuntimeError.
    """

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
        # None 또는 빈 문자열이면 발송 불가
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


class KakaoBizmProvider:
    """비즈엠(스윗트래커) 알림톡 발송 제공사.

    iwinv 와 달리 서버가 템플릿을 렌더링하지 않고, 완성된 문구(msg)를 그대로
    보낸다. 따라서 승인된 템플릿의 고정문구와 msg 가 일치해야 발송된다.
    발신프로필키(profile, 카카오 채널 등록 시 발급)와 승인된 tmplId 가 필요하다.
    """

    API_URL = "https://alimtalk-api.bizmsg.kr/v2/sender/send"
    requires_template_code = True

    def send_message(
        self,
        to: str,
        text: str,
        *,
        template_code: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> None:
        user_id = os.getenv("BIZM_USER_ID")
        if not user_id:
            raise RuntimeError("BIZM_USER_ID 미설정 — 발송 불가")
        profile_key = os.getenv("BIZM_PROFILE_KEY")
        if not profile_key:
            raise RuntimeError("BIZM_PROFILE_KEY 미설정 — 발송 불가")
        if not template_code:
            raise RuntimeError("template_code 없음 — 알림톡 발송 불가")

        # body 는 JSON Array(최대 100건). 완성된 문구(text)를 msg 로 그대로 보낸다.
        payload = [
            {
                "message_type": "AT",
                "phn": _only_digits(to),
                "profile": profile_key,
                "tmplId": template_code,
                "msg": text,
                "reserveDt": "00000000000000",
            }
        ]
        resp = httpx.post(
            self.API_URL,
            headers={"userid": user_id, "Content-Type": "application/json"},
            json=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        results = resp.json()
        if not all(item.get("code") == "success" for item in results):
            raise RuntimeError(f"bizm 발송 실패: {results}")


def make_provider() -> NotificationProvider:
    """env(NOTIFY_PROVIDER)로 발송 제공사를 선택한다."""
    selected = os.getenv("NOTIFY_PROVIDER", "").lower()
    if selected == "iwinv":
        return KakaoIwinvProvider()
    if selected == "bizm":
        return KakaoBizmProvider()
    return HttpNotificationProvider()
