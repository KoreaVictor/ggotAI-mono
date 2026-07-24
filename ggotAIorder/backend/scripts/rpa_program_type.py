"""이 가게가 쓰는 관리 프로그램 종류를 표준출력에 한 줄로 찍는다.

로그온 시 부수 프로세스를 띄울지 PowerShell 쪽에서 판단하려고 쓴다
(launch_rpa_chrome.ps1 — FlowerNT는 전용 Chrome이 필요하고 RoseWeb은 아니다).

출력: flowernt | roseweb | etc | none | unknown  (항상 exit 0)
  none    = RPA 미사용/미설정
  unknown = DB 조회 실패 + 캐시 없음 → 호출자가 안전한 쪽을 고를 것

조회에 성공하면 값을 캐시에 남겨, 다음 로그온에 네트워크가 늦게 올라와도
직전 값을 쓸 수 있게 한다. 진단 메시지는 표준오류로만 나간다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ggotaiorder.config import load_config
from ggotaiorder.rpa.program_settings import load_program_settings
from ggotaiorder.rpa.program_type import UNKNOWN, resolve_program_type

# backend/scripts/rpa_program_type.py → backend/
CACHE_PATH = Path(__file__).resolve().parents[1] / ".rpa_program_type"


def main() -> int:
    try:
        cfg = load_config()
    except Exception as exc:  # .env 미설정 등 — 판단 불가
        print(f"config 로드 실패({type(exc).__name__})", file=sys.stderr)
        print(UNKNOWN)
        return 0

    resolved = resolve_program_type(
        lookup=lambda: load_program_settings(cfg.shop_key, cfg.aes_encryption_key),
        cache_path=CACHE_PATH,
    )
    print(resolved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
