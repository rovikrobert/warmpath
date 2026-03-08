"""Test agent reorg — ux_lead + design_lead in engineering, not product."""


def test_ux_lead_in_engineering_registry():
    from agents.orchestrator import _AGENT_MODULES

    assert "ux_lead" in _AGENT_MODULES


def test_design_lead_in_engineering_registry():
    from agents.orchestrator import _AGENT_MODULES

    assert "design_lead" in _AGENT_MODULES


def test_ux_lead_not_in_product_registry():
    from product_team.orchestrator import _AGENT_MODULES

    assert "ux_lead" not in _AGENT_MODULES


def test_design_lead_not_in_product_registry():
    from product_team.orchestrator import _AGENT_MODULES

    assert "design_lead" not in _AGENT_MODULES


def test_ux_lead_in_engineering_config():
    from agents.shared.config import AGENT_NAMES

    assert "ux_lead" in AGENT_NAMES


def test_design_lead_in_engineering_config():
    from agents.shared.config import AGENT_NAMES

    assert "design_lead" in AGENT_NAMES


def test_ux_lead_not_in_product_config():
    from product_team.shared.config import PRODUCT_AGENT_NAMES

    assert "ux_lead" not in PRODUCT_AGENT_NAMES


def test_design_lead_not_in_product_config():
    from product_team.shared.config import PRODUCT_AGENT_NAMES

    assert "design_lead" not in PRODUCT_AGENT_NAMES
