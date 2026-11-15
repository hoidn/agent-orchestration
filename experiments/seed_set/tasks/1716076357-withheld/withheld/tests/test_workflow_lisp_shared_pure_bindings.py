from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
import shutil

from orchestrator.workflow_lisp.lowering import pure_projection as pure_projection_lowering
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from tests.test_workflow_lisp_generic_unions_runtime import (
    _public_run,
    _public_run_files,
)

def _source(uses: int) -> str:
    references = " ".join("forwarded" for _ in range(uses))
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.33")',
            "  (defmodule grt/entry)",
            "  (export run)",
            "  (defworkflow run ((n Int)) -> Int",
            f"    (let* ((increment (+ n 1)) (forwarded (+ increment 1)))",
            f"      (+ {references}))))",
        )
    )


def _compiled_payload(root: Path, uses: int) -> Mapping[str, object]:
    source = root / "grt" / "entry.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(_source(uses), encoding="utf-8")
    compiled = compile_stage3_module(
        source,
        lowering_route="wcc_m4",
        validate_shared=True,
        workspace_root=root,
    )
    return next(
        step.pure_projection["payload"]
        for step in compiled.validated_bundles["run"].surface.steps
        if step.pure_projection is not None
    )


def _node_count(value: object) -> int:
    if isinstance(value, Mapping):
        if not isinstance(value.get("kind"), str):
            return sum(
                _node_count(item)
                for key, item in value.items()
                if key not in {"type", "element_type", "result_element_type", "result_type", "binder"}
            )
        return 1 + sum(
            _node_count(item)
            for key, item in value.items()
            if key not in {"type", "element_type", "result_element_type", "result_type", "binder"}
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return sum(_node_count(item) for item in value)
    return 0




def test_hundred_uses_run_through_the_public_entrypoint(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "grt" / "entry.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(_source(100), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {}), input_file=_write_input(tmp_path, 10))

    assert result.exit_code == 0
    assert dict(result.workflow_outputs) == {"__result__": 1200}


def test_transitive_binding_keeps_nested_let_shadowing_through_public_entrypoint(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "grt" / "entry.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.33")',
                "  (defmodule grt/entry)",
                "  (export run)",
                "  (defun expanded-shadow ((n Int)) -> Int",
                "    (let* ((x n) (y (let* ((x (+ x 1))) x))) (+ x y)))",
                "  (defworkflow run ((value Int)) -> Int (expanded-shadow value)))",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    input_file = tmp_path / "inputs.json"
    input_file.write_text(json.dumps({"value": 3}), encoding="utf-8")

    result = _public_run(_public_run_files(tmp_path, {}), input_file=input_file)

    assert (result.exit_code, dict(result.workflow_outputs)) == (0, {"__result__": 7})


def test_reused_value_in_unselected_if_arm_remains_lazy(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "grt" / "entry.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.33")',
                "  (defmodule grt/entry)",
                "  (export run)",
                "  (defworkflow run ((take Bool) (n Int)) -> Int",
                "    (let* ((overflow (+ n 1))) (if take (+ overflow overflow) 0))))",
            )
        ),
        encoding="utf-8",
    )
    input_file = tmp_path / "inputs.json"
    input_file.write_text(
        json.dumps({"take": False, "n": 2**63 - 1}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {}), input_file=input_file)

    assert (result.exit_code, dict(result.workflow_outputs)) == (0, {"__result__": 0})


def test_record_mapping_with_fallible_field_remains_lazy_in_unselected_if_arm(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "grt" / "entry.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.33")',
                "  (defmodule grt/entry)",
                "  (export run)",
                "  (defrecord Box (value Int))",
                "  (defworkflow run ((take Bool) (n Int)) -> Int",
                "    (let* ((box (record Box :value (+ n 1))))",
                "      (if take (+ box.value box.value) 0))))",
            )
        ),
        encoding="utf-8",
    )
    input_file = tmp_path / "inputs.json"
    input_file.write_text(json.dumps({"take": False, "n": 2**63 - 1}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {}), input_file=input_file)

    assert (result.exit_code, dict(result.workflow_outputs)) == (0, {"__result__": 0})


def _write_input(root: Path, value: int) -> Path:
    path = root / "inputs.json"
    path.write_text(json.dumps({"n": value}), encoding="utf-8")
    return path


