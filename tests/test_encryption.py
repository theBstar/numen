"""Unit tests for OAuth token encryption helpers."""

from src.shared.encryption import decrypt_token, encrypt_token, is_encrypted, try_decrypt


def test_roundtrip():
    plaintext = "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ciphertext = encrypt_token(plaintext)
    assert ciphertext != plaintext
    assert decrypt_token(ciphertext) == plaintext


def test_try_decrypt_passes_through_plaintext():
    plaintext = "ghp_legacyplaintexttoken"
    # Should not raise; should return the original value for legacy rows.
    assert try_decrypt(plaintext) == plaintext


def test_try_decrypt_decrypts_ciphertext():
    plaintext = "xoxb-secret-slack-token"
    ciphertext = encrypt_token(plaintext)
    assert try_decrypt(ciphertext) == plaintext


def test_try_decrypt_none():
    assert try_decrypt(None) is None


def test_is_encrypted():
    assert is_encrypted(encrypt_token("abc")) is True
    assert is_encrypted("ghp_plain") is False
    assert is_encrypted(None) is False
