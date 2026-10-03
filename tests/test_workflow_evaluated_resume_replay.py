from __future__ import annotations

import json
import os
from pathlib import Path

from tests.test_workflow_evaluated_providers import (
    SOURCE,
    _cli as _provider_cli,
    _fixture as _provider_fixture,
    _requests,
)
from tests.test_workflow_evaluated_resume import _resume_cli, _snapshot
from tests.test_workflow_evaluated_cli import _run_cli


def _create_completed_three_command_run(tmp_path: Path) -> Path:
    source = tmp_path / "replay.orc"
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule replay) (export run)
          (defworkflow run () -> Int
            (let* ((first (command-result first :argv ("python" "first.py") :returns Int))
                   (second (command-result second :argv ("python" "second.py" first) :returns Int))
                   (third (command-result third :argv ("python" "third.py" second) :returns Int)))
              third)))''',
        encoding="utf-8",
    )
    scripts = {
        "first.py": ("first", "1"),
        "second.py": ("second", "2"),
        "third.py": ("third", "3"),
    }
    for filename, (name, value) in scripts.items():
        (tmp_path / filename).write_text(
            "import os, sys\nfrom pathlib import Path\n"
            f'Path("dispatches.txt").open("a", encoding="utf-8").write("{name}:" + ",".join(sys.argv[1:]) + "\\n")\n'
            f'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("{value}", encoding="utf-8")\n',
            encoding="utf-8",
        )
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(
        json.dumps({name: {"stable_command": ["python", f"{name}.py"], "closure": [f"{name}.py"]}
                    for name in ("first", "second", "third")}),
        encoding="utf-8",
    )

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundaries))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == [
        "first:", "second:1", "third:2"
    ]
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    return run_root


def _assert_completed_resume_is_readonly_with_torn_tail(tmp_path: Path, run_root: Path) -> None:
    (run_root / "state.json").write_text('{"status":"stale"}', encoding="utf-8")
    with (run_root / "memo.jsonl").open("ab") as stream:
        stream.write(b'{"record":"partial"')
    completed_snapshot = _snapshot(tmp_path / ".orchestrate")
    for _ in range(2):
        completed = _resume_cli(tmp_path, run_root.name)
        assert completed.returncode == 0, completed.stderr
        assert _snapshot(tmp_path / ".orchestrate") == completed_snapshot
    assert (run_root / "state.json").read_text(encoding="utf-8") == '{"status":"stale"}'
    assert (run_root / "memo.jsonl").read_bytes().endswith(b'{"record":"partial"')


def _assert_changed_completed_effect_refuses_without_dispatch(tmp_path: Path, run_root: Path) -> None:
    second = tmp_path / "second.py"
    second.write_text(second.read_text(encoding="utf-8") + "# changed closure\n", encoding="utf-8")
    before = _snapshot(tmp_path / ".orchestrate")
    resumed = _resume_cli(tmp_path, run_root.name)

    assert resumed.returncode == 2, resumed.stderr
    assert "effect_input_diverged" in resumed.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == [
        "first:", "second:1", "third:2"
    ]
    assert _snapshot(tmp_path / ".orchestrate") == before


def test_completed_resume_replays_ordered_commits_before_returning_terminal(tmp_path: Path) -> None:
    run_root = _create_completed_three_command_run(tmp_path)
    _assert_completed_resume_is_readonly_with_torn_tail(tmp_path, run_root)
    _assert_changed_completed_effect_refuses_without_dispatch(tmp_path, run_root)


def test_completed_terminal_halt_compares_bool_and_int_canonically(tmp_path: Path) -> None:
    source = tmp_path / "scalar.orc"
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule scalar) (export run) (defworkflow run () -> Int 1))''',
        encoding="utf-8",
    )
    result = _run_cli(tmp_path, str(source))
    assert result.returncode == 0, result.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    memo_path = run_root / "memo.jsonl"
    rows = [json.loads(line) for line in memo_path.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["outcome"] == "completed" and rows[-1]["value"] == 1
    rows[-1]["value"] = True
    memo_path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows))
    before = _snapshot(tmp_path / ".orchestrate")

    resumed = _resume_cli(tmp_path, run_root.name)

    assert resumed.returncode == 2, resumed.stderr
    assert "memo_inconsistent" in resumed.stderr
    assert _snapshot(tmp_path / ".orchestrate") == before


def test_completed_resume_does_not_sweep_an_unreached_command_closure(tmp_path: Path) -> None:
    source = tmp_path / "dormant.orc"
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule dormant) (export run)
          (defworkflow run () -> Int
            (if false
                (command-result unused :argv ("python" "unused.py") :returns Int)
                0)))''',
        encoding="utf-8",
    )
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(json.dumps({"unused": {
        "stable_command": ["python", "unused.py"], "closure": ["missing-helper.py"]
    }}), encoding="utf-8")

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundaries))

    assert result.returncode == 0, result.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    before = _snapshot(tmp_path / ".orchestrate")
    resumed = _resume_cli(tmp_path, run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert not (tmp_path / "unused.py").exists()


def _create_failed_attempt_without_terminal(tmp_path: Path, monkeypatch):
    from tests.test_workflow_evaluated_command_lifecycle import _program, _publish
    from orchestrator.workflow.evaluated import runtime as runtime_module
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.memo import memo_writer_lock, read_memo
    from orchestrator.workflow.evaluated.machine import site_classes

    class Interrupted(BaseException):
        pass

    script = tmp_path / "probe.py"
    original_script = (
        "import os, sys\nfrom pathlib import Path\n"
        "target = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])\n"
        "Path('dispatches.txt').open('a', encoding='utf-8').write(target.parent.name + '\\n')\n"
        "if target.parent.name == 'attempt-1': sys.exit(9)\n"
        "target.write_text('5', encoding='utf-8')\n"
    )
    script.write_text(original_script, encoding="utf-8")
    _source, program = _program(
        tmp_path,
        '(command-result emit :argv ("python" "probe.py") :returns Int)',
        bindings={"emit": "probe.py"},
    )
    with _publish(tmp_path, program) as authority:
        real_append = runtime_module.append_record

        def stop_after_failed(path, record):
            entry = real_append(path, record)
            if record["record"] == "failed":
                raise Interrupted()
            return entry

        with monkeypatch.context() as patched:
            patched.setattr(runtime_module, "append_record", stop_after_failed)
            try:
                runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)
            except Interrupted:
                pass
            else:
                raise AssertionError("failed attempt was not interrupted before terminal")

    run_root = tmp_path / ".state" / "runs" / "run-1"
    return run_root, load_run_authority(run_root), script, original_script


def _assert_failed_baseline_refusal(authority, workspace: Path, before: bytes) -> None:
    from orchestrator.workflow.evaluated import runtime as runtime_module
    from orchestrator.workflow.evaluated.memo import memo_writer_lock
    from tests.test_workflow_evaluated_resume import _snapshot

    with memo_writer_lock(authority.run_root):
        refused = runtime_module.execute_pure_resume(
            authority, {}, run_id="run-1", workspace=workspace
        )
    assert refused == (2, None)
    assert authority.memo_path.read_bytes().endswith(b'{"record":"partial"')
    assert _snapshot(workspace / ".state") == before


def _assert_failed_baseline_retries_once(authority, workspace: Path, script, original_script, attempt_one, old_attempt_evidence):
    from orchestrator.workflow.evaluated import runtime as runtime_module
    from orchestrator.workflow.evaluated.memo import memo_writer_lock
    from tests.test_workflow_evaluated_resume import _snapshot

    script.write_text(original_script, encoding="utf-8")
    with memo_writer_lock(authority.run_root):
        resumed = runtime_module.execute_pure_resume(
            authority, {}, run_id="run-1", workspace=workspace
        )
    assert resumed == (0, 5)
    rows = [json.loads(line) for line in authority.memo_path.read_text(encoding="utf-8").splitlines()]
    assert [row["attempt"] for row in rows if row["record"] == "started"] == [1, 2]
    assert {path.name: path.read_bytes() for path in attempt_one.iterdir()} == old_attempt_evidence
    assert (workspace / "dispatches.txt").read_text(encoding="utf-8").splitlines() == [
        "attempt-1", "attempt-2"
    ]


def test_resume_preflights_failed_attempt_baseline_before_tail_repair(tmp_path: Path, monkeypatch) -> None:
    from orchestrator.workflow.evaluated.memo import read_memo
    from orchestrator.workflow.evaluated.machine import site_classes

    run_root, authority, script, original_script = _create_failed_attempt_without_terminal(tmp_path, monkeypatch)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert snapshot.pending_starts == {} and snapshot.terminal is None
    assert [entry.data["record"] for entry in snapshot.entries] == ["started", "failed"]
    attempt_one = next(run_root.glob("effects/*/attempt-1"))
    old_attempt_evidence = {path.name: path.read_bytes() for path in attempt_one.iterdir()}
    with authority.memo_path.open("ab") as stream:
        stream.write(b'{"record":"partial"')
    before = _snapshot(tmp_path / ".state")
    script.write_text(original_script + "# changed implementation bytes\n", encoding="utf-8")

    _assert_failed_baseline_refusal(authority, tmp_path, before)
    _assert_failed_baseline_retries_once(
        authority, tmp_path, script, original_script, attempt_one, old_attempt_evidence
    )


def test_completed_provider_resume_reuses_deleted_must_exist_result_twice(tmp_path: Path, monkeypatch) -> None:
    source = SOURCE.replace(
        "(defrecord Result (ok Bool))",
        '(defpath Artifact :kind relpath :under "artifacts/work" :must-exist true)',
    ).replace("Result", "Artifact")
    fixture = _provider_fixture(tmp_path, source)
    artifact = tmp_path / "artifacts" / "work" / "saved.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("committed output\n", encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    result = _provider_cli(tmp_path, fixture, payload='"artifacts/work/saved.txt"')

    assert result.returncode == 0, result.stderr
    run_root = next((tmp_path / ".orchestrate" / "runs").iterdir())
    rows = [json.loads(line) for line in (run_root / "memo.jsonl").read_text(encoding="utf-8").splitlines()]
    committed = next(row for row in rows if row["record"] == "committed")
    assert committed["value"] == "artifacts/work/saved.txt"
    artifact.unlink()
    (run_root / "state.json").write_text('{"status":"stale"}', encoding="utf-8")
    with (run_root / "memo.jsonl").open("ab") as stream:
        stream.write(b'{"record":"partial"')
    before = _snapshot(tmp_path / ".orchestrate")

    for _ in range(2):
        resumed = _resume_cli(tmp_path, run_root.name)
        assert resumed.returncode == 0, resumed.stderr
        assert _snapshot(tmp_path / ".orchestrate") == before
    assert len(_requests(tmp_path)) == 1
    assert not artifact.exists()
    _assert_provider_replay_skips_result_validation(tmp_path, run_root, before, monkeypatch)


def _assert_provider_replay_skips_result_validation(tmp_path: Path, run_root: Path, before, monkeypatch) -> None:
    from orchestrator.workflow.evaluated import commands as command_module
    from orchestrator.cli.commands.resume import resume_workflow

    validations = []

    def forbidden_validation(*args, **kwargs):
        validations.append((args, kwargs))
        raise AssertionError("completed provider replay revalidated committed result bytes")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(command_module, "_validate_result_bytes", forbidden_validation)
    assert resume_workflow(run_root.name) == 0
    assert validations == []
    assert _snapshot(tmp_path / ".orchestrate") == before


def test_public_pure_failure_resume_twice_preserves_failed_terminal(tmp_path: Path) -> None:
    from orchestrator.workflow.evaluated.memo import read_memo

    source = tmp_path / "failure.orc"
    source.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule failure) (export run) '
        '(defworkflow run ((divisor Float)) -> Float (/ 1.0 divisor)))\n',
        encoding="utf-8",
    )
    run = _run_cli(tmp_path, str(source), "--input", "divisor=0")
    assert run.returncode == 1
    run_root = next((tmp_path / ".orchestrate" / "runs").iterdir())
    before = _snapshot(tmp_path / ".orchestrate")

    for _ in range(2):
        resumed = _resume_cli(tmp_path, run_root.name)
        assert resumed.returncode in {1, 2}, resumed.stderr
        assert "pure_expr_division_by_zero" in resumed.stderr
        assert _snapshot(tmp_path / ".orchestrate") == before
    terminal = read_memo(run_root / "memo.jsonl", {}).terminal
    assert terminal is not None
    assert terminal.data["outcome"] == "failed"
    assert terminal.data["code"] == "pure_expr_division_by_zero"
