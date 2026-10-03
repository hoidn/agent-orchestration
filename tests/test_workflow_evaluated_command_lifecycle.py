from __future__ import annotations

import hashlib
import json
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

import orchestrator.workflow.evaluated.memo as memo_module
import orchestrator.workflow.evaluated.runtime as runtime_module
import orchestrator.workflow.workspace_files as workspace_files_module
from orchestrator.workflow.evaluated.attempts import attempt_paths
from orchestrator.workflow.evaluated.authority import load_run_authority, publish_run_authority
from orchestrator.workflow.evaluated.machine import site_classes as command_site_classes
from orchestrator.workflow.evaluated.memo import append_record, invalidate_suffix, memo_writer_lock, read_memo
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding


class _InterruptedRun(BaseException):
    pass


def _program(
    root: Path,
    body: str,
    *,
    declarations: str = "",
    bindings: dict[str, str],
    stable_suffix: tuple[str, ...] = (),
    must_not_repeat: bool = False,
):
    source = root / "lifecycle.orc"
    source.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule lifecycle) (export run) ' + declarations +
        '(defworkflow run () -> Int ' + body + '))\n',
        encoding="utf-8",
    )
    command_bindings = {
        name: ExternalToolBinding(
            name=name,
            stable_command=("python", script, *stable_suffix),
            closure=(script,),
            must_not_repeat=must_not_repeat,
        )
        for name, script in bindings.items()
    }
    typed = compile_typed_program(
        source,
        entry_workflow="lifecycle::run",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries=command_bindings,
    )
    return source, build_closed_program(typed)


@contextmanager
def _publish(root: Path, program):
    run_root = root / ".state" / "runs" / "run-1"
    with publish_run_authority(
        run_root,
        program,
        run_id="run-1",
        workflow_file="lifecycle.orc",
        workflow_checksum="sha256:" + hashlib.sha256(b"lifecycle source").hexdigest(),
        resume_request={"source_roots": [], "entry_workflow": None,
            "provider_externs_path": None, "prompt_externs_path": None,
            "imported_workflow_bundles_path": None, "command_boundaries_path": None,
            "input_file": None, "input_overrides": {}},
        bound_inputs={},
    ) as authority:
        yield authority


def _script(root: Path, name: str = "probe.py") -> Path:
    path = root / name
    path.write_text(
        'import json, os\nfrom pathlib import Path\n'
        'marker = Path("dispatches.txt")\n'
        'marker.open("a", encoding="utf-8").write("x\\n")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("5", encoding="utf-8")\n',
        encoding="utf-8",
    )
    return path


def _started_snapshot(authority, program):
    return read_memo(authority.memo_path, command_site_classes(program))


def test_pending_start_retry_refusal_preserves_memo_and_next_ordinal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    script = _script(tmp_path)
    _source, program = _program(
        tmp_path,
        '(command-result emit :argv ("python" "probe.py") :returns Int)',
        bindings={"emit": "probe.py"},
    )
    publisher = _publish(tmp_path, program)
    with publisher as authority:
        real_mkdir = workspace_files_module.WorkspaceFiles.mkdir_exclusive

        def stop_after_started(owner, path):
            if str(path).startswith("effects/"):
                raise _InterruptedRun()
            return real_mkdir(owner, path)

        with monkeypatch.context() as patched:
            patched.setattr(workspace_files_module.WorkspaceFiles, "mkdir_exclusive", stop_after_started)
            with pytest.raises(_InterruptedRun):
                runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)

    authority = load_run_authority(tmp_path / ".state" / "runs" / "run-1")
    before = authority.memo_path.read_bytes()
    script.write_text(script.read_text(encoding="utf-8") + "# changed closure bytes\n", encoding="utf-8")

    with memo_writer_lock(authority.run_root):
        exit_code, value = runtime_module.execute_pure_run(
            authority, {}, run_id="run-1", workspace=tmp_path
        )

    snapshot = _started_snapshot(authority, program)
    identity = next(iter(snapshot.pending_starts))
    assert exit_code == 1
    assert value is None
    assert authority.memo_path.read_bytes() == before
    assert set(snapshot.pending_starts) == {identity}
    assert [entry.data["record"] for entry in snapshot.entries] == ["started"]
    assert attempt_paths(snapshot, identity)[0] == 2
    assert not (authority.run_root / Path(snapshot.pending_starts[identity].data["result_path"]).parent).exists()
    assert not (tmp_path / "dispatches.txt").exists()
    assert "[effect_input_diverged]" in caplog.text
    assert "[effect_rerun]" not in caplog.text


def test_pending_start_retry_with_unchanged_closure_runs_next_ordinal_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _script(tmp_path)
    _source, program = _program(
        tmp_path,
        '(command-result emit :argv ("python" "probe.py") :returns Int)',
        bindings={"emit": "probe.py"},
    )
    real_mkdir = workspace_files_module.WorkspaceFiles.mkdir_exclusive

    def stop_after_started(owner, path):
        if str(path).startswith("effects/"):
            raise _InterruptedRun()
        return real_mkdir(owner, path)

    with monkeypatch.context() as patched:
        patched.setattr(workspace_files_module.WorkspaceFiles, "mkdir_exclusive", stop_after_started)
        with _publish(tmp_path, program) as authority:
            with pytest.raises(_InterruptedRun):
                runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)
        authority = load_run_authority(tmp_path / ".state" / "runs" / "run-1")
        with memo_writer_lock(authority.run_root):
            with pytest.raises(_InterruptedRun):
                runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)
    with memo_writer_lock(authority.run_root):
        exit_code, value = runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)

    snapshot = _started_snapshot(authority, program)
    starts = [entry.data for entry in snapshot.entries if entry.data["record"] == "started"]
    commits = [entry.data for entry in snapshot.entries if entry.data["record"] == "committed"]
    identity = starts[0]["identity"]
    assert (exit_code, value) == (0, 5)
    assert [row["attempt"] for row in starts] == [1, 2, 3]
    assert [row["attempt"] for row in commits] == [3]
    assert [entry.data["record"] for entry in snapshot.entries] == [
        "started", "started", "started", "committed", "terminal"
    ]
    assert all(not (authority.run_root / Path(row["result_path"]).parent).exists() for row in starts[:2])
    assert (authority.run_root / Path(starts[2]["result_path"]).parent).is_dir()
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["x"]
    reruns = [record.getMessage() for record in caplog.records if record.msg.startswith("[effect_rerun]")]
    assert reruns == [f"[effect_rerun] {identity} attempts=[1]", f"[effect_rerun] {identity} attempts=[1, 2]"]


def test_invalidation_releases_only_the_invalidated_commit_closure_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    script = _script(tmp_path)
    _source, program = _program(
        tmp_path,
        '(command-result emit :argv ("python" "probe.py") :returns Int)',
        bindings={"emit": "probe.py"},
    )
    with _publish(tmp_path, program) as authority:
        exit_code, value = runtime_module.execute_pure_run(
            authority, {}, run_id="run-1", workspace=tmp_path
        )
    assert (exit_code, value) == (0, 5)

    authority = load_run_authority(tmp_path / ".state" / "runs" / "run-1")
    site_classes = command_site_classes(program)
    first = _started_snapshot(authority, program)
    identity = next(iter(first.active_commits))
    with memo_writer_lock(authority.run_root):
        invalidate_suffix(authority.memo_path, identity, site_classes)

    script.write_text(script.read_text(encoding="utf-8") + "# changed after invalidation\n", encoding="utf-8")
    with memo_writer_lock(authority.run_root):
        exit_code, value = runtime_module.execute_pure_run(
            authority, {}, run_id="run-1", workspace=tmp_path
        )
    assert (exit_code, value) == (0, 5)
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["x", "x"]
    assert "[effect_rerun]" not in caplog.text

    second = _started_snapshot(authority, program)
    second_commit = second.active_commits[identity]
    with memo_writer_lock(authority.run_root):
        invalidate_suffix(authority.memo_path, identity, site_classes)
    script.write_text(script.read_text(encoding="utf-8") + "# third attempt baseline\n", encoding="utf-8")

    real_mkdir = workspace_files_module.WorkspaceFiles.mkdir_exclusive

    def stop_after_started(owner, path):
        if str(path).startswith("effects/"):
            raise _InterruptedRun()
        return real_mkdir(owner, path)

    with monkeypatch.context() as patched:
        patched.setattr(workspace_files_module.WorkspaceFiles, "mkdir_exclusive", stop_after_started)
        with memo_writer_lock(authority.run_root):
            with pytest.raises(_InterruptedRun):
                runtime_module.execute_pure_run(
                    authority, {}, run_id="run-1", workspace=tmp_path
                )

    pending = _started_snapshot(authority, program)
    third_start = pending.pending_starts[identity]
    assert third_start.data["attempt"] == 3
    assert second_commit.data["record"] == "committed"
    before = authority.memo_path.read_bytes()
    script.write_text(script.read_text(encoding="utf-8") + "# changed while pending\n", encoding="utf-8")

    with memo_writer_lock(authority.run_root):
        exit_code, value = runtime_module.execute_pure_run(
            authority, {}, run_id="run-1", workspace=tmp_path
        )

    after = _started_snapshot(authority, program)
    assert (exit_code, value) == (1, None)
    assert authority.memo_path.read_bytes() == before
    assert after.pending_starts[identity].data == third_start.data
    assert attempt_paths(after, identity)[0] == 4
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["x", "x"]


def test_committed_command_replay_does_not_redispatch_or_revalidate_result_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _script(tmp_path)
    _source, program = _program(
        tmp_path,
        '(command-result emit :argv ("python" "probe.py") :returns Int)',
        bindings={"emit": "probe.py"},
    )
    publisher = _publish(tmp_path, program)
    with publisher as authority:
        real_append = runtime_module.append_record

        def interrupt_after_commit(path, record):
            entry = real_append(path, record)
            if record.get("record") == "committed":
                raise _InterruptedRun()
            return entry

        with monkeypatch.context() as patched:
            patched.setattr(runtime_module, "append_record", interrupt_after_commit)
            with pytest.raises(_InterruptedRun):
                runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)

    authority = load_run_authority(tmp_path / ".state" / "runs" / "run-1")
    before = _started_snapshot(authority, program)
    commit = next(entry.data for entry in before.entries if entry.data["record"] == "committed")
    result_path = authority.run_root / commit["result_path"]
    result_path.unlink()
    dispatches_before = (tmp_path / "dispatches.txt").read_text(encoding="utf-8")

    with memo_writer_lock(authority.run_root):
        exit_code, value = runtime_module.execute_pure_run(
            authority, {}, run_id="run-1", workspace=tmp_path
        )

    after = _started_snapshot(authority, program)
    assert exit_code == 0
    assert value == 5
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8") == dispatches_before
    assert len([row for row in after.entries if row.data["record"] == "started"]) == 1
    assert len([row for row in after.entries if row.data["record"] == "committed"]) == 1
    assert after.terminal is not None and after.terminal.data["outcome"] == "completed"


def test_command_dependency_records_only_values_read_by_current_effect(tmp_path: Path) -> None:
    first = tmp_path / "first.py"
    first.write_text(
        'import os\nfrom pathlib import Path\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("5", encoding="utf-8")\n',
        encoding="utf-8",
    )
    second = tmp_path / "second.py"
    second.write_text(
        'import os, sys\nfrom pathlib import Path\n'
        'Path("second-argv.json").write_text(sys.argv[1], encoding="utf-8")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("6", encoding="utf-8")\n',
        encoding="utf-8",
    )
    _source, program = _program(
        tmp_path,
        '(let* ((first (command-result first :argv ("python" "first.py") :returns Int)) '
        '(second (command-result second :argv ("python" "second.py" first) :returns Int))) second)',
        bindings={"first": "first.py", "second": "second.py"},
    )
    publisher = _publish(tmp_path, program)
    with publisher as authority:
        exit_code, value = runtime_module.execute_pure_run(
            authority, {}, run_id="run-1", workspace=tmp_path
        )

    snapshot = _started_snapshot(authority, program)
    commits = [entry.data for entry in snapshot.entries if entry.data["record"] == "committed"]
    assert exit_code == 0
    assert value == 6
    assert len(commits) == 2
    assert (tmp_path / "second-argv.json").read_text(encoding="utf-8") == "5"
    assert commits[1]["depends_on"] == [commits[0]["identity"]]


@pytest.mark.parametrize("change", ("replace", "appear"))
def test_closure_change_or_appearance_during_child_fails_the_started_ordinal(
    tmp_path: Path, change: str
) -> None:
    script = tmp_path / "probe.py"
    mutate = (
        'Path(__file__).write_text(Path(__file__).read_text() + "# changed\\n", encoding="utf-8")'
        if change == "replace"
        else 'Path("appeared.py").write_text("# appeared\\n", encoding="utf-8")'
    )
    script.write_text(
        "import os\nfrom pathlib import Path\n"
        'Path("dispatches.txt").open("a", encoding="utf-8").write("x\\n")\n'
        + mutate + "\n"
        + 'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("5", encoding="utf-8")\n',
        encoding="utf-8",
    )
    suffix = ("appeared.py",) if change == "appear" else ()
    argv = '("python" "probe.py" "appeared.py")' if change == "appear" else '("python" "probe.py")'
    _source, program = _program(
        tmp_path,
        f'(command-result emit :argv {argv} :returns Int)',
        bindings={"emit": "probe.py"},
        stable_suffix=suffix,
    )

    with _publish(tmp_path, program) as authority:
        exit_code, value = runtime_module.execute_pure_run(
            authority, {}, run_id="run-1", workspace=tmp_path
        )

    snapshot = _started_snapshot(authority, program)
    started = next(row.data for row in snapshot.entries if row.data["record"] == "started")
    failed = next(row.data for row in snapshot.entries if row.data["record"] == "failed")
    assert (exit_code, value) == (1, None)
    assert [row.data["record"] for row in snapshot.entries] == ["started", "failed", "terminal"]
    assert (started["attempt"], failed["attempt"]) == (1, 1)
    assert failed["code"] == "command_closure_written"
    assert snapshot.terminal is not None
    assert snapshot.terminal.data["code"] == "command_closure_written"
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["x"]
    if change == "appear":
        assert (tmp_path / "appeared.py").exists()
    else:
        assert "# changed" in script.read_text(encoding="utf-8")


def test_must_not_repeat_pending_command_refuses_without_new_attempt_or_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _script(tmp_path)
    _source, program = _program(
        tmp_path,
        '(command-result emit :argv ("python" "probe.py") :returns Int)',
        bindings={"emit": "probe.py"},
        must_not_repeat=True,
    )
    with _publish(tmp_path, program) as authority:
        real_mkdir = workspace_files_module.WorkspaceFiles.mkdir_exclusive

        def stop_after_started(owner, path):
            if str(path).startswith("effects/"):
                raise _InterruptedRun()
            return real_mkdir(owner, path)

        with monkeypatch.context() as patched:
            patched.setattr(workspace_files_module.WorkspaceFiles, "mkdir_exclusive", stop_after_started)
            with pytest.raises(_InterruptedRun):
                runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)

    authority = load_run_authority(tmp_path / ".state" / "runs" / "run-1")
    before = authority.memo_path.read_bytes()
    with memo_writer_lock(authority.run_root):
        exit_code, value = runtime_module.execute_pure_run(
            authority, {}, run_id="run-1", workspace=tmp_path
        )
    snapshot = _started_snapshot(authority, program)
    assert (exit_code, value) == (1, None)
    assert authority.memo_path.read_bytes() == before
    assert [row.data["record"] for row in snapshot.entries] == ["started"]
    assert attempt_paths(snapshot, next(iter(snapshot.pending_starts)))[0] == 2
    assert not (tmp_path / "dispatches.txt").exists()
    assert "[effect_rerun]" not in caplog.text


def test_new_command_does_not_start_while_another_checked_effect_is_pending(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _script(tmp_path, "first.py")
    _script(tmp_path, "second.py")
    _source, program = _program(
        tmp_path,
        '(let* ((first (command-result first :argv ("python" "first.py") :returns Int)) '
        '(second (command-result second :argv ("python" "second.py") :returns Int))) second)',
        bindings={"first": "first.py", "second": "second.py"},
    )
    with _publish(tmp_path, program) as authority:
        site_classes = command_site_classes(program)
        pending_identity = sorted(site_classes)[1]
        snapshot = read_memo(authority.memo_path, site_classes)
        ordinal, _directory, result_path = attempt_paths(snapshot, pending_identity)
        append_record(
            authority.memo_path,
            {
                "record": "started",
                "identity": pending_identity,
                "attempt": ordinal,
                "input_digest": canonical_sha256({}),
                "input_parts": {},
                "implementation_files": {},
                "result_path": result_path,
                "time": time.time(),
            },
        )
        before = authority.memo_path.read_bytes()
        exit_code, value = runtime_module.execute_pure_run(
            authority, {}, run_id="run-1", workspace=tmp_path
        )

    after = read_memo(authority.memo_path, site_classes)
    assert (exit_code, value) == (1, None)
    assert authority.memo_path.read_bytes() == before
    assert set(after.pending_starts) == {pending_identity}
    assert after.terminal is None
    assert "[memo_inconsistent]" in caplog.text
    assert not (tmp_path / "dispatches.txt").exists()


def test_prior_terminal_refusal_does_not_append_a_second_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _script(tmp_path)
    _source, program = _program(
        tmp_path,
        '(command-result emit :argv ("python" "probe.py") :returns Int)',
        bindings={"emit": "probe.py"},
    )
    with _publish(tmp_path, program) as authority:
        site_classes = command_site_classes(program)
        append_record(
            authority.memo_path,
            {"record": "terminal", "outcome": "failed", "code": "prior_failure", "message": "prior"},
        )
        before = authority.memo_path.read_bytes()

        def refuse(*args, **kwargs):
            error = RuntimeError("pre-start refusal")
            error.code = "effect_input_invalid"
            raise error

        with monkeypatch.context() as patched:
            patched.setattr(runtime_module, "evaluate_closed_program", refuse)
            exit_code, value = runtime_module.execute_pure_run(
                authority, {}, run_id="run-1", workspace=tmp_path
            )

    snapshot = read_memo(authority.memo_path, site_classes)
    assert (exit_code, value) == (1, None)
    assert authority.memo_path.read_bytes() == before
    assert [row.data["record"] for row in snapshot.entries] == ["terminal"]
    assert not (tmp_path / "dispatches.txt").exists()
