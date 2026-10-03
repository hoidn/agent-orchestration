from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_workflow_evaluated_cli import _run_cli
from orchestrator.workflow.run_ref.contracts import canonical_sha256


def _write_entry(root: Path, source: str) -> Path:
    path = root / "src" / "r12" / "entry.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _write_probe(root: Path) -> None:
    (root / "probe.py").write_text(
        "import json, os, sys\nfrom pathlib import Path\n"
        'with Path("argv.jsonl").open("a", encoding="utf-8") as marker:\n'
        '    marker.write(json.dumps(sys.argv[1:]) + "\\n")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("0", encoding="utf-8")\n',
        encoding="utf-8",
    )


def _write_boundaries(root: Path) -> Path:
    path = root / "commands.json"
    path.write_text(json.dumps({
        "emit": {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]}
    }), encoding="utf-8")
    return path


def _write_inputs(root: Path, values: dict) -> Path:
    path = root / "inputs.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def _run_entry(root: Path, source: Path, boundaries: Path, *extra: str):
    return _run_cli(
        root,
        str(source),
        "--source-root", str(root / "src"),
        "--entry-workflow", "r12/entry::run",
        "--command-boundaries-file", str(boundaries),
        *extra,
    )


def _assert_undefined_before_dispatch(root: Path, result) -> None:
    assert result.returncode == 1
    assert "[undefined_variables]" in result.stderr
    assert not (root / "argv.jsonl").exists()
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    rows = [json.loads(line) for line in (run_root / "memo.jsonl").read_text().splitlines()]
    assert [row["record"] for row in rows] == ["terminal"]


def test_imported_inline_helper_keeps_native_input_root_outside_loops(tmp_path: Path) -> None:
    helper = tmp_path / "src" / "r12" / "helper.orc"
    helper.parent.mkdir(parents=True)
    helper.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule r12/helper) (export echo-label)
          (defproc echo-label ((label String)) -> Int
            :effects ((uses-command emit)) :lowering inline
            (command-result emit :argv
              ("python" "probe.py" "imported-proc" label "${inputs.state_root}") :returns Int)))
''',
        encoding="utf-8",
    )
    source = _write_entry(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule r12/entry) (import r12/helper :as helper :only (echo-label))
      (export run)
      (defworkflow run ((state_root String :default "PARENT")) -> Int
        (helper.echo-label "IMPORTED")))
''')
    _write_probe(tmp_path)

    result = _run_entry(tmp_path, source, _write_boundaries(tmp_path))

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "argv.jsonl").read_bytes() == b'["imported-proc", "IMPORTED", "PARENT"]\n'


def test_nested_direct_loops_use_the_innermost_zero_based_command_index(tmp_path: Path) -> None:
    source = _write_entry(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule r12/entry) (export run)
      (defworkflow run () -> Int
        (loop/recur :max 2 :state (loop-state (outer Int 0)) :on-exhausted 99
          (fn (outer_state)
            (let* ((inside (loop/recur :max 2 :state (loop-state (inner Int 0)) :on-exhausted 99
                             (fn (inner_state)
                               (let* ((value (command-result emit
                                               :argv ("python" "probe.py"
                                                 outer_state.outer inner_state.inner "${loop.index}")
                                               :returns Int)))
                                 (if (< inner_state.inner 1)
                                   (continue (loop-state :like inner_state
                                     :inner (+ inner_state.inner 1)))
                                   (done value)))))))
              (if (< outer_state.outer 1)
                (continue (loop-state :like outer_state :outer (+ outer_state.outer 1)))
                (done inside)))))))
''')
    _write_probe(tmp_path)

    result = _run_entry(tmp_path, source, _write_boundaries(tmp_path))

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "argv.jsonl").read_bytes() == (
        b'["0", "0", "0"]\n["0", "1", "1"]\n'
        b'["1", "0", "0"]\n["1", "1", "1"]\n'
    )


def test_imported_helper_without_own_loop_resets_loop_index_before_dispatch(tmp_path: Path) -> None:
    helper = tmp_path / "src" / "r12" / "helper.orc"
    helper.parent.mkdir(parents=True)
    helper.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule r12/helper) (export log-index)
          (defproc log-index ((label String)) -> Int
            :effects ((uses-command emit)) :lowering inline
            (command-result emit :argv ("python" "probe.py" label "${loop.index}") :returns Int)))
''',
        encoding="utf-8",
    )
    source = _write_entry(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule r12/entry) (import r12/helper :as helper :only (log-index))
      (export run)
      (defworkflow run () -> Int
        (loop/recur :max 1 :state (loop-state (outer Int 0)) :on-exhausted 99
          (fn (outer_state)
            (let* ((inside (loop/recur :max 1 :state (loop-state (inner Int 0)) :on-exhausted 99
                             (fn (inner_state)
                               (let* ((value (helper.log-index "imported"))) (done value))))))
              (done inside))))))
''')
    _write_probe(tmp_path)

    result = _run_entry(tmp_path, source, _write_boundaries(tmp_path))

    _assert_undefined_before_dispatch(tmp_path, result)


_EDGE_DEFINITIONS = {
    "private": '''(defproc isolated () -> Int
      :effects ((uses-command emit)) :lowering private-workflow
      (command-result emit :argv ("python" "probe.py" "${loop.index}") :returns Int))''',
    "native": '''(defworkflow isolated () -> Int
      (command-result emit :argv ("python" "probe.py" "${loop.index}") :returns Int))''',
}
_EDGE_CALLS = {"private": "(isolated)", "native": "(call isolated)"}
_EDGE_ARGV_DEFINITIONS = {
    "private": '''(defproc isolated ((label String)) -> Int
      :effects ((uses-command emit)) :lowering private-workflow
      (command-result emit :argv ("python" "probe.py" "private" "${inputs.label}") :returns Int))''',
    "native": '''(defworkflow isolated ((label String)) -> Int
      (command-result emit :argv ("python" "probe.py" "native" "${inputs.label}") :returns Int))''',
}


@pytest.mark.parametrize("edge", ("private", "native"), ids=("private-procedure", "native-workflow"))
def test_private_and_native_helpers_receive_their_exact_input_argv(
    tmp_path: Path, edge: str
) -> None:
    invoke = "(isolated label)" if edge == "private" else "(call isolated :label label)"
    source = _write_entry(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule r12/entry) (export run)
      {_EDGE_ARGV_DEFINITIONS[edge]}
      (defworkflow run ((label String)) -> Int
        (loop/recur :max 1 :state (loop-state (i Int 0)) :on-exhausted 99
          (fn (state) (let* ((result {invoke})) (done result))))))
''')
    _write_probe(tmp_path)
    inputs = _write_inputs(tmp_path, {"label": "payload"})

    result = _run_entry(
        tmp_path, source, _write_boundaries(tmp_path), "--input-file", str(inputs)
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "argv.jsonl").read_bytes() == f'["{edge}", "payload"]\n'.encode()


@pytest.mark.parametrize("edge", ("private", "native"), ids=("private-procedure", "native-workflow"))
def test_private_and_native_edges_reset_loop_index_before_dispatch(
    tmp_path: Path, edge: str
) -> None:
    source = _write_entry(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule r12/entry) (export run)
      {_EDGE_DEFINITIONS[edge]}
      (defworkflow run () -> Int
        (loop/recur :max 1 :state (loop-state (i Int 0)) :on-exhausted 99
          (fn (state)
            (let* ((result {_EDGE_CALLS[edge]})) (done result))))))
''')
    _write_probe(tmp_path)

    result = _run_entry(tmp_path, source, _write_boundaries(tmp_path))

    _assert_undefined_before_dispatch(tmp_path, result)


@pytest.mark.parametrize(
    "slot,expected_exit,expected_argv",
    [
        ("${inputs.pair__x}", 0, b'["7", "\\"ready\\""]\n'),
        ("${inputs.pair.x}", 1, None),
    ],
    ids=("native-projection-and-value-suffix", "missing-dot-field-path"),
)
def test_input_slots_select_native_rows_and_keep_value_suffixes_as_paths(
    tmp_path: Path, slot: str, expected_exit: int, expected_argv: bytes | None
) -> None:
    source = _write_entry(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule r12/entry) (export run)
      (defrecord Pair (x Int))
      (defworkflow run ((pair Pair) (payload Value)) -> Int
        (command-result emit :argv ("python" "probe.py" "{slot}" "${{inputs.payload.z|json}}") :returns Int)))
''')
    _write_probe(tmp_path)
    inputs = _write_inputs(tmp_path, {"pair": {"x": 7}, "payload": {"z": "ready"}})

    result = _run_entry(
        tmp_path, source, _write_boundaries(tmp_path), "--input-file", str(inputs)
    )

    assert result.returncode == expected_exit, result.stderr
    if expected_argv is None:
        _assert_undefined_before_dispatch(tmp_path, result)
    else:
        assert (tmp_path / "argv.jsonl").read_bytes() == expected_argv


_FILTER_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule r12/entry) (export run)
  (defworkflow run ((selected Bool) (payload Value)) -> Int
    (if selected
      (command-result emit :argv ("python" "probe.py" "${inputs.payload.z|unknown-filter}") :returns Int)
      (command-result emit :argv ("python" "probe.py" "fallback") :returns Int))))
'''


@pytest.mark.parametrize(
    "selected,expected_exit,expected_argv",
    [(True, 1, None), (False, 0, b'["fallback"]\n')],
    ids=("selected-filter-refusal", "unselected-filter-not-evaluated"),
)
def test_unknown_filter_is_checked_only_in_the_selected_command(
    tmp_path: Path, selected: bool, expected_exit: int, expected_argv: bytes | None
) -> None:
    source = _write_entry(tmp_path, _FILTER_SOURCE)
    _write_probe(tmp_path)
    inputs = _write_inputs(
        tmp_path, {"selected": selected, "payload": {"z": "ready"}}
    )

    result = _run_entry(
        tmp_path, source, _write_boundaries(tmp_path), "--input-file", str(inputs)
    )

    assert result.returncode == expected_exit, result.stderr
    if expected_argv is None:
        _assert_undefined_before_dispatch(tmp_path, result)
    else:
        assert (tmp_path / "argv.jsonl").read_bytes() == expected_argv


def test_persisted_dependencies_follow_values_not_selected_branch_control(
    tmp_path: Path,
) -> None:
    source = _write_entry(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule r12/entry) (export run)
      (defworkflow run () -> Int
        (let* ((decision (command-result choose
                        :argv ("python" "probe.py" "choose") :returns Bool))
               (inside (if decision
                         (command-result emit
                           :argv ("python" "probe.py" "branch") :returns Int)
                         99))
               (dependent (command-result emit
                            :argv ("python" "probe.py" "dependent"
                                   (if decision 7 9)) :returns Int)))
          dependent)))
''')
    (tmp_path / "probe.py").write_text(
        "import json, os, sys\nfrom pathlib import Path\n"
        'with Path("argv.jsonl").open("a", encoding="utf-8") as marker:\n'
        '    marker.write(json.dumps(sys.argv[1:]) + "\\n")\n'
        'outputs = {"choose": "true", "branch": "11", "dependent": "17"}\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(\n'
        '    outputs[sys.argv[1]], encoding="utf-8")\n',
        encoding="utf-8",
    )
    boundaries = tmp_path / "commands.json"
    binding = {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]}
    boundaries.write_text(
        json.dumps({"choose": binding, "emit": binding}), encoding="utf-8"
    )

    result = _run_entry(tmp_path, source, boundaries)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "argv.jsonl").read_bytes() == (
        b'["choose"]\n["branch"]\n["dependent", "7"]\n'
    )
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    rows = [
        json.loads(line)
        for line in (run_root / "memo.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    commits = [row for row in rows if row["record"] == "committed"]
    assert [row["record"] for row in rows] == [
        "started", "committed", "started", "committed", "started", "committed", "terminal"
    ]
    assert len(commits) == 3
    choose, branch, dependent = commits
    assert choose["value"] is True
    expected_argv = [
        ["python", "probe.py", "choose"],
        ["python", "probe.py", "branch"],
        ["python", "probe.py", "dependent", "7"],
    ]
    assert [row["input_parts"]["argv"] for row in commits] == [
        canonical_sha256(argv) for argv in expected_argv
    ]
    assert [row["input_digest"] for row in commits] == [
        canonical_sha256(row["input_parts"]) for row in commits
    ]
    assert branch["depends_on"] == []
    assert dependent["depends_on"] == [choose["identity"]]
