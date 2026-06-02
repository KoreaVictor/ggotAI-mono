"""AES-256-CBC 대칭키 복호화 (프론트엔드 crypto-js 호환).

DB 저장 포맷: ``iv_hex:ciphertext_base64``
- 알고리즘: AES-256-CBC
- 패딩: PKCS7(128)
- 키: UTF-8 32바이트 문자열 (AES_ENCRYPTION_KEY)
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _key_bytes(key: str) -> bytes:
    raw = key.encode("utf-8")
    if len(raw) != 32:
        raise ValueError("AES 키는 UTF-8 기준 정확히 32바이트여야 합니다.")
    return raw


def decrypt(db_value: str, key: str) -> str:
    """``iv_hex:ciphertext_base64`` 형식을 복호화해 평문을 반환한다."""
    iv_hex, ct_b64 = db_value.split(":", 1)
    iv = bytes.fromhex(iv_hex)
    ciphertext = base64.b64decode(ct_b64)

    decryptor = Cipher(algorithms.AES(_key_bytes(key)), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    plain = unpadder.update(padded) + unpadder.finalize()
    return plain.decode("utf-8")


def encrypt(plaintext: str, key: str, iv: bytes | None = None) -> str:
    """평문을 ``iv_hex:ciphertext_base64`` 형식으로 암호화한다.

    iv 미지정 시 16바이트 랜덤 IV를 생성한다. (검증/테스트 및 백엔드 측
    설정 저장에 사용; 프론트엔드는 crypto-js로 동일 포맷을 생성한다.)
    """
    if iv is None:
        iv = os.urandom(16)
    if len(iv) != 16:
        raise ValueError("IV 는 정확히 16바이트여야 합니다.")

    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()

    encryptor = Cipher(algorithms.AES(_key_bytes(key)), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return iv.hex() + ":" + base64.b64encode(ciphertext).decode("ascii")
