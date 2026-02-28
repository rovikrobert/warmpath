"""Shared fixtures for MCP server tests."""

from __future__ import annotations

import os

os.environ.setdefault("AI_MOCK_MODE", "true")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("STRIPE_SECRET_KEY", "")
