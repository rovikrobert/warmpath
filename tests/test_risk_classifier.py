"""Test risk classification for agent findings."""

from agents.shared.report import Finding
from agents.shared.risk_classifier import RiskLevel, classify_risk


def _finding(severity="medium", auto_fixable=False, file=None, category="lint"):
    return Finding(
        id="test-1",
        severity=severity,
        category=category,
        title="Test",
        detail="Detail",
        file=file,
        auto_fixable=auto_fixable,
    )


def test_trivial_risk_for_auto_fixable_lint():
    f = _finding(severity="low", auto_fixable=True, category="lint")
    assert classify_risk(f) == RiskLevel.TRIVIAL


def test_low_risk_for_auto_fixable_medium():
    f = _finding(severity="medium", auto_fixable=True, category="dependency")
    assert classify_risk(f) == RiskLevel.LOW


def test_high_risk_for_auth_file():
    f = _finding(severity="medium", file="app/api/auth.py", category="security")
    assert classify_risk(f) == RiskLevel.HIGH


def test_critical_risk_for_credit_file():
    f = _finding(
        severity="high", file="app/services/credit_service.py", category="security"
    )
    assert classify_risk(f) == RiskLevel.CRITICAL


def test_medium_risk_default():
    f = _finding(severity="medium", category="test_coverage")
    assert classify_risk(f) == RiskLevel.MEDIUM


def test_critical_severity_always_critical():
    f = _finding(severity="critical", category="lint")
    assert classify_risk(f) == RiskLevel.CRITICAL
