from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage1_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


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


def _suite_imports_module(source: str, module_name: str) -> bool:
    return re.search(r"\(import\s+" + re.escape(module_name) + r"\b", source) is not None


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


def test_checked_in_gate_declares_allowed_value_classes() -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    assert {row.scope_class for row in gate.counted_suites} <= gate_module.SCOPE_CLASS_VALUES
    assert {row.status for row in gate.builtin_stdlib_inventory} <= gate_module.BUILTIN_STDLIB_STATUS_VALUES


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


def test_checked_in_gate_pending_modules_are_absent_and_fail_module_not_found(tmp_path: Path) -> None:
    gate_module = _verification_gate_module()
    gate = gate_module.load_verification_gate(GATE_PATH)

    for row in gate.builtin_stdlib_inventory:
        if row.status != "pending":
            continue
        assert not _module_path(row.module).exists(), row.module
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
