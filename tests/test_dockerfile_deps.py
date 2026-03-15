"""Verify Dockerfile installs required tools for agent repair pipeline."""


def test_gh_cli_install_line_in_dockerfile():
    """Dockerfile must install gh CLI for agent PR creation."""
    with open("Dockerfile") as f:
        content = f.read()
    assert "gh" in content, "Dockerfile must install gh CLI"
