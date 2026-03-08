"""Tests for Sentry SDK configuration fields."""


def test_sentry_dsn_config_field():
    """Settings should have SENTRY_DSN as optional field."""
    from app.config import Settings

    s = Settings(DATABASE_URL="sqlite:///test.db")
    assert s.SENTRY_DSN is None


def test_sentry_traces_sample_rate_default():
    """Settings should default SENTRY_TRACES_SAMPLE_RATE to 0.1."""
    from app.config import Settings

    s = Settings(DATABASE_URL="sqlite:///test.db")
    assert s.SENTRY_TRACES_SAMPLE_RATE == 0.1
