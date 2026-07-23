"""mall_credentials 에 커머스API 자격증명을 시드한다(초기 주입/갱신).

client_secret 은 core.crypto.encrypt 로 iv:ct 포맷 암호화 저장. (shop_key, provider)
UNIQUE 이므로 이미 있으면 갱신(upsert). enable_rpa_shop.py 와 동일한 운영 스크립트 방식.

사용 예:
    python -m scripts.seed_mall_credential --shop 19 \
        --client-id abcd1234 --client-secret '$2a$04$....' --store-id 100200
"""

from __future__ import annotations

import argparse
import sys

from ggotaiorder.config import load_config
from ggotaiorder.core.crypto import encrypt
from ggotaiorder.core.supabase_client import get_client
from ggotaiorder.mall.models import PROVIDER_SMARTSTORE


def main() -> int:
    ap = argparse.ArgumentParser(description="커머스API 자격증명 시드")
    ap.add_argument("--shop", type=int, required=True, help="shop_key (예: 19)")
    ap.add_argument("--client-id", required=True, help="커머스API application id")
    ap.add_argument("--client-secret", required=True, help="application secret(bcrypt salt) — 암호화 저장")
    ap.add_argument("--provider", default=PROVIDER_SMARTSTORE, help="기본 smartstore")
    ap.add_argument("--store-id", default=None, help="스마트스토어 채널/스토어 식별자(extra.store_id)")
    args = ap.parse_args()

    cfg = load_config()
    enc_secret = encrypt(args.client_secret, cfg.aes_encryption_key)
    extra: dict = {}
    if args.store_id:
        extra["store_id"] = args.store_id

    row = {
        "shop_key": args.shop,
        "provider": args.provider,
        "client_id": args.client_id,
        "enc_client_secret": enc_secret,
        "extra": extra,
        "is_active": True,
    }
    client = get_client()
    res = (
        client.table("mall_credentials")
        .upsert(row, on_conflict="shop_key,provider")
        .execute()
    )
    if not res.data:
        print("업서트 응답이 비었습니다 — 실패 가능", file=sys.stderr)
        return 1
    print(f"OK: mall_credentials 시드 shop={args.shop} provider={args.provider}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
