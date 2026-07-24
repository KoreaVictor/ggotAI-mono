"""가게가 쓰는 관리 프로그램 종류를 해석한다(캐시 폴백 포함).

용도는 "이 PC에서 그 프로그램용 부수 프로세스를 띄울 것인가" 판단이다. FlowerNT는
전용 Chrome(CDP 9222)이 필요하지만 RoseWeb(데스크톱 앱)은 필요 없다 — 그런데도
로그온마다 Chrome이 뜨면 사장님 화면에 쓸데없는 창이 하나 더 생긴다.

권위는 DB(setting_info)지만, 이 판단이 필요한 시점이 하필 **로그온 직후**라
네트워크·DNS가 아직 안 올라와 조회가 실패하는 일이 흔하다(실측: 부팅 후 3분간
getaddrinfo 실패). 그래서 성공한 값을 파일에 캐시해 두고 실패 시 그걸 쓴다.
캐시조차 없으면 UNKNOWN 을 돌려주고, 무엇을 할지는 호출자가 정한다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ggotaiorder.rpa.program_settings import RpaProgramSettings

logger = logging.getLogger(__name__)

UNKNOWN = "unknown"
NONE = "none"          # RPA 미사용/미설정 — 부수 프로세스 불필요


def _normalize(settings: RpaProgramSettings | None) -> str:
    if settings is None or not settings.enabled:
        return NONE
    return (settings.program_type or "").strip() or NONE


def resolve_program_type(*, lookup, cache_path: Path | str) -> str:
    """관리 프로그램 종류를 돌려준다.

    lookup() 성공 → 정규화한 값을 캐시에 적고 반환.
    lookup() 실패 → 캐시 값, 캐시도 없으면 UNKNOWN.
    """
    cache_path = Path(cache_path)
    try:
        resolved = _normalize(lookup())
    except Exception as exc:
        cached = _read_cache(cache_path)
        if cached:
            logger.warning(
                "관리 프로그램 종류 조회 실패(%s) — 캐시값 사용: %s",
                type(exc).__name__, cached,
            )
            return cached
        logger.warning(
            "관리 프로그램 종류 조회 실패(%s), 캐시도 없음 — %s",
            type(exc).__name__, UNKNOWN,
        )
        return UNKNOWN

    _write_cache(cache_path, resolved)
    return resolved


def _read_cache(path: Path) -> str | None:
    try:
        # utf-8-sig: 이 파일을 메모장·PowerShell 로 저장하면 BOM이 붙는데, 그게 값에
        # 남으면 호출자의 문자열 비교가 조용히 어긋난다.
        return path.read_text(encoding="utf-8-sig").strip() or None
    except OSError:
        return None


def _write_cache(path: Path, value: str) -> None:
    # 캐시는 부가기능 — 못 써도 해석 결과에는 영향이 없어야 한다.
    try:
        path.write_text(value, encoding="utf-8")
    except OSError as exc:
        logger.debug("관리 프로그램 종류 캐시 기록 실패(%s): %s", type(exc).__name__, path)
