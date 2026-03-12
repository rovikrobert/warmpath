"""Per-endpoint query count and latency budgets.

Used by:
  1. DB instrumentation middleware to log warnings when exceeded
  2. CI test to verify no endpoint exceeds its budget
"""

# (method, path_prefix) -> {"max_queries": N, "max_latency_ms": M}
ENDPOINT_BUDGETS: dict[tuple[str, str], dict[str, int]] = {
    ("GET", "/api/v1/contacts"): {"max_queries": 8, "max_latency_ms": 500},
    ("GET", "/api/v1/feed"): {"max_queries": 6, "max_latency_ms": 300},
    ("GET", "/api/v1/feed/count"): {"max_queries": 3, "max_latency_ms": 100},
    ("GET", "/api/v1/search"): {"max_queries": 10, "max_latency_ms": 500},
    ("GET", "/api/v1/dashboard"): {"max_queries": 12, "max_latency_ms": 800},
    ("GET", "/api/v1/credits"): {"max_queries": 4, "max_latency_ms": 200},
    ("GET", "/api/v1/marketplace/my-listings"): {
        "max_queries": 8,
        "max_latency_ms": 400,
    },
    ("POST", "/api/v1/marketplace/search"): {"max_queries": 15, "max_latency_ms": 1000},
    ("GET", "/api/v1/applications"): {"max_queries": 8, "max_latency_ms": 500},
    ("GET", "/health"): {"max_queries": 0, "max_latency_ms": 100},
}


def get_budget(method: str, path: str) -> dict[str, int] | None:
    """Find the matching budget for a request. Returns None if no budget defined."""
    for (m, prefix), budget in ENDPOINT_BUDGETS.items():
        if method == m and path.startswith(prefix):
            return budget
    return None
