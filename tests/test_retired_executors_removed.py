"""The retired executor packages and their commands are gone, and nothing still imports them."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from tests.test_cli_run_output import cli

REPO = Path(__file__).parents[1]
REMOVED_PACKAGES = [
    "orchestrator.workflow.provider_peer_group",
    "orchestrator.workflow.provider_supervision",
    "orchestrator.workflow.legacy_provider_quarantine",
]
REMOVED_COMMANDS = [
    ["peer-ready"], ["peer-send", "b", "m"], ["peer-ack", "m1"], ["peer-finish"],
]


def _imported_modules(path: Path) -> set[str]:
    package = list(path.relative_to(REPO).parent.parts)
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            module = ".".join(base + ([node.module] if node.module else []))
            names.update([module, *(f"{module}.{alias.name}" for alias in node.names)])
    return names


@pytest.mark.parametrize("package", REMOVED_PACKAGES)
def test_removed_packages_are_absent(package: str) -> None:
    assert importlib.util.find_spec(package) is None


@pytest.mark.parametrize("package", REMOVED_PACKAGES)
def test_nothing_imports_removed_packages(package: str) -> None:
    importers = [
        str(path.relative_to(REPO))
        for top in ("orchestrator", "tests")
        for path in sorted((REPO / top).rglob("*.py"))
        if any(
            name == package or name.startswith(package + ".")
            for name in _imported_modules(path)
        )
    ]
    assert importers == []


@pytest.mark.parametrize("argv", REMOVED_COMMANDS, ids=lambda argv: argv[0])
def test_removed_commands_are_refused(tmp_path: Path, argv: list[str]) -> None:
    result = cli(tmp_path, *argv)

    assert (result.returncode, "invalid choice" in result.stderr, list(tmp_path.iterdir())) == (2, True, [])
