"""The retired executor packages and their commands are gone, and nothing still imports them."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from tests.test_cli_run_output import cli

REPO = Path(__file__).parents[1]
REMOVED_PACKAGES = [
    "orchestrator.workflow.provider_peer_group",
    "orchestrator.workflow.provider_supervision",
    "orchestrator.workflow.legacy_provider_quarantine",
    "orchestrator.cli.commands.peer",
]
# A module that held one former public name of each removed package or module.
FORMER_PUBLIC_MODULES = [
    "orchestrator.workflow.provider_peer_group.protocol",
    "orchestrator.workflow.provider_supervision.contracts",
    "orchestrator.workflow.legacy_provider_quarantine",
    "orchestrator.cli.commands.peer",
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
    # Source files, not find_spec: a leftover ignored __pycache__ directory is a namespace package.
    path = REPO / package.replace(".", "/")
    assert (path.with_suffix(".py").exists(), sorted(path.rglob("*.py"))) == (False, [])


@pytest.mark.parametrize("module", FORMER_PUBLIC_MODULES)
def test_former_public_modules_do_not_import(module: str) -> None:
    with pytest.raises(ImportError):
        importlib.import_module(module)


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


RETIRED_FORM_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
  (defmodule main) (export run)
  (defworkflow {holder} () -> Int
    ({form} :arms ()))
  {entry})
'''


@pytest.mark.parametrize("target", ["2.35", "2.40"])
@pytest.mark.parametrize("reached", [True, False], ids=["reached", "unreached"])
@pytest.mark.parametrize("form", ["trial"])
def test_retired_form_refuses_with_located_retirement_diagnostic(
    tmp_path: Path, form: str, target: str, reached: bool
) -> None:
    entry = "" if reached else "(defworkflow run () -> Int 1)"
    source = RETIRED_FORM_SOURCE.format(target=target, form=form, holder="run" if reached else "unused", entry=entry)
    (tmp_path / "main.orc").write_text(source, encoding="utf-8")

    result = cli(tmp_path, "compile", "main.orc")

    lines = [line for line in result.stderr.splitlines() if "[form_retired]" in line]
    assert (result.returncode, len(lines), lines and "main.orc:4:" in lines[0],
            lines and "archive/dead-executors-2026-11-11" in lines[0]) == (2, 1, True, True), result.stderr


def test_user_definition_named_like_a_retired_form_still_compiles(tmp_path: Path) -> None:
    (tmp_path / "main.orc").write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defproc trial ((n Int)) -> Int :effects () :lowering inline (+ n 1))
  (defworkflow run ((n Int)) -> Int (trial n)))
''', encoding="utf-8")

    result = cli(tmp_path, "run", "main.orc", "--input", "n=1")

    assert (result.returncode, result.stdout.splitlines()[-1:]) == (0, ["2"]), result.stderr
