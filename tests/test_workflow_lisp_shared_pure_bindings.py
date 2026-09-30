from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
import shutil

from orchestrator.workflow.pure_expr import _validate_expr_node
from orchestrator.workflow_lisp.lowering import pure_projection as pure_projection_lowering
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from tests.test_workflow_lisp_generic_unions_runtime import (
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
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


def _node_count(payload: Mapping[str, object]) -> int:
    return _validate_expr_node(
        payload["expr"],
        bindings=payload["bindings"],
        schema_version=payload["pure_expr_schema_version"],
        local_bindings={},
    )


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
    assert _node_count(eleven) - _node_count(ten) == 1


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


def test_shared_bindings_can_change_which_failing_operation_is_reported(
    tmp_path: Path, monkeypatch
) -> None:
    sources = (
        "(let* ((q (/ 1.0 d)) (b (+ n 1))) "
        "(+ (int/to-float b) (+ q q)))",
        "(let* ((b (+ n 1)) (q (/ 1.0 d))) "
        "(+ (+ q q) (int/to-float (+ b b))))",
    )
    observed = []
    for index, body in enumerate(sources):
        root = tmp_path / str(index)
        source = root / "grt" / "entry.orc"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "\n".join(
                (
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.34")',
                    "  (defmodule grt/entry)",
                    "  (export run)",
                    f"  (defworkflow run ((n Int) (d Float)) -> Float {body}))",
                )
            ),
            encoding="utf-8",
        )
        input_file = root / "inputs.json"
        input_file.write_text(json.dumps({"n": 2**63 - 1, "d": 0.0}), encoding="utf-8")
        monkeypatch.chdir(root)
        result = _public_run(_public_run_files(root, {}), input_file=input_file)
        state = json.loads(
            next((root / ".orchestrate" / "runs").glob("*/state.json")).read_text(
                encoding="utf-8"
            )
        )
        error = next(
            step["error"]
            for step in state["steps"].values()
            if isinstance(step, dict) and isinstance(step.get("error"), dict)
        )
        assert result.exit_code == 1
        observed.append(error["type"])

    assert observed == ["pure_expr_division_by_zero", "pure_expr_overflow"]


def test_list_map_effect_state_binding_is_shared_without_changing_effects(
    tmp_path: Path, monkeypatch
) -> None:
    probe = _write_probe(
        tmp_path,
        "tick",
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "value = int(sys.argv[1])\n"
        "output = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        "output.write_text(json.dumps(value), encoding='utf-8')\n"
        "log = Path(__file__).with_suffix('.log')\n"
        "with log.open('a', encoding='utf-8') as handle:\n"
        "    handle.write(f'{value}\\n')\n",
    )
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
                "  (defworkflow child ((value Int)) -> Int",
                f'    (command-result tick :argv ("python" "{probe}" value) :returns Int))',
                "  (defworkflow run ((values List[Int])) -> List[Int]",
                "    (list/map-effect ((item values)) :max 3 (call child :value item)))",
                ")",
            )
        ),
        encoding="utf-8",
    )
    input_file = tmp_path / "inputs.json"
    input_file.write_text(json.dumps({"values": [5, 6, 7]}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    validated_payloads: list[Mapping[str, object]] = []
    validate = pure_projection_lowering.validate_pure_expr_payload

    def capture_payload(payload, **kwargs):
        validated_payloads.append(payload)
        return validate(payload, **kwargs)

    monkeypatch.setattr(
        pure_projection_lowering, "validate_pure_expr_payload", capture_payload
    )
    result = _public_run(
        _public_run_files(tmp_path, {"tick": probe}), input_file=input_file
    )

    assert (result.exit_code, dict(result.workflow_outputs)) == (
        0,
        {"__result__": (5, 6, 7)},
    )
    assert _log(probe) == ["5", "6", "7"]
    assert any(
        "__list_map_effect_state"
        in [binding["name"] for binding in payload["expr"].get("bindings", [])]
        and payload["pure_expr_schema_version"] == 3
        for payload in validated_payloads
        if isinstance(payload.get("expr"), Mapping)
    )


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
        node_counts.append(_node_count(payload))
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
    # The locations are read from the controller's source, so that an edit of it does not move them.
    lines = source.read_text(encoding="utf-8").splitlines()
    refused = next(
        (number, line.index("(result state") + 1)
        for number, line in enumerate(lines, 1)
        if ":on-exhausted (result state" in line
    )
    helper = next(
        (number, line.index("(defun result") + 1)
        for number, line in enumerate(lines, 1)
        if "(defun result" in line
    )
    assert f"mlevolve_pair/search.orc:{refused[0]}:{refused[1]}:" in caplog.text
    assert f"mlevolve_pair/search.orc:{helper[0]}:{helper[1]}" in caplog.text
    assert "pure_expr_payload_too_large" not in caplog.text
    assert node_counts and max(node_counts) <= 256
