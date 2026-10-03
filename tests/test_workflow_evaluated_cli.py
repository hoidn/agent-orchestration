from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.commands.evaluated import bind_program_inputs
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv


PROGRAM = '''\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule evaluated/inputs)
  (export run)
  (defrecord Result (accepted Bool) (score Float))
  (defworkflow run ((score Float) (threshold Float :default 0.5)) -> Result
    (record Result :accepted (> score threshold) :score score)))
'''


def _build(root: Path):
    source = root / "evaluated" / "inputs.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(PROGRAM, encoding="utf-8")
    result = build_closed_program_bundle(
        FrontendBuildRequest(source_path=source, workspace_root=root)
    )
    return source, result.program


def _run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "orchestrator", "run", *arguments],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_input_binding_applies_defaults_and_rejects_bad_inputs(tmp_path: Path) -> None:
    _source, program = _build(tmp_path)

    assert bind_program_inputs(program, {"score": "0.75"}, workspace=tmp_path) == {
        "score": 0.75,
        "threshold": 0.5,
    }
    for invalid in ({}, {"score": "0.75", "extra": "x"}, {"score": "nope"}, {"score": "NaN"}):
        with pytest.raises(ValueError):
            bind_program_inputs(program, invalid, workspace=tmp_path)


def test_public_dry_run_validates_without_run_authority(tmp_path: Path) -> None:
    source, _program = _build(tmp_path)

    result = _run_cli(tmp_path, str(source), "--dry-run", "--input", "score=0.75")

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".orchestrate" / "runs").exists()


@pytest.mark.parametrize(
    "inputs",
    [(), ("score=0.75", "extra=x"), ("score=not-a-float",), ("score=NaN",)],
    ids=["missing", "unknown", "wrong-type", "nonfinite"],
)
def test_public_dry_run_rejects_invalid_inputs_without_run_authority(
    tmp_path: Path, inputs: tuple[str, ...]
) -> None:
    source, _program = _build(tmp_path)
    arguments = [str(source), "--dry-run"]
    for value in inputs:
        arguments.extend(["--input", value])

    result = _run_cli(tmp_path, *arguments)

    assert result.returncode == 2
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_public_pure_run_persists_checked_terminal(tmp_path: Path) -> None:
    source, _program = _build(tmp_path)

    result = _run_cli(tmp_path, str(source), "--input", "score=0.75")

    assert result.returncode == 0, result.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    header = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
    memo_path = run_root / "memo.jsonl"
    snapshot = read_memo(memo_path, {})
    assert header["bound_inputs"] == {"score": 0.75, "threshold": 0.5}
    assert snapshot.terminal is not None
    assert snapshot.terminal.data == {
        "record": "terminal",
        "outcome": "completed",
        "value": {"accepted": True, "score": 0.75},
    }


def test_public_pure_evaluation_failure_persists_failed_terminal(
    tmp_path: Path,
) -> None:
    source = tmp_path / "evaluated" / "failure.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule evaluated/failure) (export run) '
        '(defworkflow run ((divisor Float)) -> Float (/ 1.0 divisor)))\n',
        encoding="utf-8",
    )

    result = _run_cli(tmp_path, str(source), "--input", "divisor=0")

    assert result.returncode == 1
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    assert (run_root / "run.json").is_file()
    snapshot = read_memo(run_root / "memo.jsonl", {})
    assert snapshot.terminal is not None
    assert snapshot.terminal.data["outcome"] == "failed"
    assert snapshot.terminal.data["code"] == "pure_expr_division_by_zero"


def test_public_run_returns_terminal_record_fields_without_an_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _program = _build(tmp_path)
    files = {
        "source": source,
        "source_root": tmp_path,
        "providers": tmp_path / "providers.json",
        "prompts": tmp_path / "prompts.json",
    }
    files["providers"].write_text("{}", encoding="utf-8")
    files["prompts"].write_text("{}", encoding="utf-8")
    args = _run_args(files)
    args.input = ["score=0.75"]
    argv = [*_run_argv(files), "--input", "score=0.75"]
    monkeypatch.chdir(tmp_path)

    with patch.object(sys, "argv", argv):
        result = run_workflow(args)

    assert result.exit_code == 0
    assert result.run_root is not None
    assert result.run_root.parent == tmp_path / ".orchestrate" / "runs"
    assert dict(result.workflow_outputs) == {"accepted": True, "score": 0.75}


def test_public_run_dispatches_command_once_and_commits_typed_result(tmp_path: Path) -> None:
    source = tmp_path / "evaluated" / "command_once.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        """(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule evaluated/command_once) (export run)
          (defrecord Result (ok Bool))
          (defworkflow run () -> Result
            (command-result emit :argv ("python" "probe.py" "emit") :returns Result)))
""",
        encoding="utf-8",
    )
    (tmp_path / "probe.py").write_text(
        r"""import os
from pathlib import Path

with Path("dispatches.txt").open("a", encoding="utf-8") as marker:
    marker.write("emit\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_bytes(b'{"ok":true}')
""",
        encoding="utf-8",
    )
    boundary_file = tmp_path / "command-boundaries.json"
    boundary_file.write_text(json.dumps({"emit": {
        "stable_command": ["python", "probe.py"], "closure": ["probe.py"]
    }}), encoding="utf-8")

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundary_file))

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["emit"]
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    memo_path = run_root / "memo.jsonl"
    raw_rows = [json.loads(line) for line in memo_path.read_text(encoding="utf-8").splitlines()]
    effects = [row for row in raw_rows if row["record"] in {"started", "committed"}]
    snapshot = read_memo(memo_path, {row["identity"]: "command" for row in effects})
    starts = [entry.data for entry in snapshot.entries if entry.data["record"] == "started"]
    commits = [entry.data for entry in snapshot.entries if entry.data["record"] == "committed"]
    assert len(starts) == len(commits) == 1
    assert starts[0]["identity"] == commits[0]["identity"]
    assert starts[0]["attempt"] == commits[0]["attempt"] == 1
    assert commits[0]["effect_class"] == "command"
    assert commits[0]["value"] == {"ok": True}
    result_path = run_root / commits[0]["result_path"]
    assert commits[0]["result_digest"] == "sha256:" + hashlib.sha256(result_path.read_bytes()).hexdigest()
    assert snapshot.terminal is not None
    assert snapshot.terminal.data == {
        "record": "terminal", "outcome": "completed", "value": {"ok": True}
    }


def test_public_run_skips_c4_for_an_unreached_command_branch(tmp_path: Path) -> None:
    source = tmp_path / "evaluated" / "unreached_command.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        """(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule evaluated/unreached_command) (export run)
          (defproc dormant () -> Int :effects ((uses-command sleep)) :lowering inline
            (command-result sleep :argv ("python" "dormant.py") :returns Int))
          (defworkflow run () -> Int
            (let* ((chosen (command-result choose :argv ("python" "choose.py") :returns Int)))
              (if false (dormant) chosen))))
""",
        encoding="utf-8",
    )
    (tmp_path / "choose.py").write_text(
        r"""import os
from pathlib import Path

with Path("dispatches.txt").open("a", encoding="utf-8") as marker:
    marker.write("choose\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("7", encoding="utf-8")
""",
        encoding="utf-8",
    )
    (tmp_path / "dormant.py").write_text(
        r"""import os
from pathlib import Path

with Path("dispatches.txt").open("a", encoding="utf-8") as marker:
    marker.write("dormant\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("8", encoding="utf-8")
""",
        encoding="utf-8",
    )
    boundary_file = tmp_path / "command-boundaries.json"
    boundary_file.write_text(json.dumps({
        "choose": {"stable_command": ["python", "choose.py"], "closure": []},
        "sleep": {"stable_command": ["python", "dormant.py"], "closure": ["."]},
    }), encoding="utf-8")

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundary_file))

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["choose"]
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    memo_path = run_root / "memo.jsonl"
    raw_rows = [json.loads(line) for line in memo_path.read_text(encoding="utf-8").splitlines()]
    effects = [row for row in raw_rows if row["record"] in {"started", "committed"}]
    snapshot = read_memo(memo_path, {row["identity"]: "command" for row in effects})
    assert [entry.data["record"] for entry in snapshot.entries] == [
        "started", "committed", "terminal"
    ]
    assert snapshot.entries[1].data["effect_class"] == "command"
    assert snapshot.entries[1].data["value"] == 7
    assert snapshot.terminal is not None
    assert snapshot.terminal.data["value"] == 7
    assert len(list(run_root.glob("effects/*/attempt-*"))) == 1


def test_public_run_preserves_an_earlier_commit_on_later_local_c4_refusal(tmp_path: Path) -> None:
    source = tmp_path / "evaluated" / "local_c4.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        """(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule evaluated/local_c4) (export run)
          (defworkflow run () -> Int
            (let* ((chosen (command-result choose :argv ("python" "choose.py") :returns Int))
                   (written (command-result writer :argv ("python" "writer.py") :returns Int)))
              written)))
""",
        encoding="utf-8",
    )
    (tmp_path / "choose.py").write_text(
        r"""import os
from pathlib import Path

with Path("dispatches.txt").open("a", encoding="utf-8") as marker:
    marker.write("choose\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("7", encoding="utf-8")
""",
        encoding="utf-8",
    )
    (tmp_path / "writer.py").write_text(
        r"""import os
from pathlib import Path

with Path("dispatches.txt").open("a", encoding="utf-8") as marker:
    marker.write("writer\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("9", encoding="utf-8")
""",
        encoding="utf-8",
    )
    boundary_file = tmp_path / "command-boundaries.json"
    boundary_file.write_text(json.dumps({
        "choose": {"stable_command": ["python", "choose.py"], "closure": []},
        "writer": {"stable_command": ["python", "writer.py"], "closure": ["."]},
    }), encoding="utf-8")

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundary_file))

    assert result.returncode != 0
    assert "[command_closure_unreadable]" in result.stderr
    assert "runtime destination overlaps command closure" in result.stderr
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["choose"]
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    memo_path = run_root / "memo.jsonl"
    raw_rows = [json.loads(line) for line in memo_path.read_text(encoding="utf-8").splitlines()]
    effects = [row for row in raw_rows if row["record"] in {"started", "committed"}]
    snapshot = read_memo(memo_path, {row["identity"]: "command" for row in effects})
    starts = [entry.data for entry in snapshot.entries if entry.data["record"] == "started"]
    commits = [entry.data for entry in snapshot.entries if entry.data["record"] == "committed"]
    assert len(starts) == len(commits) == 1
    assert starts[0]["identity"] == commits[0]["identity"]
    assert commits[0]["effect_class"] == "command"
    assert commits[0]["value"] == 7
    assert [entry.data["record"] for entry in snapshot.entries] == [
        "started", "committed", "terminal"
    ]
    assert snapshot.terminal is not None
    assert snapshot.terminal.data["outcome"] == "failed"
    assert snapshot.terminal.data["code"] == "command_closure_unreadable"
    assert "runtime destination overlaps command closure" in snapshot.terminal.data["message"]
    assert len(list(run_root.glob("effects/*/attempt-*"))) == 1


def test_command_template_loop_index_reaches_each_attempt_argv(tmp_path: Path) -> None:
    source = tmp_path / "evaluated" / "command_loop_index.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        """(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule evaluated/command_loop_index) (export run)
          (defworkflow run () -> Int
            (loop/recur :max 3
              :state (loop-state (i Int 0))
              :on-exhausted 99
              (fn (state)
                (let* ((observed (command-result emit
                    :argv ("python" "probe.py" "${loop.index}") :returns Int)))
                  (if (< state.i 1)
                    (continue (loop-state :like state :i (+ state.i 1)))
                    (done observed)))))))
""",
        encoding="utf-8",
    )
    (tmp_path / "probe.py").write_text(
        r"""import os
import sys
from pathlib import Path

index = sys.argv[1]
with Path("indices.txt").open("a", encoding="utf-8") as marker:
    marker.write(index + "\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(index, encoding="utf-8")
""",
        encoding="utf-8",
    )
    boundary_file = tmp_path / "command-boundaries.json"
    boundary_file.write_text(json.dumps({"emit": {
        "stable_command": ["python", "probe.py"], "closure": ["probe.py"]
    }}), encoding="utf-8")

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundary_file))

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "indices.txt").read_text(encoding="utf-8").splitlines() == ["0", "1"]
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    memo_path = run_root / "memo.jsonl"
    raw_rows = [json.loads(line) for line in memo_path.read_text(encoding="utf-8").splitlines()]
    effects = [row for row in raw_rows if row["record"] in {"started", "committed"}]
    snapshot = read_memo(memo_path, {row["identity"]: "command" for row in effects})
    starts = [entry.data for entry in snapshot.entries if entry.data["record"] == "started"]
    commits = [entry.data for entry in snapshot.entries if entry.data["record"] == "committed"]
    assert len(starts) == len(commits) == 2
    assert all(row["effect_class"] == "command" for row in commits)
    assert [row["value"] for row in commits] == [0, 1]
    assert snapshot.terminal is not None
    assert snapshot.terminal.data["value"] == 1
