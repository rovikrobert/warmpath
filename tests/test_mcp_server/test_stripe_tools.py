"""Tests for MCP Stripe tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mcp_server.tools.stripe import (
    stripe_balance,
    stripe_charges,
    stripe_disputes,
    stripe_subscriptions,
)


@patch("mcp_server.tools.stripe._get_client")
class TestStripeBalance:
    def test_returns_balance(self, mock_get: MagicMock) -> None:
        client = MagicMock()
        client.is_available.return_value = True
        client.get_balance.return_value = {"available": [{"amount": 1000}]}
        mock_get.return_value = client

        result = stripe_balance()
        assert result["available"][0]["amount"] == 1000

    def test_unavailable_returns_error(self, mock_get: MagicMock) -> None:
        client = MagicMock()
        client.is_available.return_value = False
        mock_get.return_value = client

        result = stripe_balance()
        assert "error" in result


@patch("mcp_server.tools.stripe._get_client")
class TestStripeSubscriptions:
    def test_returns_subscriptions(self, mock_get: MagicMock) -> None:
        client = MagicMock()
        client.is_available.return_value = True
        client.list_subscriptions.return_value = {"data": [{"id": "sub_1"}]}
        mock_get.return_value = client

        result = stripe_subscriptions()
        assert len(result["data"]) == 1


@patch("mcp_server.tools.stripe._get_client")
class TestStripeCharges:
    def test_returns_charges(self, mock_get: MagicMock) -> None:
        client = MagicMock()
        client.is_available.return_value = True
        client.list_charges.return_value = {"data": []}
        mock_get.return_value = client

        result = stripe_charges()
        assert result["data"] == []


@patch("mcp_server.tools.stripe._get_client")
class TestStripeDisputes:
    def test_returns_disputes(self, mock_get: MagicMock) -> None:
        client = MagicMock()
        client.is_available.return_value = True
        client.list_disputes.return_value = {"data": []}
        mock_get.return_value = client

        result = stripe_disputes()
        assert result["data"] == []
