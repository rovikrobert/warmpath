"""Fernet encryption for Contact PII columns.

EncryptedString / EncryptedText — SQLAlchemy TypeDecorators that
transparently encrypt on write and decrypt on read.  Business logic
sees plaintext; the database stores ciphertext.

compute_blind_index() — HMAC-SHA256 deterministic hash for exact-match
lookups on encrypted columns (suppression system, dedup).
"""
import hashlib
import hmac
import logging
from cryptography.fernet import Fernet
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator
from app.config import settings
from app.utils.hashing import hash_for_suppression
logger = logging.getLogger(__name__)
_fernet: Fernet | None = None
_fernet_checked = False

def _get_fernet() -> Fernet | None:
    """Return the cached Fernet instance, or None if ENCRYPTION_KEY is empty."""
    global _fernet, _fernet_checked
    if not _fernet_checked:
        key = settings.ENCRYPTION_KEY
        if not key:
            logger.warning('ENCRYPTION_KEY not set — PII stored as plaintext')
            _fernet = None
        else:
            _fernet = Fernet(key.encode())
        _fernet_checked = True
    return _fernet

class EncryptedString(TypeDecorator):
    """VARCHAR replacement that Fernet-encrypts on bind and decrypts on load.

    Stores as TEXT because ciphertext is longer than the original value.
    When ENCRYPTION_KEY is empty the column behaves like plain Text().
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect) -> str | None:
        if value is None:
            return None
        f = _get_fernet()
        if f is None:
            return value
        return f.encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect) -> str | None:
        if value is None:
            return None
        f = _get_fernet()
        if f is None:
            return value
        try:
            return f.decrypt(value.encode()).decode()
        except Exception:
            return value

class EncryptedText(TypeDecorator):
    """Text replacement for longer fields (notes, how_you_know)."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect) -> str | None:
        if value is None:
            return None
        f = _get_fernet()
        if f is None:
            return value
        return f.encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect) -> str | None:
        if value is None:
            return None
        f = _get_fernet()
        if f is None:
            return None
        try:
            return f.decrypt(value.encode()).decode()
        except Exception:
            return value

def compute_blind_index(value: str) -> str:
    """HMAC-SHA256 deterministic hash for exact-match lookups.

    Falls back to plain SHA-256 (existing suppression hashing) when
    BLIND_INDEX_KEY is not configured.
    """
    key = settings.BLIND_INDEX_KEY
    if not key:
        return hash_for_suppression(value)
    return hmac.new(key.encode(), value.lower().strip().encode(), hashlib.sha256).hexdigest()