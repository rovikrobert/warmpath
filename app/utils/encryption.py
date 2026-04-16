"""Fernet encryption for Contact PII columns.

EncryptedString / EncryptedText — SQLAlchemy TypeDecorators that
transparently encrypt on write and decrypt on read.  Business logic
sees plaintext; the database stores ciphertext.

compute_blind_index() — HMAC-SHA256 deterministic hash for exact-match
lookups on encrypted columns (suppression system, dedup).

**IMPORTANT**: SQL-level operations (ILIKE, LIKE, ==, !=, etc.) on
encrypted columns operate on ciphertext and produce wrong results.
Always load rows first and filter in Python where the ORM decrypts.
The Comparator subclass below logs warnings if SQL-level text
comparisons are generated, to catch this mistake early.
"""

import hashlib
import hmac
import logging
import warnings

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.sql.expression import ColumnElement
from sqlalchemy.types import TypeDecorator

from app.config import settings
from app.utils.hashing import hash_for_suppression

logger = logging.getLogger(__name__)


class EncryptionConfigError(RuntimeError):
    """Raised when the encryption policy forbids the current configuration."""


# ---------------------------------------------------------------------------
# Cached Fernet singleton — keyed by the configured key so settings overrides
# (e.g. in tests) take effect without manual cache invalidation.
# ---------------------------------------------------------------------------

_fernet: Fernet | None = None
_cached_key: str | None = None
_plaintext_warned = False


def _get_fernet() -> Fernet | None:
    """Return the cached Fernet instance, or None if plaintext fallback is allowed.

    Policy:
      - production: ENCRYPTION_KEY required — raise if missing.
      - non-production: ENCRYPTION_KEY required unless
        ALLOW_PLAINTEXT_PII_FALLBACK=true is set explicitly.
    """
    global _fernet, _cached_key, _plaintext_warned
    key = settings.ENCRYPTION_KEY
    if not key:
        if settings.is_production:
            raise EncryptionConfigError(
                "ENCRYPTION_KEY is required in production. "
                "Set ENCRYPTION_KEY to a 44-byte base64 Fernet key."
            )
        if not settings.ALLOW_PLAINTEXT_PII_FALLBACK:
            raise EncryptionConfigError(
                "ENCRYPTION_KEY is missing. Set ENCRYPTION_KEY, or explicitly opt in "
                "to plaintext storage by setting ALLOW_PLAINTEXT_PII_FALLBACK=true "
                "(non-production only)."
            )
        if not _plaintext_warned:
            logger.warning(
                "ENCRYPTION_KEY not set and ALLOW_PLAINTEXT_PII_FALLBACK=true — "
                "PII will be stored AS PLAINTEXT. Never use this in production."
            )
            _plaintext_warned = True
        # invalidate any previously cached Fernet from a prior key
        _fernet = None
        _cached_key = None
        return None

    if key != _cached_key:
        _fernet = Fernet(key.encode())
        _cached_key = key
    return _fernet


def _decrypt_or_fallback(value: str) -> str:
    """Decrypt a stored value, applying the documented fallback policy on failure.

    Production: any decrypt failure raises (fail closed).
    Non-production with ALLOW_PLAINTEXT_PII_FALLBACK=true: log a loud warning
    and return the raw stored value (used to migrate pre-encryption rows).
    Otherwise: raise.
    """
    f = _get_fernet()
    if f is None:
        # _get_fernet() already enforced policy and logged; passthrough is allowed.
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except InvalidToken:
        if settings.is_production:
            logger.error(
                "Failed to decrypt PII column value in production — refusing to "
                "silently return ciphertext."
            )
            raise
        if settings.ALLOW_PLAINTEXT_PII_FALLBACK:
            logger.warning(
                "Decrypt failed; returning stored value as-is (plaintext fallback). "
                "This indicates a pre-encryption row or a key rotation issue."
            )
            return value
        raise


class _EncryptedComparator(TypeDecorator.Comparator):  # type: ignore[type-arg]
    """Warn when SQL-level text comparisons are used on encrypted columns.

    SQL operators like ILIKE, LIKE, ==, != operate on ciphertext in the
    database and will never match plaintext search terms.  Load rows first
    and filter in Python where the ORM decrypts transparently.
    """

    def _warn(self, op: str) -> None:
        col = getattr(self.expr, "key", self.expr)
        warnings.warn(
            f"SQL-level {op}() on encrypted column '{col}' operates on "
            "ciphertext — results will be wrong. Filter in Python instead.",
            stacklevel=4,
        )

    def ilike(self, other: object, **kw: object) -> ColumnElement[bool]:
        self._warn("ilike")
        return super().ilike(other, **kw)  # type: ignore[arg-type]

    def like(self, other: object, **kw: object) -> ColumnElement[bool]:
        self._warn("like")
        return super().like(other, **kw)  # type: ignore[arg-type]

    def contains(self, other: object, **kw: object) -> ColumnElement[bool]:
        self._warn("contains")
        return super().contains(other, **kw)  # type: ignore[arg-type]

    def startswith(self, other: object, **kw: object) -> ColumnElement[bool]:
        self._warn("startswith")
        return super().startswith(other, **kw)  # type: ignore[arg-type]

    def endswith(self, other: object, **kw: object) -> ColumnElement[bool]:
        self._warn("endswith")
        return super().endswith(other, **kw)  # type: ignore[arg-type]


class EncryptedString(TypeDecorator):
    """VARCHAR replacement that Fernet-encrypts on bind and decrypts on load.

    Stores as TEXT because ciphertext is longer than the original value.
    When ENCRYPTION_KEY is empty the column behaves like plain Text().
    """

    impl = Text
    cache_ok = True
    comparator_factory = _EncryptedComparator

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
        return _decrypt_or_fallback(value)


class EncryptedText(TypeDecorator):
    """Text replacement for longer fields (notes, how_you_know)."""

    impl = Text
    cache_ok = True
    comparator_factory = _EncryptedComparator

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
        return _decrypt_or_fallback(value)


def compute_blind_index(value: str) -> str:
    """HMAC-SHA256 deterministic hash for exact-match lookups.

    Falls back to plain SHA-256 (existing suppression hashing) when
    BLIND_INDEX_KEY is not configured.
    """
    key = settings.BLIND_INDEX_KEY
    if not key:
        return hash_for_suppression(value)
    return hmac.new(
        key.encode(), value.lower().strip().encode(), hashlib.sha256
    ).hexdigest()
