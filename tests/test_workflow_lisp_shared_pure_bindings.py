from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from tests.workflow_evaluated_totality_helpers import _log, _public_run_files, _write_probe
from tests.workflow_evaluated_totality_helpers import checked_run, _public_run

def _source(uses: int) -> str:
    references = " ".join("forwarded" for _ in range(uses))
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.35")',
            "  (defmodule grt/entry)",
            "  (export run)",
            "  (defworkflow run ((n Int)) -> Int",
            f"    (let* ((increment (+ n 1)) (forwarded (+ increment 1)))",
            f"      (+ {references}))))",
        )
    )








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
                '  (:target-dsl "2.35")',
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


def test_outer_pure_binding_is_sequenced_before_unselected_if_arm(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "grt" / "entry.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
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

    assert result.exit_code == 1
    _, snapshot = checked_run(tmp_path)
    assert snapshot.terminal.data["outcome"] == "failed"
    assert snapshot.terminal.data["code"] == "pure_expr_overflow"
    assert not snapshot.active_commits


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
                    '  (:target-dsl "2.35")',
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
        assert result.exit_code == 1
        _, snapshot = checked_run(root)
        observed.append(snapshot.terminal.data["code"])

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
                '  (:target-dsl "2.35")',
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


    result = _public_run(
        _public_run_files(tmp_path, {"tick": probe}), input_file=input_file
    )

    assert (result.exit_code, dict(result.workflow_outputs)) == (
        0,
        {"__result__": (5, 6, 7)},
    )
    assert _log(probe) == ["5", "6", "7"]


def test_outer_record_field_is_sequenced_before_unselected_if_arm(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "grt" / "entry.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
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

    assert result.exit_code == 1
    _, snapshot = checked_run(tmp_path)
    assert snapshot.terminal.data["outcome"] == "failed"
    assert snapshot.terminal.data["code"] == "pure_expr_overflow"
    assert not snapshot.active_commits


def _write_input(root: Path, value: int) -> Path:
    path = root / "inputs.json"
    path.write_text(json.dumps({"n": value}), encoding="utf-8")
    return path




def test_fallible_binding_inside_unselected_arm_is_not_evaluated(tmp_path, monkeypatch):
    source = tmp_path / "grt" / "entry.orc"
    source.parent.mkdir(parents=True)
    source.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule grt/entry) (export run)
      (defworkflow run ((n Int)) -> Int
        (if false (let* ((overflow (+ n 1))) (+ overflow overflow)) 0)))''')
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"n": 2**63 - 1}))
    monkeypatch.chdir(tmp_path)
    result = _public_run(_public_run_files(tmp_path, {}), input_file=inputs)
    assert (result.exit_code, dict(result.workflow_outputs)) == (0, {"__result__": 0})
    _, snapshot = checked_run(tmp_path)
    assert snapshot.terminal.data["value"] == 0
    assert not snapshot.active_commits
