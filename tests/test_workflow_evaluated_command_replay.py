from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow.evaluated import runtime as runtime_module
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.memo import memo_writer_lock
from tests.test_workflow_evaluated_command_lifecycle import (
    _InterruptedRun, _program, _publish, _script, _started_snapshot,
)


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
