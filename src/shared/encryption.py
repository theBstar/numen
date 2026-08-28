"""Field-level encryption for sensitive data (OAuth tokens).

Key source: `settings.encryption_key` (dedicated, never rotated). In dev,
if unset, we derive from `settings.secret_key` so local tests don't need
a new env var. Production startup fails closed if `encryption_key` is empty.

Backward compatibility: `try_decrypt` returns the input unchanged when it
is not valid Fernet ciphertext, so plaintext rows from before the rollout
keep working until the backfill script encrypts them in place.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.config import settings


def _derive_key(secret: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"numen-token-encryption",
        iterations=480000,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


def _get_fernet() -> Fernet:
    secret = settings.encryption_key or settings.secret_key
    return Fernet(_derive_key(secret))


def encrypt_token(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def try_decrypt(value: str | None) -> str | None:
    """Decrypt if the value is Fernet ciphertext; otherwise return as-is.

    Used by the SQLAlchemy TypeDecorator during the rollout period when
    both plaintext and ciphertext rows coexist. After the backfill script
    runs, every row is ciphertext and this degrades to decrypt_token.
    """
    if value is None:
        return None
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return value


def is_encrypted(value: str | None) -> bool:
    if value is None:
        return False
    try:
        _get_fernet().decrypt(value.encode())
        return True
    except (InvalidToken, ValueError):
        return False
