from __future__ import annotations

import hashlib
import inspect
from functools import partial
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated import effect_inputs
from orchestrator.workflow.evaluated import runtime as runtime_module
from orchestrator.workflow.evaluated.authority import load_run_authority, publish_run_authority
from orchestrator.workflow.evaluated.machine import site_classes as command_site_classes
from orchestrator.workflow.evaluated.memo import memo_writer_lock, read_memo
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from tests.test_workflow_evaluated_command_lifecycle import (
    _InterruptedRun, _program, _publish, _script, _started_snapshot,
)


def _append_then_interrupt_after_first_commit(real_append, state, path, record, **kwargs):
    entry = real_append(path, record, **kwargs)
    if record.get("record") == "committed" and not state["interrupted"]:
        state["interrupted"] = True
        raise _InterruptedAfterCommit()
    return entry


def _remove_artifact_before_producer_reuse(real_reuse, artifact, *args, **kwargs):
    node = inspect.signature(real_reuse).bind(*args, **kwargs).arguments["node"]
    if node["boundary"] == "produce":
        artifact.unlink()
    return real_reuse(*args, **kwargs)


def _assert_path_replay_result(exit_code, value, artifact, tmp_path):
    assert (exit_code, value) == (0, 9)
    assert not artifact.exists()
    assert (tmp_path / "received-path.txt").read_text(encoding="utf-8") == "artifacts/work/output.json"


def _assert_path_replay_commit_lineage(after, producer_commit, dispatches_before):
    commits = [entry.data for entry in after.entries if entry.data["record"] == "committed"]
    assert len(commits) == 2
    assert commits[0] == producer_commit
    assert commits[1]["input_parts"]["argv"] == canonical_sha256([
        "python", "consume.py", "artifacts/work/output.json"
    ])
    assert commits[1]["input_digest"] == canonical_sha256(commits[1]["input_parts"])
    assert commits[1]["depends_on"] == [commits[0]["identity"]]
    assert after.raw.startswith(dispatches_before)
    assert after.terminal is not None and after.terminal.data["value"] == 9


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

        def interrupt_after_commit(path, record, **kwargs):
            entry = real_append(path, record, **kwargs)
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


class _InterruptedAfterCommit(BaseException):
    pass


def test_committed_must_exist_path_can_be_rendered_after_artifact_disappears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "evaluated" / "path_replay.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule evaluated/path_replay) (export run)
          (defpath ArtifactPath :kind relpath :under "artifacts/work" :must-exist true)
          (defrecord Produced (path ArtifactPath))
          (defproc consume-path ((path ArtifactPath)) -> Int
            :effects ((uses-command consume)) :lowering private-workflow
            (command-result consume :argv ("python" "consume.py" "${inputs.path}") :returns Int))
          (defworkflow run () -> Int
            (let* ((produced (command-result produce :argv ("python" "produce.py") :returns Produced)))
              (consume-path produced.path))))
''',
        encoding="utf-8",
    )
    producer = tmp_path / "produce.py"
    producer.write_text(
        'import json, os\nfrom pathlib import Path\n'
        'Path("artifacts/work").mkdir(parents=True, exist_ok=True)\n'
        'Path("artifacts/work/output.json").write_text("{}", encoding="utf-8")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('
        'json.dumps({"path": "artifacts/work/output.json"}), encoding="utf-8")\n',
        encoding="utf-8",
    )
    consumer = tmp_path / "consume.py"
    consumer.write_text(
        'import os, sys\nfrom pathlib import Path\n'
        'Path("received-path.txt").write_text(sys.argv[1], encoding="utf-8")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("9", encoding="utf-8")\n',
        encoding="utf-8",
    )
    boundaries = {
        name: ExternalToolBinding(
            name=name,
            stable_command=("python", f"{name}.py"),
            closure=(f"{name}.py",),
        )
        for name in ("produce", "consume")
    }
    program = build_closed_program(compile_typed_program(
        source,
        entry_workflow="evaluated/path_replay::run",
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        command_boundaries=boundaries,
    ))
    run_root = tmp_path / ".state" / "runs" / "run-1"
    with publish_run_authority(
        run_root,
        program,
        run_id="run-1",
        workflow_file="path_replay.orc",
        workflow_checksum="sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
        resume_request={"source_roots": [], "entry_workflow": None,
            "provider_externs_path": None, "prompt_externs_path": None,
            "imported_workflow_bundles_path": None, "command_boundaries_path": None,
            "input_file": None, "input_overrides": {}},
        bound_inputs={},
    ) as authority:
        real_append = runtime_module.append_record
        interrupted = {"interrupted": False}

        with monkeypatch.context() as patched:
            patched.setattr(
                runtime_module, "append_record",
                partial(_append_then_interrupt_after_first_commit, real_append, interrupted),
            )
            with pytest.raises(_InterruptedAfterCommit):
                runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)

    authority = load_run_authority(run_root)
    checked_classes = command_site_classes(program)
    prior = read_memo(authority.memo_path, checked_classes)
    producer_commit = next(
        entry.data for entry in prior.entries if entry.data["record"] == "committed"
    )
    artifact = tmp_path / "artifacts/work/output.json"
    assert artifact.is_file()
    dispatches_before = prior.raw
    real_reuse = effect_inputs._reuse_effect_commit

    with monkeypatch.context() as patched:
        patched.setattr(
            effect_inputs, "_reuse_effect_commit",
            partial(_remove_artifact_before_producer_reuse, real_reuse, artifact),
        )
        with memo_writer_lock(authority.run_root):
            exit_code, value = runtime_module.execute_pure_run(
                authority, {}, run_id="run-1", workspace=tmp_path
            )

    after = read_memo(authority.memo_path, checked_classes)
    _assert_path_replay_result(exit_code, value, artifact, tmp_path)
    _assert_path_replay_commit_lineage(after, producer_commit, dispatches_before)
