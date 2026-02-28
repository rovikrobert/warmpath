"""Tests for the root LangGraph definition.

Tests graph structure (nodes, edges) without executing LLM calls.
"""

from app.agent_runtime.graph import build_graph


def test_build_graph_has_required_nodes():
    """Root graph contains all expected nodes."""
    graph = build_graph()
    node_names = set(graph.nodes.keys())
    assert "classify" in node_names
    assert "cos_route" in node_names
    assert "synthesize" in node_names
    assert "evaluate" in node_names


def test_build_graph_compiles_without_error():
    """Graph compiles successfully (valid edges, no dangling nodes)."""
    graph = build_graph()
    # compile() validates the graph structure
    compiled = graph.compile()
    assert compiled is not None
