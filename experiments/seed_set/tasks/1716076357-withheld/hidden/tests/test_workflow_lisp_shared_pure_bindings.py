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


def test_repeated_binding_is_shared_and_adds_one_node_per_use(tmp_path: Path) -> None:
    ten = _compiled_payload(tmp_path / "ten", 10)
    eleven = _compiled_payload(tmp_path / "eleven", 11)
    ten_expr = ten["expr"]
    eleven_expr = eleven["expr"]

    assert ten["pure_expr_schema_version"] == 3
    assert ten_expr["kind"] == "let"
    assert [binding["name"] for binding in ten_expr["bindings"]] == [
        "increment",
        "forwarded",
    ]
    assert _node_count(eleven_expr) - _node_count(ten_expr) == 1


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


def test_mlevolve_search_controller_runs_through_the_public_entrypoint(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    source_root = tmp_path
    project = source_root / "mlevolve_pair"
    shutil.copytree(Path(__file__).resolve().parents[1] / "experiments" / "mlevolve_pair", project)
    source = project / "search.orc"
    source.write_text(source.read_text(encoding="utf-8").replace("run-search", "run"), encoding="utf-8")
    providers = source_root / "providers.json"
    prompts = source_root / "prompts.json"
    providers.write_text("{}", encoding="utf-8")
    prompts.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(source_root)
    validate = pure_projection_lowering.validate_pure_expr_payload
    node_counts: list[int] = []

    def count_validated_payload(payload, **kwargs):
        node_counts.append(_node_count(payload["expr"]))
        return validate(payload, **kwargs)

    monkeypatch.setattr(
        pure_projection_lowering,
        "validate_pure_expr_payload",
        count_validated_payload,
    )

    commands = json.loads((project / "commands.json").read_text(encoding="utf-8"))
    for binding in commands.values():
        binding["stable_command"] = [
            item.replace("experiments/mlevolve_pair/", "mlevolve_pair/")
            for item in binding["stable_command"]
        ]
    command_path = source_root / "commands.json"
    command_path.write_text(json.dumps(commands), encoding="utf-8")

    result = _public_run(
        {
            "source": source,
            "source_root": source_root,
            "providers": providers,
            "prompts": prompts,
            "commands": command_path,
        }
    )

    assert result.exit_code == 2
    assert "workflow_boundary_type_invalid" in caplog.text
    assert "mlevolve_pair/search.orc:91:25:" in caplog.text
    assert "mlevolve_pair/search.orc:38:3" in caplog.text
    assert "pure_expr_payload_too_large" not in caplog.text
    assert node_counts and max(node_counts) <= 256
