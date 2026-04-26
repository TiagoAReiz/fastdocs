from app.core.crypto import decrypt, encrypt


def test_encrypt_decrypt_roundtrip():
    plain = "AIzaSyTestKey12345"
    assert decrypt(encrypt(plain)) == plain


def test_different_plaintexts_produce_different_ciphertext():
    a = encrypt("key-a")
    b = encrypt("key-b")
    assert a != b


def test_ciphertext_not_equal_to_plaintext():
    plain = "my-secret"
    assert encrypt(plain) != plain
