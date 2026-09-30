"""Spike of evaluated execution, iteration 2, item D2: what `orchestrator report` shows, derived from the memo.

Throwaway. The same program (`three_call_sites`) runs on each route in a child process
that is killed by SIGKILL while its second command runs, then resumed to the end. The
flat route's report comes from its `state.json`; the spike's from a view derived from
the memo, the closed program and the attempt files, rendered by the same report
projection (`_state_only_snapshot`). The assertions state what each shows.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from orchestrator.cli.commands.report import _state_only_snapshot
from tests.experiments.test_evaluated_execution_spike import build, fixture, install
from tests.workflow_lisp_totality_matrix_sources import COMMANDS, PROBE

REPO = Path(__file__).resolve().parents[2]
HOLDING_PROBE = PROBE.replace(
    "payload = {",
    'if Path("hold").exists() and n == 2:\n'
    '    Path("marker").write_text("during")\n'
    "    import time\n"
    "    while True:\n"
    "        time.sleep(0.05)\n"
    "payload = {",
    1,
)
ENV = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}


def _killed_while_the_second_command_runs(argv: list[str], root: Path) -> None:
    (root / "hold").write_text("", encoding="utf-8")
    process = subprocess.Popen(argv, cwd=root, env=ENV, start_new_session=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 60
    while not (root / "marker").exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert (root / "marker").exists(), process.communicate()[1][-2000:]
    os.killpg(process.pid, signal.SIGKILL)
    process.communicate()
    (root / "hold").unlink()


def _install(root: Path) -> Path:
    entry = install(root, fixture("three_call_sites"))
    (root / "probe.py").write_text(HOLDING_PROBE, encoding="utf-8")
    return entry


def flat_reports(root: Path) -> tuple[dict, dict]:
    """The flat route's report of the run in progress, then of the finished run."""

    entry = _install(root)
    (root / "providers.json").write_text("{}", encoding="utf-8")
    (root / "prompts.json").write_text("{}", encoding="utf-8")
    boundaries = {name: {"kind": "external_tool", "stable_command": ["python", "probe.py"]} for name in COMMANDS}
    (root / "commands.json").write_text(json.dumps(boundaries), encoding="utf-8")
    run = [sys.executable, "-m", "orchestrator", "run", str(entry), "--entry-workflow", "run", "--source-root", str(root),
           "--provider-externs-file", "providers.json", "--prompt-externs-file", "prompts.json",
           "--command-boundaries-file", "commands.json"]
    _killed_while_the_second_command_runs(run, root)
    run_dir = next((root / ".orchestrate" / "runs").iterdir())
    in_progress = _state_only_snapshot(json.loads((run_dir / "state.json").read_text(encoding="utf-8")), run_dir)
    subprocess.run([sys.executable, "-m", "orchestrator", "resume", run_dir.name], cwd=root, env=ENV, check=True,
                   capture_output=True)
    finished = _state_only_snapshot(json.loads((run_dir / "state.json").read_text(encoding="utf-8")), run_dir)
    return in_progress, finished


def spike_reports(root: Path) -> tuple[dict, dict]:
    """The same projection over the view derived from the spike's memo."""

    from experiments.evaluated_execution_spike.view import derive_state

    program = build(root, fixture("three_call_sites"))
    _install(root)
    (root / "program.json").write_text(program.artifact(), encoding="utf-8")
    run_root = root / ".orchestrate" / "spike" / "run"
    child = [sys.executable, __file__, str(root / "program.json"), str(root), str(run_root)]
    _killed_while_the_second_command_runs(child, root)
    in_progress = _state_only_snapshot(derive_state(program, run_root), run_root)
    subprocess.run(child, cwd=root, env=ENV, check=True, capture_output=True)
    finished = _state_only_snapshot(derive_state(program, run_root), run_root)
    return in_progress, finished


def summary(snapshot: dict) -> dict:
    """What a reader of the report sees: the run's status, its outputs, and each row's status and output."""

    return {
        "status": snapshot["run"]["status"],
        "outputs": snapshot["run"].get("workflow_outputs"),
        "rows": [(step["status"], step["output"]["output_preview"], step["output"]["artifacts"])
                 for step in snapshot["steps"]],
    }


def test_a_view_derived_from_the_memo_shows_what_the_flat_report_shows_and_where_it_differs(tmp_path: Path) -> None:
    flat_in_progress, flat_finished = flat_reports(tmp_path / "flat")
    spike_in_progress, spike_finished = spike_reports(tmp_path / "spike")

    one, two, three = ('{"n": 1}\n', {"n": 1}), ('{"n": 2}\n', {"n": 2}), ('{"n": 3}\n', {"n": 3})
    # In progress, killed. The flat report cannot tell a dead process from a live one; the memo's lock can.
    assert summary(flat_in_progress) == {"status": "running", "outputs": {},
                                         "rows": [("completed", *one), ("running", "", {})]}
    assert summary(spike_in_progress) == {"status": "running", "outputs": None,
                                          "rows": [("completed", *one), ("interrupted", "", {})]}
    # Finished. The flat route has one more row, a pure projection of the result; the spike has none.
    assert summary(flat_finished) == {"status": "completed", "outputs": {"return__n": 6},
                                      "rows": [("completed", *one), ("completed", *two), ("completed", *three),
                                               ("completed", "", {})]}
    assert summary(spike_finished) == {"status": "completed", "outputs": {"return__n": 6},
                                       "rows": [("completed", *one), ("completed", *two), ("completed", *three)]}


if __name__ == "__main__":  # the spike's child: run or resume the program in the workspace
    from experiments.evaluated_execution_spike.evaluator import evaluate
    from experiments.evaluated_execution_spike.sites import ClosedProgram

    program_file, workspace, run_root = map(Path, sys.argv[1:4])
    os.chdir(workspace)
    closed = ClosedProgram.from_artifact(program_file.read_text(encoding="utf-8"))
    evaluate(closed, inputs={}, workspace=workspace, run_root=run_root)
