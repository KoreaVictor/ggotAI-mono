"""shop 의 RPA(FlowerNT3) 설정을 활성화한다.

setting_info 에 rpa_program_type/url/login_id/login_password(암호화)/enabled/auto_submit 를
직접 기록한다. 비밀번호는 core.crypto.encrypt 로 iv:ct 포맷으로 저장한다.

사용 예(안전 1단계 — 채우기만, 등록 안 함):
    python -m scripts.enable_rpa_shop --shop 19 --login-id myid --password mypw --auto-submit N

자동등록까지(검증 후 2단계):
    python -m scripts.enable_rpa_shop --shop 19 --auto-submit Y

비번/계정을 바꾸지 않고 auto_submit/enabled 만 토글할 수도 있다(미전달 인자는 기존값 보존).
"""

from __future__ import annotations

import argparse
import sys

from ggotaiorder.config import load_config
from ggotaiorder.core.crypto import encrypt
from ggotaiorder.core.supabase_client import get_client


def main() -> int:
    ap = argparse.ArgumentParser(description="shop RPA(FlowerNT3) 설정 활성화")
    ap.add_argument("--shop", type=int, required=True, help="shop_key (예: 19)")
    ap.add_argument("--program-type", default="flowernt", help="기본 flowernt")
    ap.add_argument("--url", default=None, help="미지정 시 기본 도메인 사용")
    ap.add_argument("--login-id", default=None, help="FlowerNT3 ms_id (세션 만료 시 자동복구용)")
    ap.add_argument("--password", default=None, help="FlowerNT3 ms_pass (암호화 저장)")
    ap.add_argument("--enabled", choices=["Y", "N"], default="Y")
    ap.add_argument(
        "--auto-submit", choices=["Y", "N"], default="N",
        help="Y=등록까지 자동, N=채우기만(권장: 첫 검증은 N)",
    )
    args = ap.parse_args()

    cfg = load_config()

    update: dict[str, object] = {
        "rpa_program_type": args.program_type,
        "rpa_enabled": args.enabled,
        "rpa_auto_submit": args.auto_submit,
    }
    if args.url is not None:
        update["rpa_program_url"] = args.url
    if args.login_id is not None:
        update["rpa_login_id"] = args.login_id
    if args.password is not None:
        update["rpa_login_password"] = encrypt(args.password, cfg.aes_encryption_key)

    res = (
        get_client()
        .table("setting_info")
        .update(update)
        .eq("shop_key", args.shop)
        .execute()
    )
    if not res.data:
        print(f"[실패] shop_key={args.shop} setting_info 행 없음", file=sys.stderr)
        return 1

    safe = {k: ("***" if k == "rpa_login_password" else v) for k, v in update.items()}
    print(f"[성공] shop {args.shop} RPA 설정 갱신: {safe}")
    print("  auto_submit=N 이면 폼 채우기까지만 하고 등록(submit)은 하지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
