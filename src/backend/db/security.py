from functools import lru_cache
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def password_hash_needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, VerificationError):
        return True


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """A random Argon2id hash keeps unknown-user login work comparable."""
    return hash_password(secrets.token_urlsafe(32))


# Avoid an extra first-request hash operation that would expose account timing.
dummy_password_hash()
