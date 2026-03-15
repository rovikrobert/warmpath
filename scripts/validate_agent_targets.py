"""Validate that agent scan configs reference targets that exist in the codebase.

Checks:
  1. Product team page targets (PERSONAS key_pages + PERSONA_JOURNEYS) → frontend/src/pages/*.{jsx,tsx}
  2. Data team table targets (DATABASE_TABLES + ALL_TABLES) → app/models/**/__tablename__

Stdlib-only — runs in CI without installing project requirements.

Usage:
    python3 scripts/validate_agent_targets.py          # validate
    python3 scripts/validate_agent_targets.py --fix     # show suggested removals
"""

from __future__ import annotations

import ast
import glob
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = REPO_ROOT / "frontend" / "src" / "pages"
MODELS_DIR = REPO_ROOT / "app" / "models"
PRODUCT_CONFIG = REPO_ROOT / "product_team" / "shared" / "config.py"
DATA_CONFIG = REPO_ROOT / "data_team" / "shared" / "config.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_page_files() -> set[str]:
    """Return set of page component names from frontend/src/pages/*.{jsx,tsx}."""
    names: set[str] = set()
    for ext in ("jsx", "tsx"):
        for path in glob.glob(str(PAGES_DIR / f"*.{ext}")):
            names.add(Path(path).stem)
    return names


def _extract_tablenames() -> set[str]:
    """Parse all model files via AST to find __tablename__ string assignments."""
    tablenames: set[str] = set()
    for py_path in sorted(MODELS_DIR.glob("*.py")):
        try:
            tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
        except SyntaxError:
            print(f"  WARNING: could not parse {py_path.relative_to(REPO_ROOT)}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "__tablename__"
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)
                    ):
                        tablenames.add(node.value.value)
    return tablenames


def _pages_from_personas(dict_node: ast.Dict) -> set[str]:
    """Extract page names from a PERSONAS dict AST node."""
    pages: set[str] = set()
    for val in dict_node.values:
        if not isinstance(val, ast.Dict):
            continue
        for k, v in zip(val.keys, val.values, strict=True):
            if (
                isinstance(k, ast.Constant)
                and k.value == "key_pages"
                and isinstance(v, ast.List)
            ):
                for elt in v.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        pages.add(elt.value)
    return pages


def _pages_from_journeys(dict_node: ast.Dict) -> set[str]:
    """Extract page names from a PERSONA_JOURNEYS dict AST node."""
    pages: set[str] = set()
    for val in dict_node.values:
        if not isinstance(val, ast.List):
            continue
        for journey in val.elts:
            if not isinstance(journey, ast.List):
                continue
            for elt in journey.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    pages.add(elt.value)
    return pages


def _extract_product_pages(tree: ast.Module) -> dict[str, set[str]]:
    """Extract page names from PERSONAS and PERSONA_JOURNEYS in product config AST.

    Returns {"PERSONAS": {pages...}, "PERSONA_JOURNEYS": {pages...}}.
    """
    result: dict[str, set[str]] = {"PERSONAS": set(), "PERSONA_JOURNEYS": set()}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "PERSONAS" and isinstance(node.value, ast.Dict):
                result["PERSONAS"] = _pages_from_personas(node.value)
            elif target.id == "PERSONA_JOURNEYS" and isinstance(node.value, ast.Dict):
                result["PERSONA_JOURNEYS"] = _pages_from_journeys(node.value)

    return result


def _extract_data_tables(tree: ast.Module) -> set[str]:
    """Extract table names from DATABASE_TABLES dict in data config AST."""
    tables: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id == "DATABASE_TABLES"
                and isinstance(node.value, ast.Dict)
            ):
                for val in node.value.values:
                    if not isinstance(val, ast.List):
                        continue
                    for elt in val.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            tables.add(elt.value)
    return tables


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_pages(fix: bool = False) -> list[str]:
    """Check product team page targets against actual page files."""
    errors: list[str] = []
    actual_pages = _extract_page_files()

    if not actual_pages:
        errors.append(f"No page files found in {PAGES_DIR.relative_to(REPO_ROOT)}/")
        return errors

    if not PRODUCT_CONFIG.exists():
        errors.append(
            f"Product config not found: {PRODUCT_CONFIG.relative_to(REPO_ROOT)}"
        )
        return errors

    tree = ast.parse(
        PRODUCT_CONFIG.read_text(encoding="utf-8"), filename=str(PRODUCT_CONFIG)
    )
    config_pages = _extract_product_pages(tree)

    for source, pages in config_pages.items():
        for page in sorted(pages):
            if page not in actual_pages:
                msg = (
                    f"STALE: {source} references '{page}' but no "
                    f"{page}.jsx/.tsx exists in frontend/src/pages/"
                )
                errors.append(msg)
                if fix:
                    print(
                        f"  --fix: remove '{page}' from {source} in product_team/shared/config.py"
                    )

    return errors


def validate_tables(fix: bool = False) -> list[str]:
    """Check data team table targets against actual model __tablename__ values."""
    errors: list[str] = []
    actual_tables = _extract_tablenames()

    if not actual_tables:
        errors.append(
            f"No __tablename__ values found in {MODELS_DIR.relative_to(REPO_ROOT)}/"
        )
        return errors

    if not DATA_CONFIG.exists():
        errors.append(f"Data config not found: {DATA_CONFIG.relative_to(REPO_ROOT)}")
        return errors

    tree = ast.parse(DATA_CONFIG.read_text(encoding="utf-8"), filename=str(DATA_CONFIG))
    config_tables = _extract_data_tables(tree)

    for table in sorted(config_tables):
        if table not in actual_tables:
            msg = (
                f"STALE: DATABASE_TABLES references '{table}' but no model "
                f"with __tablename__ = '{table}' found in app/models/"
            )
            errors.append(msg)
            if fix:
                print(
                    f"  --fix: remove '{table}' from DATABASE_TABLES in data_team/shared/config.py"
                )

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    fix = "--fix" in sys.argv

    print("=" * 60)
    print("Agent Config Target Validation")
    print("=" * 60)

    # --- Page targets ---
    print("\n[1/2] Product team page targets")
    actual_pages = _extract_page_files()
    print(f"  Found {len(actual_pages)} page files in frontend/src/pages/")

    page_errors = validate_pages(fix=fix)
    if page_errors:
        for e in page_errors:
            print(f"  ERROR: {e}")
    else:
        print("  OK: all page targets exist")

    # --- Table targets ---
    print("\n[2/2] Data team table targets")
    actual_tables = _extract_tablenames()
    print(f"  Found {len(actual_tables)} __tablename__ values in app/models/")

    table_errors = validate_tables(fix=fix)
    if table_errors:
        for e in table_errors:
            print(f"  ERROR: {e}")
    else:
        print("  OK: all table targets exist")

    # --- Summary ---
    all_errors = page_errors + table_errors
    print(f"\n{'=' * 60}")
    if all_errors:
        print(f"FAILED: {len(all_errors)} stale target(s) found")
        if not fix:
            print("Run with --fix for suggested removals")
        return 1
    else:
        print("PASSED: all agent scan targets are valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
