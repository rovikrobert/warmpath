"""Tests for the hardened webhook + encryption fail-open policy.

Covers the matrix of {production, non-production} × {opt-in, default}
for both unsigned webhooks and missing ENCRYPTION_KEY / decrypt failure.
"""

from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient

from app import api
from app.config import settings
from app.utils import encryption as enc


# ---------------------------------------------------------------------------
# Webhook policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsigned_webhook_rejected_in_production(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production must reject unsigned webhooks even with ALLOW_INSECURE_WEBHOOKS=true."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_WEBHOOKS", True)
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "")

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps({"type": "email.opened", "data": {"email_id": "x"}}),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unsigned_webhook_rejected_when_flag_off(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-production must still reject when ALLOW_INSECURE_WEBHOOKS=false."""
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_WEBHOOKS", False)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")

    resp = await client.post(
        "/api/v1/webhooks/stripe",
        content=json.dumps({"type": "checkout.session.completed", "data": {}}),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 503
    assert "ALLOW_INSECURE_WEBHOOKS" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unsigned_webhook_accepted_with_dev_optin(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-production + ALLOW_INSECURE_WEBHOOKS=true accepts unsigned payloads."""
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_WEBHOOKS", True)
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "")

    resp = await client.post(
        "/api/v1/webhooks/resend",
        content=json.dumps({"type": "email.opened", "data": {}}),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_signed_webhook_path_unaffected_by_policy(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the secret IS configured, the policy flag is irrelevant — bad sig still 400s."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_WEBHOOKS", True)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_fake_for_test")

    resp = await client.post(
        "/api/v1/webhooks/stripe",
        content=json.dumps({"type": "checkout.session.completed", "data": {}}),
        headers={
            "Content-Type": "application/json",
            "stripe-signature": "t=1,v1=deadbeef",
        },
    )

    assert resp.status_code == 400
    assert "signature" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Encryption policy
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_encryption_cache():
    """Each test starts with a clean cache so settings overrides take effect."""
    enc._fernet = None
    enc._cached_key = None
    enc._plaintext_warned = False
    yield
    enc._fernet = None
    enc._cached_key = None
    enc._plaintext_warned = False


def test_encryption_required_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing ENCRYPTION_KEY in production must raise — never silently passthrough."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "ALLOW_PLAINTEXT_PII_FALLBACK", True)  # ignored

    with pytest.raises(enc.EncryptionConfigError, match="production"):
        enc._get_fernet()


def test_encryption_required_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-production also requires opt-in; otherwise raise."""
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "ALLOW_PLAINTEXT_PII_FALLBACK", False)

    with pytest.raises(enc.EncryptionConfigError, match="ALLOW_PLAINTEXT_PII_FALLBACK"):
        enc._get_fernet()


def test_plaintext_passthrough_with_dev_optin(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Dev opt-in returns None and logs a loud warning exactly once."""
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "")
    monkeypatch.setattr(settings, "ALLOW_PLAINTEXT_PII_FALLBACK", True)

    with caplog.at_level("WARNING", logger="app.utils.encryption"):
        assert enc._get_fernet() is None
        # second call must not duplicate the warning
        assert enc._get_fernet() is None

    warnings = [r for r in caplog.records if "PLAINTEXT" in r.getMessage()]
    assert len(warnings) == 1


def test_decrypt_failure_raises_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Corrupt/plaintext value must NOT pass through silently in production."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "ALLOW_PLAINTEXT_PII_FALLBACK", True)  # ignored

    from cryptography.fernet import InvalidToken

    with pytest.raises(InvalidToken):
        enc._decrypt_or_fallback("not-a-fernet-token")


def test_decrypt_failure_passthrough_with_dev_optin(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Dev opt-in lets pre-encryption rows survive migration with a warning."""
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "ALLOW_PLAINTEXT_PII_FALLBACK", True)

    with caplog.at_level("WARNING", logger="app.utils.encryption"):
        result = enc._decrypt_or_fallback("legacy-plaintext-row")

    assert result == "legacy-plaintext-row"
    assert any("Decrypt failed" in r.getMessage() for r in caplog.records)


def test_decrypt_failure_raises_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """No flag, non-production: decrypt failure still raises (no silent fallback)."""
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "ALLOW_PLAINTEXT_PII_FALLBACK", False)

    from cryptography.fernet import InvalidToken

    with pytest.raises(InvalidToken):
        enc._decrypt_or_fallback("not-a-fernet-token")


# Silence unused-import warning — kept in case future tests need to reference
# the api package directly while monkeypatching settings.
_ = api
