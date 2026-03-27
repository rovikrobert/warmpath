"""CI check: detect N+1 query patterns (db.execute inside loops).

Walks the Python AST looking for `.execute()` calls inside for/while/async-for
loops. Exits non-zero when violations are found.

Allowlisted patterns (intentional pagination, single-yield generators) can be
suppressed with an inline `# n1-ok` comment on the execute() line.

Usage:
    python3 scripts/check_n_plus_one.py [directory]  # default: app/
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


class _N1Visitor(ast.NodeVisitor):
    """Find .execute() calls nested inside loops."""

    def __init__(self, source_lines: list[str]) -> None:
        self.hits: list[tuple[int, int]] = []  # (execute_line, loop_line)
        self._loop_stack: list[ast.AST] = []
        self._lines = source_lines

    # -- loop entry/exit ------------------------------------------------

    def _enter_loop(self, node: ast.AST) -> None:
        self._loop_stack.append(node)
        self.generic_visit(node)
        self._loop_stack.pop()

    def visit_For(self, node: ast.For) -> None:
        self._enter_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._enter_loop(node)

    def visit_While(self, node: ast.While) -> None:
        self._enter_loop(node)

    # -- execute detection ---------------------------------------------

    def visit_Await(self, node: ast.Await) -> None:
        if self._loop_stack:
            self._check(node.value, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self._loop_stack:
            self._check(node, node.lineno)
        self.generic_visit(node)

    def _check(self, node: ast.AST, lineno: int) -> None:
        if not isinstance(node, ast.Call):
            return
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "execute":
            # Allow suppression via inline comment
            src_line = self._lines[lineno - 1] if lineno <= len(self._lines) else ""
            if "# n1-ok" in src_line:
                return
            loop_line = self._loop_stack[-1].lineno  # type: ignore[attr-defined]
            self.hits.append((lineno, loop_line))


def scan_file(path: Path) -> list[tuple[int, int]]:
    """Return list of (execute_line, loop_line) for violations in *path*."""
    source = path.read_text()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    visitor = _N1Visitor(source.splitlines())
    visitor.visit(tree)
    return visitor.hits


_DEFAULT_ROOTS = [
    "app",
    "ops_team",
    "agents",
    "data_team",
    "product_team",
    "finance_team",
    "gtm_team",
    "mcp_server",
]


def main() -> int:
    roots = (
        [Path(sys.argv[1])]
        if len(sys.argv) > 1
        else [Path(r) for r in _DEFAULT_ROOTS if Path(r).is_dir()]
    )
    violations: list[str] = []

    for root in roots:
        for py_file in sorted(root.rglob("*.py")):
            if "__pycache__" in py_file.parts:
                continue
            for exec_line, loop_line in scan_file(py_file):
                violations.append(
                    f"  {py_file}:{exec_line}  .execute() inside loop at line {loop_line}"
                )

    if violations:
        print(f"N+1 query pattern detected ({len(violations)} violation(s)):")
        print("\n".join(violations))
        print(
            "\nFix: batch into a single query with an IN clause, or add '# n1-ok' if intentional."
        )
        return 1

    print("No N+1 query patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
