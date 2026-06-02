import pytest

from ggotaiorder.core.crypto import decrypt, encrypt

# cryptography(AES-256-CBC/PKCS7)로 실제 생성·검증한 고정 벡터.
# crypto-js가 동일 key/iv/plaintext로 만드는 결과와 바이트 단위로 동일하다.
KEY = "0123456789abcdef0123456789abcdef"      # 32 bytes -> AES-256
IV_HEX = "00112233445566778899aabbccddeeff"
PLAIN = "flower_pw_123!"
DB_VALUE = "00112233445566778899aabbccddeeff:trOEJkzSStKQyv6HIunOxw=="


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
    with pytest.raises(ValueError):
        decrypt(DB_VALUE, "short-key")


def test_decrypt_bad_iv_length_raises():
    bad = "00112233:trOEJkzSStKQyv6HIunOxw=="  # 4-byte IV
    with pytest.raises(ValueError):
        decrypt(bad, KEY)
