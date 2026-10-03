from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from tests.test_workflow_evaluated_resume import _resume_cli, _snapshot
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_resume_retry import (
    _public_env,
    _run_root,
    _start_and_kill,
)


def _create_two_command_run(tmp_path: Path) -> Path:
    source = tmp_path / "order.orc"
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule order) (export run)
          (defworkflow run () -> Int
            (let* ((first (command-result first :argv ("python" "first.py") :returns Int))
                   (second (command-result second :argv ("python" "second.py") :returns Int)))
              (+ first second))))''',
        encoding="utf-8",
    )
    for name, value in (("first", "1"), ("second", "2")):
        (tmp_path / f"{name}.py").write_text(
            "import os\nfrom pathlib import Path\n"
            f'Path("dispatches.txt").open("a", encoding="utf-8").write("{name}\\n")\n'
            f'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("{value}", encoding="utf-8")\n',
            encoding="utf-8",
        )
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(
        json.dumps({name: {"stable_command": ["python", f"{name}.py"], "closure": [f"{name}.py"]}
                    for name in ("first", "second")}),
        encoding="utf-8",
    )

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundaries))
    assert result.returncode == 0, result.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["first", "second"]
    return run_root


def _reverse_active_commit_journal(run_root: Path) -> None:
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo

    authority = load_run_authority(run_root)
    rows = [json.loads(line) for line in authority.memo_path.read_text(encoding="utf-8").splitlines()]
    groups: list[list[dict]] = []
    for row in rows:
        if row["record"] == "started":
            groups.append([row])
        elif row["record"] == "committed":
            groups[-1].append(row)
    assert len(groups) == 2
    reordered = [*groups[1], *groups[0], rows[-1]]
    authority.memo_path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in reordered),
        encoding="utf-8",
    )
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    commits = sorted(snapshot.active_commits.values(), key=lambda entry: entry.offset)
    assert [entry.data["identity"] for entry in commits] == [
        groups[1][1]["identity"], groups[0][1]["identity"]
    ]


def test_completed_resume_rejects_active_commits_reordered_from_program_order(tmp_path: Path) -> None:
    run_root = _create_two_command_run(tmp_path)
    _reverse_active_commit_journal(run_root)
    before = _snapshot(tmp_path / ".orchestrate")

    resumed = _resume_cli(tmp_path, run_root.name)

    assert resumed.returncode == 2, resumed.stderr
    assert "memo_inconsistent" in resumed.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["first", "second"]
    assert _snapshot(tmp_path / ".orchestrate") == before


def _create_completed_branch_run(tmp_path: Path) -> Path:
    source = tmp_path / "branch.orc"
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule branch) (export run)
          (defworkflow run () -> Int
            (if (command-result choose :argv ("python" "choose.py") :returns Bool)
                (command-result yes :argv ("python" "yes.py") :returns Int)
                (command-result no :argv ("python" "no.py") :returns Int))))''',
        encoding="utf-8",
    )
    for name, value in (("choose", "true"), ("yes", "1"), ("no", "0")):
        (tmp_path / f"{name}.py").write_text(
            "import os\nfrom pathlib import Path\n"
            f'Path("dispatches.txt").open("a", encoding="utf-8").write("{name}\\n")\n'
            f'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("{value}", encoding="utf-8")\n',
            encoding="utf-8",
        )
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(
        json.dumps({name: {"stable_command": ["python", f"{name}.py"], "closure": [f"{name}.py"]}
                    for name in ("choose", "yes", "no")}),
        encoding="utf-8",
    )

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundaries))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["choose", "yes"]
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    return run_root


def _make_committed_branch_unreachable(run_root: Path) -> None:
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo

    authority = load_run_authority(run_root)
    rows = [json.loads(line) for line in authority.memo_path.read_text(encoding="utf-8").splitlines()]
    commits = [row for row in rows if row["record"] == "committed"]
    commits[0]["value"] = False
    rows = [row for row in rows if row["record"] != "terminal"]
    authority.memo_path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert len(snapshot.active_commits) == 2 and snapshot.terminal is None


def test_resume_refuses_commits_made_unreachable_by_checked_inline_value(tmp_path: Path) -> None:
    run_root = _create_completed_branch_run(tmp_path)
    _make_committed_branch_unreachable(run_root)
    before = _snapshot(tmp_path / ".orchestrate")

    resumed = _resume_cli(tmp_path, run_root.name)

    assert resumed.returncode == 2, resumed.stderr
    assert "memo_inconsistent" in resumed.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["choose", "yes"]
    assert _snapshot(tmp_path / ".orchestrate") == before


def _start_pending_yes_branch(tmp_path: Path) -> Path:
    source = tmp_path / "pending-branch.orc"
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule pending-branch) (export run)
          (defworkflow run () -> Int
            (if (command-result choose :argv ("python" "choose.py") :returns Bool)
                (command-result yes :argv ("python" "yes.py") :returns Int)
                0)))''',
        encoding="utf-8",
    )
    (tmp_path / "choose.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text('true', encoding='utf-8')\n"
        "Path('dispatches.txt').open('a', encoding='utf-8').write('choose\\n')\n",
        encoding="utf-8",
    )
    (tmp_path / "yes.py").write_text(
        "import os, time\nfrom pathlib import Path\n"
        "target = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])\n"
        "target.write_text('1', encoding='utf-8')\n"
        "Path('dispatches.txt').open('a', encoding='utf-8').write('yes\\n')\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(json.dumps({name: {
        "stable_command": ["python", f"{name}.py"], "closure": [f"{name}.py"]
    } for name in ("choose", "yes")}), encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "orchestrator", "run", str(source),
         "--command-boundaries-file", str(boundaries)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1]),
             "PYTHONDONTWRITEBYTECODE": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    deadline = time.monotonic() + 15
    marker = tmp_path / "dispatches.txt"
    while time.monotonic() < deadline:
        if marker.exists() and marker.read_text(encoding="utf-8").splitlines() == ["choose", "yes"]:
            assert process.poll() is None
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
            break
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"run exited before pending yes effect: {process.returncode}: "
                f"{stdout.decode(errors='replace')} {stderr.decode(errors='replace')}"
            )
        time.sleep(0.02)
    else:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        raise AssertionError("yes effect did not start")

    run_root = next((tmp_path / ".orchestrate" / "runs").iterdir())
    return run_root


def _make_pending_yes_unreachable(run_root: Path) -> None:
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo

    authority = load_run_authority(run_root)
    memo = authority.memo_path
    rows = [json.loads(line) for line in memo.read_text(encoding="utf-8").splitlines()]
    selector = next(row for row in rows if row["record"] == "committed")
    assert selector["value"] is True
    selector["value"] = False
    memo.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows))
    with memo.open("ab") as stream:
        stream.write(b'{"record":"partial"')
    (run_root / "state.json").write_text('{"status":"stale"}', encoding="utf-8")
    pending = read_memo(memo, site_classes(authority.program))
    assert len(pending.active_commits) == 1
    assert len(pending.pending_starts) == 1
    assert pending.terminal is None
    assert pending.tail is not None


def test_halt_refuses_pending_start_in_branch_made_unreachable_by_checked_inline_value(
    tmp_path: Path,
) -> None:
    run_root = _start_pending_yes_branch(tmp_path)
    _make_pending_yes_unreachable(run_root)
    before = _snapshot(tmp_path / ".orchestrate")

    resumed = _resume_cli(tmp_path, run_root.name)

    assert resumed.returncode == 2, resumed.stderr
    assert "memo_inconsistent" in resumed.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["choose", "yes"]
    assert _snapshot(tmp_path / ".orchestrate") == before
def test_public_pending_retry_uses_pinned_path_after_path_and_bytes_change(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "pinned.orc"
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule pinned) (export run)
          (defworkflow run () -> Int
            (command-result emit :argv ("resume-tool") :returns Int)))''',
        encoding="utf-8",
    )
    first_bin, second_bin = tmp_path / "first-bin", tmp_path / "second-bin"
    first_bin.mkdir()
    second_bin.mkdir()
    pinned = first_bin / "resume-tool"
    pinned.write_text(
        "#!/bin/sh\n"
        "case \"$ORCHESTRATOR_OUTPUT_BUNDLE_PATH\" in *attempt-1*) value=5; stage=first;; *) value=7; stage=retry;; esac\n"
        "printf '%s' \"$value\" > \"$ORCHESTRATOR_OUTPUT_BUNDLE_PATH\"\n"
        "printf '%s:%s\\n' original \"$stage\" >> \"$PWD/dispatches.txt\"\n"
        "case \"$stage\" in first) /bin/sleep 60;; esac\n",
        encoding="utf-8",
    )
    pinned.chmod(0o755)
    alternate = second_bin / "resume-tool"
    alternate.write_text(
        "#!/bin/sh\nprintf '%s' 9 > \"$ORCHESTRATOR_OUTPUT_BUNDLE_PATH\"\n"
        "printf '%s\\n' alternate >> \"$PWD/dispatches.txt\"\n",
        encoding="utf-8",
    )
    alternate.chmod(0o755)
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(json.dumps({"emit": {
        "stable_command": ["resume-tool"], "closure": []
    }}), encoding="utf-8")
    env = _public_env()
    env["PATH"] = str(first_bin) + os.pathsep + env["PATH"]
    _start_and_kill(
        [sys.executable, "-m", "orchestrator", "run", str(source),
         "--command-boundaries-file", str(boundaries)],
        root=tmp_path,
        env=env,
        marker=tmp_path / "dispatches.txt",
    )
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    pinned.write_bytes(pinned.read_bytes() + b"\n# changed pin bytes\n")
    changed_bytes = pinned.read_bytes()
    monkeypatch.setenv("PATH", str(second_bin))
    resumed = _resume_cli(tmp_path, run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    assert "interpreter_changed" in resumed.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == [
        "original:first", "original:retry"
    ]
    rows = [json.loads(line) for line in (run_root / "memo.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["attempt"] for row in rows if row["record"] == "started"] == [1, 2]
    assert rows[-1]["value"] == 7
    assert pinned.read_bytes() == changed_bytes


def test_resume_uses_newer_uncommitted_start_after_invalidation(tmp_path: Path, monkeypatch) -> None:
    import pytest

    import orchestrator.workflow.evaluated.runtime as runtime_module
    import orchestrator.workflow.workspace_files as workspace_files_module
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import invalidate_suffix, memo_writer_lock, read_memo
    from tests.test_workflow_evaluated_command_lifecycle import _InterruptedRun, _publish, _program, _script

    script = _script(tmp_path)
    _source, program = _program(
        tmp_path,
        '(command-result emit :argv ("python" "probe.py") :returns Int)',
        bindings={"emit": "probe.py"},
    )
    with _publish(tmp_path, program) as authority:
        assert runtime_module.execute_pure_run(
            authority, {}, run_id="run-1", workspace=tmp_path
        ) == (0, 5)

    authority = load_run_authority(tmp_path / ".state" / "runs" / "run-1")
    classes = site_classes(program)
    previous = read_memo(authority.memo_path, classes)
    identity = next(iter(previous.active_commits))
    with memo_writer_lock(authority.run_root):
        invalidate_suffix(authority.memo_path, identity, classes)

    real_mkdir = workspace_files_module.WorkspaceFiles.mkdir_exclusive

    def stop_after_started(owner, path):
        if str(path).startswith("effects/"):
            raise _InterruptedRun()
        return real_mkdir(owner, path)

    with monkeypatch.context() as patched:
        patched.setattr(workspace_files_module.WorkspaceFiles, "mkdir_exclusive", stop_after_started)
        with memo_writer_lock(authority.run_root):
            with pytest.raises(_InterruptedRun):
                runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)

    pending = read_memo(authority.memo_path, classes)
    assert not pending.active_commits
    assert pending.latest_starts[identity].data["attempt"] == 2
    assert pending.pending_starts[identity].data["attempt"] == 2
    before = authority.memo_path.read_bytes()
    script.write_text(script.read_text(encoding="utf-8") + "# changed after newer start\n", encoding="utf-8")

    with memo_writer_lock(authority.run_root):
        refused = runtime_module.execute_pure_resume(
            authority, {}, run_id="run-1", workspace=tmp_path
        )

    assert refused == (2, None)
    assert authority.memo_path.read_bytes() == before
    attempt_directory = Path(pending.pending_starts[identity].data["result_path"]).parent
    assert not (authority.run_root / attempt_directory).exists()
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["x"]


def _create_public_failed_terminal_command(tmp_path: Path):
    source = tmp_path / "failed.orc"
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule failed) (export run)
          (defworkflow run () -> Int
            (command-result emit :argv ("python" "probe.py") :returns Int)))''',
        encoding="utf-8",
    )
    package = tmp_path / "support"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    helper = package / "normalize.py"
    helper.write_text("def value():\n    return 5\n", encoding="utf-8")
    (tmp_path / "probe.py").write_text(
        "import os, sys\nfrom pathlib import Path\nfrom support.normalize import value\n"
        "target = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])\n"
        "Path('dispatches.txt').open('a', encoding='utf-8').write(target.parent.name + '\\n')\n"
        "if target.parent.name == 'attempt-1':\n"
        "    Path('support/normalize.py').write_text('def value():\\n    return 6\\n', encoding='utf-8')\n"
        "    sys.exit(9)\n"
        "target.write_text(str(value()), encoding='utf-8')\n",
        encoding="utf-8",
    )
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(json.dumps({"emit": {
        "stable_command": ["python", "probe.py"],
        "closure": ["probe.py", "support/__init__.py", "support/normalize.py"],
    }}), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, "-m", "orchestrator", "run", str(source),
         "--command-boundaries-file", str(boundaries)],
        cwd=tmp_path, env=_public_env(), capture_output=True, text=True, check=False,
    )
    assert run.returncode == 1, run.stderr
    run_root = _run_root(tmp_path)
    memo = run_root / "memo.jsonl"
    return run_root, helper, memo


def _capture_failed_terminal_state(tmp_path: Path, run_root: Path, memo: Path):
    rows = [json.loads(line) for line in memo.read_text(encoding="utf-8").splitlines()]
    assert [row["record"] for row in rows] == ["started", "failed", "terminal"]
    assert rows[-1]["outcome"] == "failed"
    attempt_one = next(run_root.glob("effects/*/attempt-1"))
    old_attempt_evidence = {path.name: path.read_bytes() for path in attempt_one.iterdir()}
    before = _snapshot(tmp_path / ".orchestrate")
    return attempt_one, old_attempt_evidence, before


def _assert_failed_terminal_retry(tmp_path, run_root, memo, helper, attempt_one, old_attempt_evidence):
    helper.write_text("def value():\n    return 5\n", encoding="utf-8")
    retried = _resume_cli(tmp_path, run_root.name)
    assert retried.returncode == 0, retried.stderr
    rows = [json.loads(line) for line in memo.read_text(encoding="utf-8").splitlines()]
    assert [row["attempt"] for row in rows if row["record"] == "started"] == [1, 2]
    assert rows[-1]["outcome"] == "completed"
    assert {path.name: path.read_bytes() for path in attempt_one.iterdir()} == old_attempt_evidence
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == [
        "attempt-1", "attempt-2"
    ]


def test_public_failed_terminal_preflights_changed_command_closure_readonly(tmp_path: Path) -> None:
    run_root, helper, memo = _create_public_failed_terminal_command(tmp_path)
    attempt_one, old_attempt_evidence, before = _capture_failed_terminal_state(
        tmp_path, run_root, memo
    )

    resumed = _resume_cli(tmp_path, run_root.name)

    assert resumed.returncode == 2, resumed.stderr
    assert "effect_input_diverged" in resumed.stderr
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["attempt-1"]
    _assert_failed_terminal_retry(
        tmp_path, run_root, memo, helper, attempt_one, old_attempt_evidence
    )
