"""Public behavioral acceptance for the native Workflow Lisp REPL."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys

import pytest

from tests.test_workflow_dynamic_interruptions import (
    _events, _kill_known_processes, _live_cli, _run_cli, _run_root as _case_run_root,
    _state, _wait_file, _write_case,
)
from tests.test_workflow_dynamic_source import write_source


def _env(root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _run(root: Path, source: Path, *options: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", "run", str(source),
         "--source-root", str(root), *options],
        cwd=root, env=_env(root), capture_output=True, text=True, check=False,
    )


def _repl(root: Path, lines: list[str], *, state_dir: Path | None = None,
          env: dict[str, str] | None = None):
    command = [sys.executable, "-B", "-m", "orchestrator", "repl"]
    if state_dir is not None:
        command.extend(("--state-dir", str(state_dir)))
    return subprocess.run(
        command, input="\n".join(lines) + "\n", cwd=root,
        env={**_env(root), **(env or {})},
        capture_output=True, text=True, check=False,
    )


def _load(source: Path, root: Path, *options: str) -> str:
    return " ".join([":load", shlex.quote(str(source)), "--source-root",
                     shlex.quote(str(root)), *options])


def _load_case(case: dict[str, object]) -> str:
    root = case["root"]
    source = case["source"]
    if case["kind"] == "command":
        return _load(source, root, "--command-boundaries-file",
                     shlex.quote(str(root / "commands.json")))
    return _load(source, root, "--provider-externs-file",
                 shlex.quote(str(root / "providers.json")))


def _run_root(root: Path, state_dir: Path | None = None) -> Path:
    runs = state_dir or root / ".orchestrate" / "runs"
    (run_root,) = runs.iterdir()
    return run_root


def _typed_values(stdout: str) -> list[tuple[object, str]]:
    lines = stdout.splitlines()
    values = []
    for index, line in enumerate(lines[:-1]):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if lines[index + 1].startswith(": "):
            values.append((value, lines[index + 1][2:]))
    return values


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def _state_file(run_root: Path) -> dict[str, object]:
    return json.loads((run_root / "state.json").read_text(encoding="utf-8"))


def _write_state(run_root: Path, state: dict[str, object]) -> None:
    (run_root / "state.json").write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8",
    )


def _command_case(tmp_path: Path, body: str, *, two_effects: bool = False):
    case = _write_case(tmp_path, "command", two_effects=two_effects)
    case["source"] = write_source(tmp_path, "demo/main", body)
    control = tmp_path / ".command-control"
    control.mkdir()
    run = _run_cli(case, control)
    return case, control, run, _case_run_root(case)


def _two_command_let_body() -> str:
    return '''
      (export main)
      (define (bump x) (+ x 1))
      (defworkflow main () -> Int
        (let* ((seed 8)
               (first (command-result probe
                        :argv ("python" "interrupt_probe.py"
                          (bump (+ 4 (let* ((operand_local 2)) operand_local))) "TOKEN_ONE")
                        :returns Int))
               (second (command-result probe
                         :argv ("python" "interrupt_probe.py"
                           (bump (+ 4 (let* ((operand_local 3)) operand_local))) "TOKEN_TWO")
                         :returns Int)))
          second))
    '''


def _attach_case(case: dict[str, object], run_root: Path, *lines: str,
                 env: dict[str, str] | None = None):
    return _repl(case["root"], [
        _load_case(case), f":attach {run_root.name}", *lines, ":quit",
    ], env=env)


def _inspection_env(control: Path, kind: str = "command") -> dict[str, str]:
    return {"DYNAMIC_TEST_CONTROL": str(control), "DYNAMIC_TEST_KIND": kind,
            "DYNAMIC_TEST_MODE": kind}


def _interrupt(case: dict[str, object], control: Path, barrier: str):
    with _live_cli(case, control, barrier=barrier) as process:
        marker = _wait_file(process, control / "gate.json")
        assert marker["barrier"] == barrier
        run_root = _case_run_root(case)
        _kill_known_processes(process, control)
        assert process.returncode == -signal.SIGKILL
    return run_root, _hashes(run_root)


def _assert_attached_snapshot_unchanged(source: Path, repl, run_root: Path,
                                         before: dict[str, str], source_hash: str) -> None:
    assert repl.returncode == 0, repl.stderr
    assert _hashes(run_root) == before
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash


def test_public_native_repl_attaches_captured_closure_and_returns_saved_result(tmp_path):
    source = write_source(tmp_path, "demo/main", '''
      (export run)
      (defworkflow run ((n Int :default 7)) -> Int
        (let* ((add (fn (x) (+ n x)))) (add 0)))
    ''')
    run = _run(tmp_path, source)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    before = _hashes(run_root)

    repl = _repl(tmp_path, [
        _load(source, tmp_path), f":attach {run_root.name}", ":bindings", "add", "(add 5)",
        ":result", ":quit",
    ])

    assert repl.returncode == 0, repl.stderr
    assert "add : Function" in repl.stdout and "n : Int" in repl.stdout
    assert "<function>" in repl.stdout
    assert _typed_values(repl.stdout) == [(12, "Int"), (7, "Int")]
    assert _hashes(run_root) == before


def test_public_native_repl_exposes_authored_dollar_bindings_in_completed_root(tmp_path):
    source = write_source(tmp_path, "demo/main", '''
      (export run)
      (defworkflow run () -> Int
        (let* (($effect0 17) ($effect_user 23)) (+ $effect0 $effect_user)))
    ''')
    run = _run(tmp_path, source)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    before = _hashes(run_root)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    repl = _repl(tmp_path, [
        _load(source, tmp_path), f":attach {run_root.name}", ":bindings",
        "$effect0", "$effect_user", ":result", ":quit",
    ])

    _assert_attached_snapshot_unchanged(source, repl, run_root, before, source_hash)
    names = {line.split(" : ", 1)[0] for line in repl.stdout.splitlines() if " : " in line}
    assert {"$effect0", "$effect_user"} <= names
    assert _typed_values(repl.stdout) == [(17, "Int"), (23, "Int"), (40, "Int")]


def test_public_native_repl_exposes_authored_dollar_bindings_at_first_effect_prefix(tmp_path):
    case = _write_case(tmp_path, "command")
    case["source"] = write_source(tmp_path, "demo/main", '''
      (export main)
      (defworkflow main () -> Int
        (let* (($effect0 7)
               ($effect_user 11)
               (answer (command-result probe
                         :argv ("python" "interrupt_probe.py" "TOKEN_ONLY") :returns Int))
               (total (+ $effect0 $effect_user)))
          total))
    ''')
    control = tmp_path / ".dollar-effect-control"
    with _live_cli(case, control, barrier="pre_dispatch") as process:
        marker = _wait_file(process, control / "gate.json")
        assert marker["barrier"] == "pre_dispatch"
        run_root = _case_run_root(case)
        before = _hashes(run_root)
        source_hash = hashlib.sha256(case["source"].read_bytes()).hexdigest()
        assert _state(run_root)["status"] == "running"
        _kill_known_processes(process, control)
        assert process.returncode == -signal.SIGKILL

    repl = _attach_case(case, run_root, ":bindings", "$effect0", "$effect_user",
                        env=_inspection_env(control))

    _assert_attached_snapshot_unchanged(case["source"], repl, run_root, before, source_hash)
    names = {line.split(" : ", 1)[0] for line in repl.stdout.splitlines() if " : " in line}
    assert {"$effect0", "$effect_user"} <= names
    assert "$effect0$" not in names
    assert _typed_values(repl.stdout) == [(7, "Int"), (11, "Int")]
    assert _events(control) == []


def test_public_native_repl_reconstructs_completed_command_result_read_only(tmp_path):
    case = _write_case(tmp_path, "command")
    control = tmp_path / ".command-control"
    control.mkdir()
    run = _run_cli(case, control)
    assert run.returncode == 0, run.stderr
    run_root = _case_run_root(case)
    before = _hashes(run_root)
    source_hash = hashlib.sha256(case["source"].read_bytes()).hexdigest()
    calls = _events(control)

    repl = _repl(tmp_path, [
        _load_case(case), f":attach {run_root.name}", ":bindings", ":result", ":quit",
    ], env={"DYNAMIC_TEST_CONTROL": str(control), "DYNAMIC_TEST_KIND": "command",
            "DYNAMIC_TEST_MODE": "command"})

    _assert_attached_snapshot_unchanged(case["source"], repl, run_root,
                                        before, source_hash)
    assert _typed_values(repl.stdout) == [(17, "Int")]
    assert _events(control) == calls


def test_public_native_repl_reconstructs_completed_local_provider_result_read_only(tmp_path):
    case = _write_case(tmp_path, "provider")
    control = tmp_path / ".provider-control"
    control.mkdir()
    run = _run_cli(case, control)
    assert run.returncode == 0, run.stderr
    run_root = _case_run_root(case)
    before = _hashes(run_root)
    source_hash = hashlib.sha256(case["source"].read_bytes()).hexdigest()
    calls = _events(control)
    assert [event["label"] for event in calls] == ["only"]

    repl = _repl(tmp_path, [
        _load_case(case), f":attach {run_root.name}", ":result", ":quit",
    ], env=_inspection_env(control, "provider"))

    _assert_attached_snapshot_unchanged(case["source"], repl, run_root, before, source_hash)
    assert _typed_values(repl.stdout) == [("reply-only", "String")]
    assert _events(control) == calls


def test_public_native_repl_refuses_effects_without_dispatch_or_mutation(tmp_path):
    case = _write_case(tmp_path, "command")
    source = write_source(tmp_path, "demo/main", '''
      (export main)
      (define (inc n) (+ n 1))
      (define (danger n)
        (command-result probe :argv ("python" "interrupt_probe.py" "TOKEN_ONLY" n)
          :returns Int))
      (define (explode) (/ 1 0))
      (define (danger-bad-operand)
        (command-result probe
          :argv ("python" "interrupt_probe.py" (explode) "TOKEN_ONLY") :returns Int))
      (defworkflow main () -> Int (inc 4))
    ''')
    case["source"] = source
    control = tmp_path / ".effect-control"
    control.mkdir()
    run = _run_cli(case, control)
    assert run.returncode == 0, run.stderr
    run_root = _case_run_root(case)
    before = _hashes(run_root)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    calls = _events(control)
    direct = '(command-result probe :argv ("python" "interrupt_probe.py" "TOKEN_ONLY") :returns Int)'

    repl = _repl(tmp_path, [
        _load(source, tmp_path, "--command-boundaries-file", shlex.quote(str(tmp_path / "commands.json"))),
        f":attach {run_root.name}", direct,
        "(danger (inc (+ 4 (let* ((operand_local 2)) operand_local))))",
        "(danger-bad-operand)",
        "(inc 4)", ":quit",
    ], env={"DYNAMIC_TEST_CONTROL": str(control), "DYNAMIC_TEST_KIND": "command",
            "DYNAMIC_TEST_MODE": "command"})

    _assert_attached_snapshot_unchanged(source, repl, run_root, before, source_hash)
    assert repl.stderr.count("[repl_effect_refused]") == 3
    assert "division_by_zero" not in repl.stderr
    assert "dynamic_operand_type" not in repl.stderr
    assert _typed_values(repl.stdout) == [(5, "Int")]
    assert _events(control) == calls == []


def test_public_native_repl_refuses_captured_and_imported_effect_helpers_before_bad_operand(tmp_path):
    case = _write_case(tmp_path, "command")
    write_source(tmp_path, "lib/effects", '''
      (export imported-danger)
      (define (explode) (/ 1 0))
      (define (imported-danger)
        (command-result probe :argv ("python" "interrupt_probe.py" (explode) "TOKEN_ONLY")
          :returns Int))
    ''', budget=None)
    source = write_source(tmp_path, "demo/main", '''
      (import lib/effects :only (imported-danger))
      (export run)
      (define (explode) (/ 1 0))
      (defworkflow run () -> Int
        (let* ((captured-danger
                 (fn () (command-result probe
                       :argv ("python" "interrupt_probe.py" (explode) "TOKEN_ONLY")
                       :returns Int)))
               (safe (if false (imported-danger) 7)))
          safe))
    ''')
    case["source"] = source
    control = tmp_path / ".effect-refusal-control"
    control.mkdir()
    run = _run_cli(case, control)
    assert run.returncode == 0, run.stderr
    assert _events(control) == []
    run_root = _case_run_root(case)
    before = _hashes(run_root)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    repl = _repl(tmp_path, [
        _load(source, tmp_path, "--command-boundaries-file", shlex.quote(str(tmp_path / "commands.json"))),
        f":attach {run_root.name}",
        "(if false (imported-danger) 9)",
        "(captured-danger)", "(imported-danger)", ":result", ":quit",
    ], env={"DYNAMIC_TEST_CONTROL": str(control), "DYNAMIC_TEST_KIND": "command",
            "DYNAMIC_TEST_MODE": "command"})

    _assert_attached_snapshot_unchanged(source, repl, run_root, before, source_hash)
    assert repl.stderr.count("[repl_effect_refused]") == 2
    assert "division_by_zero" not in repl.stderr
    assert _typed_values(repl.stdout) == [(9, "Int"), (7, "Int")]
    assert _events(control) == []


def test_public_native_repl_prints_record_list_and_null_results(tmp_path):
    source = write_source(tmp_path, "demo/main", '''
      (export run)
      (defrecord Summary (title String) (items List[Int]))
      (defworkflow run () -> Summary
        (record (title "ready") (items (list 2 3))))
    ''')
    run = _run(tmp_path, source)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    repl = _repl(tmp_path, [_load(source, tmp_path), f":attach {run_root.name}", ":result", ":quit"])
    assert repl.returncode == 0, repl.stderr
    assert _typed_values(repl.stdout) == [({"title": "ready", "items": [2, 3]}, "Summary")]

    null_source = write_source(tmp_path, "null/main", '''
      (export run)
      (defworkflow run ((value Value)) -> Value value)
    ''')
    null_input = tmp_path / "null-input.json"
    null_input.write_text('{"value":null}\n', encoding="utf-8")
    null_run = _run(tmp_path, null_source, "--input-file", str(null_input))
    assert null_run.returncode == 0, null_run.stderr
    null_root, = [path for path in (tmp_path / ".orchestrate/runs").iterdir()
                  if path != run_root]
    null_repl = _repl(tmp_path, [
        _load(null_source, tmp_path), f":attach {null_root.name}", ":result", ":quit",
    ])
    assert null_repl.returncode == 0, null_repl.stderr
    assert _typed_values(null_repl.stdout) == [(None, "Value")]
    assert "[repl_no_result]" not in null_repl.stderr

    existing_roots = set((tmp_path / ".orchestrate/runs").iterdir())
    list_source = write_source(tmp_path, "list/main", '''
      (export run)
      (defworkflow run () -> List[Int] (list 2 3))
    ''')
    list_run = _run(tmp_path, list_source)
    assert list_run.returncode == 0, list_run.stderr
    list_root, = set((tmp_path / ".orchestrate/runs").iterdir()) - existing_roots
    list_repl = _repl(tmp_path, [
        _load(list_source, tmp_path), f":attach {list_root.name}", ":result", ":quit",
    ])
    assert list_repl.returncode == 0, list_repl.stderr
    (value, descriptor), = _typed_values(list_repl.stdout)
    assert value == [2, 3]
    assert json.loads(descriptor) == {"kind": "list", "item": {"kind": "primitive", "name": "Int"}}


def test_public_native_repl_restores_root_scope_after_shadowing_operands_and_helpers(tmp_path):
    source = write_source(tmp_path, "demo/main", '''
      (export run)
      (define (return-value f) f)
      (define (apply-value f x) (let* ((helper_local 90)) (f x)))
      (defworkflow run ((n Int :default 7)) -> Int
        (let* ((n 10)
               (add (fn (n) (+ n 1)))
               (captured (fn (x) (+ n x)))
               (returned (return-value captured))
               (answer (apply-value returned 2))
               (total (+ (let* ((operand_local 50)) 1) answer)))
          total))
    ''')
    run = _run(tmp_path, source)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    repl = _repl(tmp_path, [
        _load(source, tmp_path), f":attach {run_root.name}", ":bindings", "(add 5)",
        "(returned 5)", ":result", ":quit",
    ])
    assert repl.returncode == 0, repl.stderr
    names = {line.split(" : ", 1)[0] for line in repl.stdout.splitlines() if " : " in line}
    assert {"n", "add", "captured", "returned", "answer", "total"} <= names
    assert not {"helper_local", "operand_local", "f", "x"} & names
    assert _typed_values(repl.stdout) == [(6, "Int"), (15, "Int"), (13, "Int")]


def test_public_native_repl_calls_imported_closure_inside_container_and_helper(tmp_path):
    write_source(tmp_path, "lib/math", '''
      (export make-adder)
      (define (make-adder n) (fn (x) (+ n x)))
    ''', budget=None)
    source = write_source(tmp_path, "demo/main", '''
      (import lib/math :only (make-adder))
      (export run)
      (define (invoke f x) (f x))
      (defworkflow run () -> Int
        (let* ((adder (make-adder 40))
               (box (record (callbacks (list adder))))
               (answer (invoke (at (field box "callbacks") 0) 2)))
          answer))
    ''')
    run = _run(tmp_path, source)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    before = _hashes(run_root)
    repl = _repl(tmp_path, [
        _load(source, tmp_path), f":attach {run_root.name}", "box",
        '(invoke (at (field box "callbacks") 0) 3)', ":result", ":quit",
    ])
    assert repl.returncode == 0, repl.stderr
    assert "[repl_value_not_printable]" in repl.stderr
    assert _typed_values(repl.stdout) == [(43, "Int"), (42, "Int")]
    assert _hashes(run_root) == before


def test_public_repl_run_uses_session_and_command_state_directories(tmp_path):
    source = write_source(tmp_path, "demo/main", '''
      (export run)
      (defworkflow run ((n Int :default 7)) -> Int n)
    ''')
    session_root = tmp_path / "session-runs"
    override_root = tmp_path / "override-runs"
    repl = _repl(tmp_path, [
        _load(source, tmp_path), ":run", ":result",
        f":run --state-dir {shlex.quote(str(override_root))}", ":result", ":quit",
    ], state_dir=session_root)
    assert repl.returncode == 0, repl.stderr
    run_ids = re.findall(r"^run_id: (\S+)$", repl.stdout, re.MULTILINE)
    assert len(run_ids) == 2
    assert (session_root / run_ids[0] / "run.json").is_file()
    assert (override_root / run_ids[1] / "run.json").is_file()
    assert _typed_values(repl.stdout) == [(7, "Int"), (7, "Int")]


def test_public_native_repl_requires_loaded_module_for_native_attachment(tmp_path):
    source = write_source(tmp_path, "demo/main", "(export run) (defworkflow run () -> Int 7)")
    run = _run(tmp_path, source)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)

    repl = _repl(tmp_path, [f":attach {run_root.name}", ":quit"])

    assert repl.returncode == 0, repl.stderr
    assert "[repl_module_required]" in repl.stderr


def test_public_native_repl_clears_capture_when_loaded_program_digest_changes(tmp_path):
    original = write_source(tmp_path, "demo/main", '''
      (export run)
      (defworkflow run ((n Int :default 7)) -> Int n)
    ''')
    run = _run(tmp_path, original)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    changed_root = tmp_path / "changed"
    changed_root.mkdir()
    changed = write_source(changed_root, "demo/main", '''
      (export run)
      (defworkflow run ((n Int :default 7)) -> Int (+ n 1))
    ''')

    repl = _repl(tmp_path, [
        _load(changed, changed_root), f":attach {run_root.name}", "n", ":quit",
    ])

    assert repl.returncode == 0, repl.stderr
    assert "[resume_program_changed]" in repl.stderr
    assert "[repl_not_attached]" in repl.stderr


def test_public_native_repl_fails_closed_on_unknown_saved_profile(tmp_path):
    source = write_source(tmp_path, "demo/main", "(export run) (defworkflow run () -> Int 7)")
    run = _run(tmp_path, source)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header["result_persistence_profile"] = "unknown.v1"
    header_path.write_text(json.dumps(header, sort_keys=True, separators=(",", ":")) + "\n",
                           encoding="utf-8")
    before = _hashes(run_root)

    repl = _repl(tmp_path, [
        _load(source, tmp_path), f":attach {run_root.name}", ":bindings", ":quit",
    ])

    assert repl.returncode == 0, repl.stderr
    assert "[repl_profile_unsupported]" in repl.stderr
    assert _hashes(run_root) == before


@pytest.mark.parametrize("after_first", [False, True])
def test_public_native_repl_captures_scope_at_real_interruption_boundary(tmp_path, after_first):
    case = _write_case(tmp_path, "command", two_effects=True)
    case["source"] = write_source(tmp_path, "demo/main", _two_command_let_body())
    control = tmp_path / ".interrupt-control"
    barrier = "second_dispatch" if after_first else "pre_dispatch"

    with _live_cli(case, control, barrier=barrier) as process:
        marker = _wait_file(process, control / "gate.json")
        assert marker["barrier"] == barrier
        run_root = _case_run_root(case)
        snapshot = _hashes(run_root)
        state = _state(run_root)
        assert state["status"] == "running" and state["workflow_outputs"] is None
        if after_first:
            assert [row["status"] for row in state["effects"]] == ["completed", "running"]
            assert [row["label"] for row in _events(control)] == ["one"]
            assert state["steps_used"] > 0
        else:
            assert [row["status"] for row in state["effects"]] == ["running"]
            assert _events(control) == []
        _kill_known_processes(process, control)
        assert process.returncode == -signal.SIGKILL

    repl = _attach_case(case, run_root, ":bindings", ":result", env=_inspection_env(control))
    assert repl.returncode == 0, repl.stderr
    names = {line.split(" : ", 1)[0] for line in repl.stdout.splitlines() if " : " in line}
    assert "seed" in names
    assert ("first" in names) is after_first
    assert not {"operand_local", "x"} & names
    assert "[repl_no_result]" in repl.stderr
    assert _hashes(run_root) == snapshot
    assert ([event["label"] for event in _events(control)] == (["one"] if after_first else []))


def test_public_native_repl_rejects_running_progress_count_mismatch(tmp_path):
    case = _write_case(tmp_path, "command", two_effects=True)
    case["source"] = write_source(tmp_path, "demo/main", _two_command_let_body())
    control = tmp_path / ".interrupt-control"
    run_root, _ = _interrupt(case, control, "second_dispatch")
    state = _state_file(run_root)
    assert state["status"] == "running" and state["steps_used"] > 0
    state["steps_used"] = 0
    _write_state(run_root, state)
    before = _hashes(run_root)
    events = _events(control)

    repl = _attach_case(case, run_root, ":bindings", env=_inspection_env(control))

    assert repl.returncode == 0, repl.stderr
    assert "[dynamic_state_invalid]" in repl.stderr
    assert _hashes(run_root) == before and _events(control) == events


def test_public_native_repl_stops_at_unrecorded_effect_without_dispatch(tmp_path):
    body = '''
      (export main)
      (defworkflow main () -> Int
        (let* ((seed 4)
               (result (command-result probe :argv ("python" "interrupt_probe.py" "TOKEN_ONLY") :returns Int)))
          result))
    '''
    case, control, run, run_root = _command_case(tmp_path, body)
    assert run.returncode == 0, run.stderr
    state = _state_file(run_root)
    state.update(status="running", steps_used=0, current_effect=None,
                 workflow_outputs=None, error=None, effects=[])
    _write_state(run_root, state)
    before = _hashes(run_root)
    events = _events(control)

    repl = _attach_case(case, run_root, ":bindings", ":result",
                        env=_inspection_env(control))

    assert repl.returncode == 0, repl.stderr
    assert "seed : Int" in repl.stdout and "[repl_no_result]" in repl.stderr
    assert _hashes(run_root) == before and _events(control) == events


def test_public_native_repl_preserves_unpublished_pure_halt_without_result(tmp_path):
    source = write_source(tmp_path, "demo/main", '''
      (export run)
      (defworkflow run () -> Int (let* ((seed 7)) seed))
    ''')
    run = _run(tmp_path, source)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    state = _state_file(run_root)
    state.update(status="running", steps_used=0, current_effect=None,
                 workflow_outputs=None, error=None, effects=[])
    _write_state(run_root, state)
    before = _hashes(run_root)

    repl = _repl(tmp_path, [
        _load(source, tmp_path), f":attach {run_root.name}", ":bindings", ":result", ":quit",
    ])

    assert repl.returncode == 0, repl.stderr
    assert "seed : Int" in repl.stdout and "position: halt-unpublished" in repl.stdout
    assert "[repl_no_result]" in repl.stderr
    assert _hashes(run_root) == before


def test_public_native_repl_rejects_corrupt_physical_effect_result_read_only(tmp_path):
    case, control, run, run_root = _command_case(
        tmp_path,
        '(export main) (defworkflow main () -> Int '
        '(command-result probe :argv ("python" "interrupt_probe.py" "TOKEN_ONLY") :returns Int))',
    )
    assert run.returncode == 0, run.stderr
    state = _state_file(run_root)
    result = run_root / state["effects"][0]["result_path"]
    result.write_text("not-json", encoding="utf-8")
    before = _hashes(run_root)
    events = _events(control)

    repl = _attach_case(case, run_root, ":bindings", env=_inspection_env(control))

    assert repl.returncode == 0, repl.stderr
    assert "[dynamic_state_invalid]" in repl.stderr
    assert _hashes(run_root) == before and _events(control) == events


@pytest.mark.parametrize("field", ["workflow_outputs", "steps_used"])
def test_public_native_repl_rejects_terminal_result_or_step_mismatch(tmp_path, field):
    case, control, run, run_root = _command_case(
        tmp_path,
        '(export main) (defworkflow main () -> Int '
        '(command-result probe :argv ("python" "interrupt_probe.py" "TOKEN_ONLY") :returns Int))',
    )
    assert run.returncode == 0, run.stderr
    state = _state_file(run_root)
    if field == "workflow_outputs":
        state[field] = 999
    else:
        assert state[field] > 0
        state[field] = 0
    _write_state(run_root, state)
    before = _hashes(run_root)
    events = _events(control)

    repl = _attach_case(case, run_root, ":bindings", env=_inspection_env(control))

    assert repl.returncode == 0, repl.stderr
    assert "[dynamic_state_invalid]" in repl.stderr
    assert _hashes(run_root) == before and _events(control) == events


def test_public_native_repl_rejects_misordered_and_extra_effect_rows(tmp_path):
    for corruption in ("misordered", "extra"):
        workspace = tmp_path / corruption
        workspace.mkdir()
        case, control, run, run_root = _command_case(
            workspace, _two_command_let_body(), two_effects=True,
        )
        assert run.returncode == 0, run.stderr
        state = _state_file(run_root)
        rows = state["effects"]
        if corruption == "misordered":
            rows[0]["location"], rows[1]["location"] = rows[1]["location"], rows[0]["location"]
            rows[0]["definition"], rows[1]["definition"] = rows[1]["definition"], rows[0]["definition"]
        else:
            extra = dict(rows[0], ordinal=3, result_path="effects/3/attempt-1/result.json",
                         stdout_path="effects/3/attempt-1/stdout.txt",
                         stderr_path="effects/3/attempt-1/stderr.txt")
            attempt = run_root / "effects/3/attempt-1"
            attempt.mkdir(parents=True)
            (attempt / "result.json").write_bytes((run_root / rows[0]["result_path"]).read_bytes())
            (attempt / "stdout.txt").write_bytes((run_root / rows[0]["stdout_path"]).read_bytes())
            (attempt / "stderr.txt").write_bytes((run_root / rows[0]["stderr_path"]).read_bytes())
            rows.append(extra)
        _write_state(run_root, state)
        before = _hashes(run_root)
        events = _events(control)

        repl = _attach_case(case, run_root, ":bindings", env=_inspection_env(control))

        assert repl.returncode == 0, repl.stderr
        assert "[dynamic_state_invalid]" in repl.stderr, corruption
        assert _hashes(run_root) == before and _events(control) == events


def test_public_native_repl_rejects_failed_effect_error_step_mismatch(tmp_path):
    case = _write_case(tmp_path, "command")
    (tmp_path / "interrupt_probe.py").write_text("raise SystemExit(9)\n", encoding="utf-8")
    case["source"] = write_source(tmp_path, "demo/main", '''
      (export main)
      (defworkflow main () -> Int
        (command-result probe :argv ("python" "interrupt_probe.py" "TOKEN_ONLY") :returns Int))
    ''')
    control = tmp_path / ".command-control"
    control.mkdir()
    run = _run_cli(case, control)
    assert run.returncode == 1, run.stderr
    run_root = _case_run_root(case)
    state = _state_file(run_root)
    error = state["effects"][0]["error"]
    assert type(error["metadata"].get("steps")) is int
    error["metadata"]["steps"] += 1
    _write_state(run_root, state)
    before = _hashes(run_root)

    repl = _attach_case(case, run_root, ":bindings", env=_inspection_env(control))

    assert repl.returncode == 0, repl.stderr
    assert "[dynamic_state_invalid]" in repl.stderr
    assert _hashes(run_root) == before


def test_public_native_repl_replays_effect_then_pure_failure_without_republishing(tmp_path):
    body = '''
      (export main)
      (define (payload n) (let* ((helper_local (+ n 1))) helper_local))
      (defworkflow main () -> Int
        (let* ((first (command-result probe
                       :argv ("python" "interrupt_probe.py" (payload 16) "TOKEN_ONLY") :returns Int))
               (bad (/ 1 0)))
          bad))
    '''
    case, control, run, run_root = _command_case(tmp_path, body)
    assert run.returncode == 1, run.stderr
    before = _hashes(run_root)
    events = _events(control)
    assert [event["label"] for event in events] == ["only"]

    repl = _attach_case(case, run_root, ":bindings", "first", ":result",
                        env=_inspection_env(control))

    assert repl.returncode == 0, repl.stderr
    assert "first : Int" in repl.stdout
    names = {line.split(" : ", 1)[0] for line in repl.stdout.splitlines() if " : " in line}
    assert "helper_local" not in names
    assert _typed_values(repl.stdout) == [(17, "Int")]
    assert "[repl_no_result]" in repl.stderr
    assert _hashes(run_root) == before and _events(control) == events


def test_public_native_repl_captures_pure_failure_before_first_effect(tmp_path):
    body = '''
      (export main)
      (defworkflow main () -> Int
        (let* ((seed 4) (bad (/ 1 0))
               (later (command-result probe :argv ("python" "interrupt_probe.py" "TOKEN_ONLY") :returns Int)))
          later))
    '''
    case, control, run, run_root = _command_case(tmp_path, body)
    assert run.returncode == 1, run.stderr
    before = _hashes(run_root)
    assert _state(run_root)["effects"] == [] and _events(control) == []

    repl = _attach_case(case, run_root, ":bindings", "seed", ":result",
                        env=_inspection_env(control))

    assert repl.returncode == 0, repl.stderr
    assert "seed : Int" in repl.stdout
    assert _typed_values(repl.stdout) == [(4, "Int")]
    assert "[repl_no_result]" in repl.stderr
    assert _hashes(run_root) == before and _events(control) == []


def test_public_repl_refuses_flat_run_attachment_read_only(tmp_path):
    source = write_source(tmp_path, "flat/main", '''
      (export run)
      (defworkflow run ((n Int :default 7)) -> Int n)
    ''', target="2.34", budget=None)
    run = _run(tmp_path, source)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    assert not (run_root / "run.json").exists()
    before = _hashes(tmp_path)

    repl = _repl(tmp_path, [f":attach {run_root.name}", ":quit"])

    assert repl.returncode == 0, repl.stderr
    assert "[repl_profile_unsupported]" in repl.stderr
    assert "[repl_io_error]" not in repl.stderr
    assert _hashes(tmp_path) == before
