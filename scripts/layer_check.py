#!/usr/bin/env python3
"""Check that dependencies point one way only, as the package docstring says.

``src/economic_regime_forecasting/__init__.py`` declares the layering:

    configuration  ->  (nothing)
    data           ->  configuration
    ...

That table is the specification, and until now nothing read it. This script
does: it parses the table out of the docstring, walks every import in the
package with ``ast``, and reports any edge the table does not permit.

The docstring stays the single source of truth. Change the declared layering
and the check follows; there is no second copy of the rules to drift.

    python3 scripts/layer_check.py             # human output, exit 1 on a violation
    python3 scripts/layer_check.py --json      # the same, machine-readable
    python3 scripts/layer_check.py --graph     # emit the adjacency the drawing uses

Stdlib only. Nothing imports this; it is operational glue.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

PACKAGE = "economic_regime_forecasting"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_CANNOT_TELL = 2

# `name  ->  a, b` or `name  ->  (prose meaning nothing)`
DECLARATION = re.compile(r"^\s{2,}([a-z_]+)\s*->\s*(.+?)\s*$")


def repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return start


def package_root(root: Path) -> Path:
    return root / "src" / PACKAGE


def declared_layers(root: Path) -> dict[str, set[str]]:
    """Parse the layer table out of the package docstring."""
    init = package_root(root) / "__init__.py"
    try:
        docstring = ast.get_docstring(ast.parse(init.read_text())) or ""
    except (OSError, SyntaxError, ValueError) as error:
        raise SystemExit(f"layer_check: cannot read {init}: {error}") from error

    layers: dict[str, set[str]] = {}
    for line in docstring.splitlines():
        match = DECLARATION.match(line)
        if not match:
            continue
        name, right = match.group(1), match.group(2)
        # A parenthetical is prose for "nothing": `(nothing)`, `(plain arrays; …)`.
        dependencies: set[str] = set()
        if not right.startswith("("):
            dependencies = {part.strip() for part in right.split(",") if part.strip()}
        layers[name] = dependencies
    return layers


def layer_of(path: Path, package: Path) -> str | None:
    """The layer a file belongs to, or None for orchestration at the package root."""
    try:
        relative = path.relative_to(package)
    except ValueError:
        return None
    parts = relative.parts
    if len(parts) > 1:
        return parts[0]
    return relative.stem  # a module sitting directly in the package root


def imported_layers(tree: ast.AST, own_layer: str | None) -> list[tuple[str, int]]:
    """Every (layer, lineno) this module imports from, absolute or relative."""
    found: list[tuple[str, int]] = []

    def record(module: str | None, line: int) -> None:
        if not module:
            return
        parts = module.split(".")
        if parts[0] == PACKAGE and len(parts) > 1:
            found.append((parts[1], line))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                record(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                record(node.module, node.lineno)
            elif node.level == 1:
                # `from .sibling import x` — same layer, always fine.
                continue
            else:
                # `from ..models import x` — the first segment names a layer.
                if node.module:
                    found.append((node.module.split(".")[0], node.lineno))
    return found


def scan(root: Path) -> dict:
    package = package_root(root)
    if not package.is_dir():
        raise SystemExit(f"layer_check: no package at {package}")

    layers = declared_layers(root)
    if not layers:
        raise SystemExit(
            "layer_check: the package docstring declares no layering. Expected lines of "
            "the form `    data           ->  configuration`."
        )

    violations: list[dict] = []
    edges: dict[str, dict[str, int]] = {}
    orchestration: list[str] = []
    checked = 0

    for path in sorted(package.rglob("*.py")):
        own = layer_of(path, package)
        if own is None:
            continue
        relative = path.relative_to(root).as_posix()
        if own not in layers:
            # A module the table does not mention: orchestration, exempt but named.
            if path.parent == package:
                orchestration.append(relative)
                continue
            violations.append(
                {
                    "file": relative,
                    "line": 1,
                    "from": own,
                    "to": "",
                    "why": f"layer {own!r} is on disk but not in the docstring table",
                }
            )
            continue

        checked += 1
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError as error:
            violations.append(
                {
                    "file": relative,
                    "line": error.lineno or 1,
                    "from": own,
                    "to": "",
                    "why": f"cannot parse: {error.msg}",
                }
            )
            continue

        for target, line in imported_layers(tree, own):
            if target == own:
                continue
            edges.setdefault(own, {})
            edges[own][target] = edges[own].get(target, 0) + 1
            if target not in layers:
                continue  # not a layer (a root-level module such as pipeline_gates)
            if target not in layers[own]:
                permitted = ", ".join(sorted(layers[own])) or "nothing"
                violations.append(
                    {
                        "file": relative,
                        "line": line,
                        "from": own,
                        "to": target,
                        "why": f"{own} may import {permitted} — not {target}",
                    }
                )

    return {
        "layers": {name: sorted(deps) for name, deps in layers.items()},
        "edges": {src: dict(sorted(dst.items())) for src, dst in sorted(edges.items())},
        "violations": violations,
        "files_checked": checked,
        "orchestration": sorted(orchestration),
    }


def report(result: dict) -> int:
    layers = result["layers"]
    print(f"declared layers ({len(layers)}): " + ", ".join(sorted(layers)))
    for name in sorted(layers):
        allowed = ", ".join(layers[name]) or "nothing"
        print(f"  {name:<16} -> {allowed}")

    if result["orchestration"]:
        print()
        print("orchestration (undeclared package-root modules, exempt):")
        for path in result["orchestration"]:
            print(f"  {path}")

    print()
    violations = result["violations"]
    if not violations:
        print(
            f"layer_check: {result['files_checked']} module(s) checked, "
            "every import points the declared way. OK."
        )
        return EXIT_OK

    print(f"layer_check: {len(violations)} violation(s).")
    for violation in violations:
        print(f"  {violation['file']}:{violation['line']}")
        print(f"    {violation['why']}")
    print()
    print(
        "Either the import is wrong, or the docstring table is out of date. "
        "The table is the specification, so decide which one is the defect."
    )
    return EXIT_VIOLATION


def main() -> int:
    parser = argparse.ArgumentParser(prog="layer_check.py", description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    parser.add_argument("--graph", action="store_true", help="emit only the layer adjacency")
    arguments = parser.parse_args()

    root = repo_root(Path.cwd())
    result = scan(root)

    if arguments.graph:
        print(json.dumps({"layers": result["layers"], "edges": result["edges"]}, indent=2))
        return EXIT_OK if not result["violations"] else EXIT_VIOLATION
    if arguments.json:
        print(json.dumps(result, indent=2))
        return EXIT_OK if not result["violations"] else EXIT_VIOLATION
    return report(result)


if __name__ == "__main__":
    raise SystemExit(main())
