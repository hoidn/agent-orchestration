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
    "orchestrator.workflow.trial",
    "orchestrator.workflow.adjudication",
    "orchestrator.cli.commands.trial",
    "orchestrator.workflow.elaboration",
]
# A module that held one former public name of each removed package or module.
FORMER_PUBLIC_MODULES = [
    "orchestrator.workflow.provider_peer_group.protocol",
    "orchestrator.workflow.provider_supervision.contracts",
    "orchestrator.workflow.legacy_provider_quarantine",
    "orchestrator.cli.commands.peer",
    "orchestrator.workflow.trial.config",
    "orchestrator.workflow.adjudication.scoring",
    "orchestrator.cli.commands.trial",
    "orchestrator.workflow.elaboration",
]
REMOVED_COMMANDS = [
    ["peer-ready"], ["peer-send", "b", "m"], ["peer-ack", "m1"], ["peer-finish"],
    ["trial", "w.orc", "--entry-workflow", "e"],
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


# The bundle-era IR modules that the Workflow Lisp frontend no longer imports.
OLD_IR_MODULES = [
    f"orchestrator.workflow.{name}"
    for name in ("surface_ast", "loaded_bundle", "executable_ir", "core_ast", "semantic_ir", "runtime_plan")
]
FRONTEND_PACKAGES = ["orchestrator/workflow_lisp", "orchestrator/py", "orchestrator/lsp"]


@pytest.mark.parametrize("package", FRONTEND_PACKAGES)
def test_frontend_imports_nothing_from_the_old_ir_stack(package: str) -> None:
    paths = sorted((REPO / package).rglob("*.py"))
    importers = [
        f"{path.relative_to(REPO)}: {name}"
        for path in paths
        for name in sorted(_imported_modules(path))
        if any(name == module or name.startswith(module + ".") for module in OLD_IR_MODULES)
    ]
    assert (bool(paths), importers) == (True, [])


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


MACRO_OR_IMPORT_SOURCES = {
    "macro": {"main.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defmacro compare () (trial :arms ()))
  (defworkflow run () -> Int (let* ((ignored (compare))) 1)))
'''},
    "imported": {
        "helper.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule helper) (export one compare)
  (defworkflow one () -> Int 1)
  (defworkflow compare () -> Int (trial :arms ())))
''',
        "main.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (import helper :as h :only (one)) (export run)
  (defworkflow run () -> Int (call h.one)))
'''},
}


@pytest.mark.parametrize("where", sorted(MACRO_OR_IMPORT_SOURCES))
def test_retired_form_refuses_inside_a_macro_expansion_or_an_imported_module(tmp_path: Path, where: str) -> None:
    for name, text in MACRO_OR_IMPORT_SOURCES[where].items():
        (tmp_path / name).write_text(text, encoding="utf-8")

    result = cli(tmp_path, "compile", "main.orc")

    lines = [line for line in result.stderr.splitlines() if "[form_retired]" in line]
    assert (result.returncode, len(lines), lines and "archive/dead-executors-2026-11-11" in lines[0]) == (2, 1, True), result.stderr


def test_let_binder_named_like_a_retired_form_still_compiles(tmp_path: Path) -> None:
    (tmp_path / "main.orc").write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defworkflow run ((n Int)) -> Int (let* ((trial (+ n 1))) trial)))
''', encoding="utf-8")

    result = cli(tmp_path, "run", "main.orc", "--input", "n=1")

    assert (result.returncode, result.stdout.splitlines()[-1:]) == (0, ["2"]), result.stderr
