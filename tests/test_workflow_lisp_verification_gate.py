from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage1_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import build_syntax_module


REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_PATH = REPO_ROOT / "docs" / "workflow_lisp_g6_verification_gate.json"
BUILTIN_STDLIB_ROOT = REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules" / "std"
FORBIDDEN_STUB_FORMS = (
    "defresource",
    "deftransition",
    "materialize-view",
    "resource-transition",
)


def _verification_gate_module():
    return importlib.import_module("orchestrator.workflow_lisp.verification_gate")


def _write_gate(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "verification_gate.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _base_gate(*, status: str = "pending") -> dict[str, object]:
    gate_module = _verification_gate_module()
    return {
        "schema_version": gate_module.G6_VERIFICATION_GATE_SCHEMA_VERSION,
        "counted_suites": [
            {
                "suite": "tests/test_workflow_lisp_generic_stdlib_composition.py",
                "scope_class": "proving_surface",
                "reason": "Imported generic stdlib proof consumed by the G6 verification gate.",
            }
        ],
        "builtin_stdlib_inventory": [
            {
                "module": "std/context",
                "status": "landed",
                "owner": "workflow-lisp-generic-core-g5-context-generalization",
            },
            {
                "module": "std/phase",
                "status": "landed",
                "owner": "accepted-baseline",
            },
            {
                "module": "std/resource",
                "status": status,
                "owner": "workflow-lisp-generic-core-g6-stdlib-migration-phase-drain-forms",
            },
            {
                "module": "std/drain",
                "status": "pending",
                "owner": "workflow-lisp-generic-core-g6-stdlib-migration-phase-drain-forms",
            },
        ],
        "later_tranche_suites": [
            {
                "suite": "tests/test_workflow_lisp_stdlib_form_migration.py",
                "owner": "workflow-lisp-generic-core-g6-stdlib-migration-phase-drain-forms",
                "reason": "Later-tranche G6 form-routing coverage.",
            }
        ],
    }


def _module_path(module_name: str) -> Path:
    return BUILTIN_STDLIB_ROOT / f"{module_name.split('/', 1)[1]}.orc"


def _is_git_tracked(path: Path) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _assert_stage1_compiles(module_name: str) -> None:
    result = compile_stage1_entrypoint(_module_path(module_name))
    assert result.entry_module.module_name == module_name


def _assert_pending_import_fails(module_name: str, tmp_path: Path) -> None:
    module_basename = module_name.split("/", 1)[1]
    entrypoint = tmp_path / "demo" / "entry.orc"
    entrypoint.parent.mkdir(parents=True, exist_ok=True)
    entrypoint.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                f"  (import {module_name} :only (placeholder))",
                "  (export LocalRecord)",
                "  (defrecord LocalRecord",
                "    (value String)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_entrypoint(entrypoint, source_roots=(tmp_path,))

    diagnostics = excinfo.value.diagnostics
    assert diagnostics
    assert diagnostics[0].code == "module_not_found"
    assert module_basename in diagnostics[0].message


def _iter_suite_sources(gate) -> list[tuple[str, str]]:
    gate_module = _verification_gate_module()
    return [
        (suite_path, (REPO_ROOT / suite_path).read_text(encoding="utf-8"))
        for suite_path in gate_module.counted_suite_paths(gate)
    ]


def _iter_checked_in_orc_fixtures(source: str) -> tuple[Path, ...]:
    filenames = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.endswith(".orc")
    }
    fixtures_root = REPO_ROOT / "tests" / "fixtures"
    resolved: list[Path] = []
    for filename in sorted(filenames):
        literal_path = REPO_ROOT / filename
        if literal_path.is_file():
            resolved.append(literal_path)
            continue
        normalized = filename.lstrip("./")
        suffix_matches = sorted(
            path
            for path in fixtures_root.rglob("*.orc")
            if path.is_file() and path.relative_to(fixtures_root).as_posix().endswith(normalized)
        )
        if len(suffix_matches) == 1:
            resolved.append(suffix_matches[0])
            continue
        basename_matches = sorted(path for path in fixtures_root.rglob(Path(filename).name) if path.is_file())
        if len(basename_matches) == 1:
            resolved.append(basename_matches[0])
    return tuple(dict.fromkeys(path.resolve() for path in resolved))


def _infer_fixture_source_root(path: Path) -> Path:
    syntax_module = build_syntax_module(read_sexpr_file(path))
    module_name = syntax_module.module_name
    if module_name is None:
        return path.parent
    expected_parts = Path(*module_name.split("/")).with_suffix(".orc").parts
    actual_parts = path.parts
    if tuple(actual_parts[-len(expected_parts) :]) != expected_parts:
        return path.parent
    return path.parents[len(expected_parts) - 1]


def _resolve_local_fixture_import(module_name: str, *, source_root: Path) -> Path | None:
    candidate = (source_root / Path(*module_name.split("/"))).with_suffix(".orc")
    if not candidate.is_file():
        return None
    return candidate.resolve()


def _iter_orc_fixture_import_closure(fixtures: tuple[Path, ...]) -> tuple[Path, ...]:
    resolved: list[Path] = []
    seen: set[Path] = set()
    pending = list(fixtures)

    while pending:
        fixture_path = pending.pop(0).resolve()
        if fixture_path in seen:
            continue
        seen.add(fixture_path)
        resolved.append(fixture_path)

        syntax_module = build_syntax_module(read_sexpr_file(fixture_path))
        source_root = _infer_fixture_source_root(fixture_path)
        for import_directive in syntax_module.imports:
            imported_path = _resolve_local_fixture_import(
                import_directive.module_name,
                source_root=source_root,
            )
            if imported_path is not None and imported_path not in seen:
                pending.append(imported_path)

    return tuple(resolved)


def _iter_checked_in_orc_fixture_closure(source: str) -> tuple[Path, ...]:
    return _iter_orc_fixture_import_closure(_iter_checked_in_orc_fixtures(source))


def _suite_imports_module(source: str, module_name: str) -> bool:
    return re.search(r"\(import\s+" + re.escape(module_name) + r"\b", source) is not None


def _assert_fixture_closure_has_no_pending_imports(
    *,
    suite_path: str,
    fixture_paths: tuple[Path, ...],
    pending_modules: set[str],
) -> None:
    for fixture_path in fixture_paths:
        fixture_source = fixture_path.read_text(encoding="utf-8")
        try:
            display_path = fixture_path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            display_path = fixture_path.as_posix()
        for module_name in pending_modules:
            assert not _suite_imports_module(fixture_source, module_name), (
                f"{suite_path} fixture {display_path} imports pending builtin {module_name}"
            )


def test_load_verification_gate_rejects_unknown_fields(tmp_path: Path) -> None:
    gate_module = _verification_gate_module()
    payload = _base_gate()
    payload["unexpected"] = True

    with pytest.raises(ValueError, match="unexpected"):
        gate_module.load_verification_gate(_write_gate(tmp_path, payload))


def test_load_verification_gate_rejects_missing_row_metadata(tmp_path: Path) -> None:
    gate_module = _verification_gate_module()
    payload = _base_gate()
    del payload["counted_suites"][0]["reason"]

    with pytest.raises(ValueError, match="counted_suites\\[0\\]\\.reason"):
        gate_module.load_verification_gate(_write_gate(tmp_path, payload))


@pytest.mark.parametrize(
    ("field_path", "mutator"),
    [
        ("counted_suites[0].scope_class", lambda payload: payload["counted_suites"][0].__setitem__("scope_class", "wrong")),  # type: ignore[index]
        ("builtin_stdlib_inventory[0].status", lambda payload: payload["builtin_stdlib_inventory"][0].__setitem__("status", "wrong")),  # type: ignore[index]
        ("later_tranche_suites[0].suite", lambda payload: payload["later_tranche_suites"][0].__setitem__("suite", "")),  # type: ignore[index]
    ],
)
def test_load_verification_gate_rejects_invalid_row_values(
    tmp_path: Path,
    field_path: str,
    mutator,
) -> None:
    gate_module = _verification_gate_module()
    payload = _base_gate()
    mutator(payload)

    with pytest.raises(ValueError, match=re.escape(field_path)):
        gate_module.load_verification_gate(_write_gate(tmp_path, payload))


def test_checked_in_gate_references_existing_suite_files() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    for suite_path in [
        *gate_module.counted_suite_paths(gate),
        *(row.suite for row in gate.later_tranche_suites),
    ]:
        assert (REPO_ROOT / suite_path).is_file(), suite_path


def test_checked_in_gate_suites_collect_cleanly() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    for suite_path in [
        *gate_module.counted_suite_paths(gate),
        *(row.suite for row in gate.later_tranche_suites),
    ]:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", suite_path, "-q"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout


def test_checked_in_gate_counted_and_later_tranche_suites_are_disjoint() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    counted = set(gate_module.counted_suite_paths(gate))
    later = {row.suite for row in gate.later_tranche_suites}

    assert counted.isdisjoint(later)


def test_checked_in_gate_phase_stdlib_counted_suite_names_owner_lane_self_hosting_proof() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    phase_stdlib_row = next(
        row for row in gate.counted_suites if row.suite == "tests/test_workflow_lisp_phase_stdlib.py"
    )

    assert "std/phase" in phase_stdlib_row.reason
    assert "owner-lane" in phase_stdlib_row.reason
    assert "self-hosting" in phase_stdlib_row.reason


def test_checked_in_gate_declares_allowed_value_classes() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    assert {row.scope_class for row in gate.counted_suites} <= gate_module.SCOPE_CLASS_VALUES
    assert {row.status for row in gate.builtin_stdlib_inventory} <= gate_module.BUILTIN_STDLIB_STATUS_VALUES


def test_checked_in_gate_landed_modules_are_git_tracked() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    for row in gate.builtin_stdlib_inventory:
        if row.status != "landed":
            continue
        assert _is_git_tracked(_module_path(row.module)), row.module


def test_checked_in_gate_landed_and_stub_modules_exist_and_compile() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    for row in gate.builtin_stdlib_inventory:
        if row.status not in {"landed", "stub"}:
            continue
        assert _module_path(row.module).is_file(), row.module
        _assert_stage1_compiles(row.module)


def test_checked_in_gate_stub_modules_do_not_ship_g6_semantics() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    for row in gate.builtin_stdlib_inventory:
        if row.status != "stub":
            continue
        source = _module_path(row.module).read_text(encoding="utf-8")
        for form_name in FORBIDDEN_STUB_FORMS:
            assert f"({form_name}" not in source, (
                f"{row.module} stub overclaims G6 semantics via {form_name}"
            )


def test_checked_in_gate_pending_modules_are_not_git_tracked(tmp_path: Path) -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    for row in gate.builtin_stdlib_inventory:
        if row.status != "pending":
            continue
        module_path = _module_path(row.module)
        assert not _is_git_tracked(module_path), row.module
        if not module_path.exists():
            _assert_pending_import_fails(row.module, tmp_path)


def test_checked_in_gate_inventory_covers_builtin_tree() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    declared = {row.module for row in gate.builtin_stdlib_inventory}
    observed = {f"std/{path.stem}" for path in BUILTIN_STDLIB_ROOT.glob("*.orc")}

    assert observed <= declared


def test_checked_in_gate_counted_suites_do_not_reference_pending_builtins() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)
    pending_modules = {row.module for row in gate.builtin_stdlib_inventory if row.status == "pending"}

    for suite_path, source in _iter_suite_sources(gate):
        for module_name in pending_modules:
            assert not _suite_imports_module(source, module_name), (
                f"{suite_path} imports pending builtin {module_name}"
            )


def test_iter_checked_in_orc_fixtures_resolves_nested_module_paths() -> None:
    source = (REPO_ROOT / "tests/test_workflow_lisp_generic_stdlib_composition.py").read_text(
        encoding="utf-8"
    )

    resolved = {path.relative_to(REPO_ROOT).as_posix() for path in _iter_checked_in_orc_fixtures(source)}

    assert (
        "tests/fixtures/workflow_lisp/modules/valid/generic_stdlib_composition/"
        "generic_stdlib_composition/entry.orc"
    ) in resolved
    assert (
        "tests/fixtures/workflow_lisp/modules/valid/generic_stdlib_composition/"
        "generic_stdlib_composition/helper.orc"
    ) in resolved


def test_iter_checked_in_orc_fixture_closure_follows_local_imports() -> None:
    source = 'ENTRY_FIXTURE = "tests/fixtures/workflow_lisp/modules/valid/generic_stdlib_composition/generic_stdlib_composition/entry.orc"\n'

    resolved = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in _iter_checked_in_orc_fixture_closure(source)
    }

    assert (
        "tests/fixtures/workflow_lisp/modules/valid/generic_stdlib_composition/"
        "generic_stdlib_composition/entry.orc"
    ) in resolved
    assert (
        "tests/fixtures/workflow_lisp/modules/valid/generic_stdlib_composition/"
        "generic_stdlib_composition/helper.orc"
    ) in resolved


def test_orc_fixture_import_closure_fails_on_transitive_pending_builtin(tmp_path: Path) -> None:
    source_root = tmp_path / "demo"
    entry_path = source_root / "demo" / "entry.orc"
    helper_path = source_root / "demo" / "helper.orc"
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    entry_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import demo/helper :only (HelperRecord))",
                "  (export EntryRecord)",
                "  (defrecord EntryRecord",
                "    (value String)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    helper_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/helper)",
                "  (import std/resource :only (ResourceView))",
                "  (export HelperRecord)",
                "  (defrecord HelperRecord",
                "    (value String)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    fixture_paths = _iter_orc_fixture_import_closure((entry_path,))

    with pytest.raises(AssertionError, match=r"imports pending builtin std/resource"):
        _assert_fixture_closure_has_no_pending_imports(
            suite_path="tests/test_demo_suite.py",
            fixture_paths=fixture_paths,
            pending_modules={"std/resource"},
        )


def test_checked_in_gate_counted_suite_fixtures_do_not_import_pending_builtins() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)
    pending_modules = {row.module for row in gate.builtin_stdlib_inventory if row.status == "pending"}

    for suite_path, source in _iter_suite_sources(gate):
        _assert_fixture_closure_has_no_pending_imports(
            suite_path=suite_path,
            fixture_paths=_iter_checked_in_orc_fixture_closure(source),
            pending_modules=pending_modules,
        )
