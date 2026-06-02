import pytest

from ggotaiorder.core.crypto import decrypt, encrypt

# cryptography(AES-256-CBC/PKCS7)로 실제 생성·검증한 고정 벡터.
# 키는 64자 hex 문자열을 hex 디코딩한 32바이트. crypto-js가 Hex.parse(key)로
# 동일 key/iv/plaintext에 대해 만드는 결과와 바이트 단위로 동일하다.
KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"  # 64 hex -> 32 bytes
IV_HEX = "00112233445566778899aabbccddeeff"
PLAIN = "flower_pw_123!"
DB_VALUE = "00112233445566778899aabbccddeeff:3ppbn4afJAnI6OD4EGhipQ=="


def test_decrypt_known_vector():
    assert decrypt(DB_VALUE, KEY) == PLAIN


def test_encrypt_with_fixed_iv_matches_vector():
    iv = bytes.fromhex(IV_HEX)
    assert encrypt(PLAIN, KEY, iv=iv) == DB_VALUE


def test_round_trip_random_iv():
    blob = encrypt("배달장소 서울시 강남구", KEY)
    assert decrypt(blob, KEY) == "배달장소 서울시 강남구"
    # 랜덤 IV 이므로 매 호출 결과가 달라야 한다
    assert encrypt("x", KEY) != encrypt("x", KEY)


def test_wrong_key_length_raises():
    # 유효한 hex이지만 16바이트(AES-256 아님) -> 길이 검증 실패
    with pytest.raises(ValueError):
        decrypt(DB_VALUE, "0123456789abcdef0123456789abcdef")


def test_non_hex_key_raises():
    with pytest.raises(ValueError):
        decrypt(DB_VALUE, "not-a-hex-key-zzzz")


def test_decrypt_bad_iv_length_raises():
    bad = "00112233:3ppbn4afJAnI6OD4EGhipQ=="  # 4-byte IV
    with pytest.raises(ValueError):
        decrypt(bad, KEY)
