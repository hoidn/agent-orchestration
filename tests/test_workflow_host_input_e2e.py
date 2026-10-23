"""Public CLI parity for typed, durable diagnose/approval workflows."""

from __future__ import annotations

import json
import hashlib
import ast
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

import pytest

from orchestrator.host_input import answer, cancel, pending
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "workflows" / "examples" / "durable_host_input"
ASSETS = ("approval.orc", "approval.py", "providers.json", "commands.json",
          "stub_provider.py", "action.py")


def _cli(root: Path, *arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", *arguments],
        cwd=root,
        env={**os.environ, "PYTHONPATH": os.pathsep.join((str(root), str(ROOT))),
             "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"], **(env or {})},
        capture_output=True, text=True, check=False,
    )


def _workspace(root: Path) -> tuple[Path, Path]:
    workspace = root / "workspace"
    workspace.mkdir(parents=True)
    for name in ASSETS:
        shutil.copy2(EXAMPLE / name, workspace / name)
    (workspace / "artifacts").mkdir()
    evidence = workspace / "artifacts" / "verification.txt"
    evidence.write_text("verified recovery evidence\n", encoding="utf-8")
    guide = workspace / "docs" / "recovery-policy.md"
    guide.parent.mkdir()
    guide.write_text("Use the verified cause to select a safe recovery.\n", encoding="utf-8")
    binary = workspace / "bin" / "codex"
    binary.parent.mkdir()
    binary.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nimport runpy\nrunpy.run_path('stub_provider.py', run_name='__main__')\n",
                      encoding="utf-8")
    binary.chmod(0o700)
    return workspace, evidence


def _start(workspace: Path, frontend: str, *, clock_env: dict[str, str] | None = None):
    state_dir = workspace / "runs"
    result = _cli(workspace, *_run_args(workspace, frontend, state_dir), env=clock_env)
    assert result.returncode == 0, result.stderr
    run_root, = [path for path in state_dir.iterdir() if path.is_dir()]
    return run_root


def _run_args(workspace: Path, frontend: str, state_dir: Path) -> list[str]:
    common = ["--source-root", str(workspace), "--provider-externs-file", str(workspace / "providers.json"),
              "--command-boundaries-file", str(workspace / "commands.json"),
              "--input", "problem=damaged artifact", "--input", "report=artifacts/verification.txt",
              "--input", "guide=docs/recovery-policy.md",
              "--state-dir", str(state_dir), "--quiet"]
    if frontend == "lisp":
        return ["run", str(workspace / "approval.orc"), *common]
    return ["py", "run", str(workspace / "approval.py"), "--entry-workflow", "recover", *common]


def _snapshot(run_root: Path):
    authority = load_run_authority(run_root)
    return read_memo(authority.memo_path, site_classes(authority.program))


_GATE_SITE = r'''import json, os, signal
from pathlib import Path

stage = os.environ.get("ORCH_HOST_INPUT_GATE")
marker = Path(os.environ["ORCH_HOST_INPUT_MARKER"]) if stage else None

def hold(row):
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps({key: row.get(key) for key in
        ("record", "identity", "attempt", "result_path", "effect_class", "host_request", "host_reply")}))
    os.replace(temporary, marker)
    while True:
        signal.pause()

if stage:
    from orchestrator.workflow.evaluated import views
    publish = views.publish_evaluated_view
    def gated_publish(authority, entry):
        row = entry.data
        targets = ((stage.startswith("started-") and row.get("record") == "started" and row.get("host_request"))
                   or (stage.startswith("action-") and row.get("record") == "started"
                       and not row.get("host_request"))
                   or (stage.startswith("suspended-") and row.get("record") == "suspended")
                   or (stage.startswith("reply-") and row.get("record") == "committed"
                       and row.get("effect_class") == "request_input"
                       and row.get("host_reply", {}).get("origin") == "host"))
        if targets and stage.endswith("-before-view"):
            hold(row)
        result = publish(authority, entry)
        if targets and stage.endswith("-after-view"):
            hold(row)
        return result
    views.publish_evaluated_view = gated_publish

    if stage == "request-views-before-suspension" or stage == "reply-after-request-view":
        from orchestrator.workflow.evaluated import host_input
        publish_requests = host_input._publish_request_views
        def gated_request_views(authority, started, commit=None):
            result = publish_requests(authority, started, commit)
            if stage == "request-views-before-suspension" and commit is None:
                hold(started.data)
            if stage == "reply-after-request-view" and commit is not None:
                hold(commit.data)
            return result
        host_input._publish_request_views = gated_request_views

    if stage == "reply-torn":
        from orchestrator.workflow.evaluated import memo
        write = memo.os.write
        def gated_write(fd, data):
            raw = bytes(data)
            try:
                row = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                row = {}
            if row.get("record") == "committed" and row.get("effect_class") == "request_input":
                written = write(fd, raw[:max(1, len(raw) // 2)])
                hold(row)
                return written
            return write(fd, data)
        memo.os.write = gated_write
'''


def _kill_at_gate(workspace: Path, args: list[str], stage: str) -> dict:
    marker = workspace / "host-input-gate.json"
    (workspace / "sitecustomize.py").write_text(_GATE_SITE, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(workspace), str(ROOT))),
           "PATH": str(workspace / "bin") + os.pathsep + os.environ["PATH"],
           "ORCH_HOST_INPUT_GATE": stage, "ORCH_HOST_INPUT_MARKER": str(marker)}
    process = subprocess.Popen(
        [sys.executable, "-B", "-m", "orchestrator", *args],
        cwd=workspace, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 30
        while process.poll() is None and not marker.is_file() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not marker.is_file():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"{stage} gate was not reached: {stdout}\n{stderr}")
        row = json.loads(marker.read_text(encoding="utf-8"))
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == -signal.SIGKILL, (stdout, stderr)
        return row
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def _start_lock_owner(workspace: Path, run_root: Path) -> subprocess.Popen[str]:
    marker = workspace / "writer-held.json"
    script = workspace / "hold_writer.py"
    script.write_text(
        "import os, signal\n"
        "from pathlib import Path\n"
        "from orchestrator.workflow.evaluated.memo import memo_writer_lock\n"
        "root = Path(os.environ['ORCH_LOCK_RUN_ROOT'])\n"
        "marker = Path(os.environ['ORCH_LOCK_MARKER'])\n"
        "with memo_writer_lock(root):\n"
        "    temporary = marker.with_suffix('.tmp')\n"
        "    temporary.write_text('locked')\n"
        "    os.replace(temporary, marker)\n"
        "    while True:\n"
        "        signal.pause()\n",
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(workspace), str(ROOT))),
           "ORCH_LOCK_RUN_ROOT": str(run_root), "ORCH_LOCK_MARKER": str(marker)}
    process = subprocess.Popen([sys.executable, "-B", str(script)], cwd=workspace, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               start_new_session=True)
    try:
        deadline = time.monotonic() + 15
        while process.poll() is None and not marker.is_file() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not marker.is_file():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"writer lock owner did not acquire the run lock: {stdout}\n{stderr}")
        assert marker.read_text(encoding="utf-8") == "locked"
        return process
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        raise


def _stop_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == -signal.SIGKILL, (stdout, stderr)


def _run_files(run_root: Path) -> dict[str, bytes]:
    return {path.relative_to(run_root).as_posix(): path.read_bytes()
            for path in run_root.rglob("*") if path.is_file()
            and path.name not in {"run.lock", "workspace.lock", "workspace.guard"}}


def _clock(workspace: Path) -> tuple[Path, dict[str, str]]:
    clock_file = workspace / "test-clock.txt"
    clock_file.write_text("100.0", encoding="utf-8")
    (workspace / "sitecustomize.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "from types import SimpleNamespace\n"
        "if os.environ.get('ORCH_TEST_CLOCK_FILE'):\n"
        "    from orchestrator.workflow.evaluated import host_input\n"
        "    clock_path = Path(os.environ['ORCH_TEST_CLOCK_FILE'])\n"
        "    host_input.time = SimpleNamespace(time=lambda: float(clock_path.read_text()))\n",
        encoding="utf-8",
    )
    return clock_file, {"ORCH_TEST_CLOCK_FILE": str(clock_file)}


@pytest.mark.parametrize("frontend", ["lisp", "python"])
@pytest.mark.parametrize("outcome", ["APPROVED", "DENIED", "CANCELLED", "EXPIRED"])
def test_public_cli_workflows_recover_typed_outcomes_once(tmp_path, frontend, outcome):
    workspace, evidence = _workspace(tmp_path)
    clock_env = None
    clock_file = None
    if outcome == "EXPIRED":
        clock_file, clock_env = _clock(workspace)
    run_root = _start(workspace, frontend, clock_env=clock_env)

    if outcome == "APPROVED":
        request = pending(run_root)
    else:
        result = _cli(workspace, "input", "get", run_root.name, "--state-dir", str(run_root.parent),
                      env=clock_env)
        assert result.returncode == 0, result.stderr
        request = json.loads(result.stdout)
    assert request is not None
    commits = [row.data for row in _snapshot(run_root).entries if row.data.get("record") == "committed"]
    verification, = [row for row in commits if row["value"].get("evidence")]
    assert verification["value"]["summary"] in request["question"]
    assert verification["value"]["cause"] in request["question"]
    assert request["show"][0]["path"] == verification["value"]["evidence"]
    assert request["show"][0]["path"] == "artifacts/verification.txt"
    assert request["show"][0]["sha256"]
    assert evidence.read_text(encoding="utf-8").strip() == "verified recovery evidence"
    provider_rows = [json.loads(line) for line in (workspace / "providers.log").read_text().splitlines()]
    assert len(provider_rows) == 1 and provider_rows[0]["summary"] == f"diagnosis-for:{provider_rows[0]['identity']}"
    assert provider_rows[0]["cause"] in {"BROKEN_RECORD", "MISSING_METADATA"}
    commands = [json.loads(line) for line in (workspace / "commands.log").read_text().splitlines()]
    assert [row["operation"] for row in commands] == ["verify"]

    if outcome == "APPROVED":
        settled = _cli(workspace, "input", "answer", run_root.name, request["request_id"],
                       "--state-dir", str(run_root.parent), "--by", "operator", "--value", '"APPROVED"')
        assert settled.returncode == 0, settled.stderr
    elif outcome == "DENIED":
        answer(run_root, request["request_id"], "DENIED", by="operator", workspace=workspace)
    elif outcome == "CANCELLED":
        cancel(run_root, request["request_id"], by="operator", workspace=workspace)
    else:
        assert request["deadline_elapsed"] is False
        assert clock_file is not None
        clock_file.write_text(str(request["deadline"]), encoding="utf-8")
    assert [json.loads(line)["operation"] for line in (workspace / "commands.log").read_text().splitlines()] == ["verify"]

    for _ in range(2):
        resumed = _cli(workspace, "resume", run_root.name, "--state-dir", str(run_root.parent), env=clock_env)
        assert resumed.returncode == 0, resumed.stderr
    snapshot = _snapshot(run_root)
    assert snapshot.terminal is not None
    expected_status = "repaired" if outcome == "APPROVED" else "escalated"
    assert snapshot.terminal.data["value"]["status"] == expected_status
    expected_reason = "" if outcome == "APPROVED" else outcome.lower()
    assert snapshot.terminal.data["value"]["reason"] == expected_reason
    assert snapshot.terminal.data["value"]["cause"] == verification["value"]["cause"]
    commands = [json.loads(line) for line in (workspace / "commands.log").read_text().splitlines()]
    expected_action = "repair" if outcome == "APPROVED" else "escalate"
    assert [row["operation"] for row in commands] == ["verify", expected_action]
    assert commands[-1]["arguments"][0] == verification["value"]["cause"] if outcome == "APPROVED" else commands[-1]["arguments"][1] == verification["value"]["cause"]
    assert len((workspace / "providers.log").read_text().splitlines()) == 1
    settled, = [row for row in snapshot.entries if row.data.get("effect_class") == "request_input"]
    assert settled.data["host_reply"]["request_id"] == request["request_id"]
    if outcome in {"APPROVED", "DENIED"}:
        assert settled.data["value"] == {"variant": "ANSWERED", "by": "operator", "value": outcome}
        assert settled.data["host_reply"]["origin"] == "host"
    elif outcome == "CANCELLED":
        assert settled.data["value"] == {"variant": "CANCELLED", "by": "operator"}
        assert settled.data["host_reply"]["origin"] == "host"
    else:
        assert settled.data["value"] == {"variant": "EXPIRED"}
        assert settled.data["host_reply"]["origin"] == "runtime"
        assert settled.data["time"] == request["deadline"]
    assert isinstance(settled.data["time"], (int, float))
    header = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
    assert header["workflow_file"].endswith(".orc")
    assert (workspace / header["workflow_file"]).is_file()
    if frontend == "python":
        assert ".orchestrate/python/" in header["workflow_file"]
        generated = workspace / header["workflow_file"]
        source_map = json.loads((generated.parents[2] / "source-map.json").read_text())
        assert source_map["source_hashes"][str(workspace / "approval.py")] == "sha256:" + hashlib.sha256((workspace / "approval.py").read_bytes()).hexdigest()
        recover = next(node for node in ast.parse((workspace / "approval.py").read_text()).body
                       if isinstance(node, ast.FunctionDef) and node.name == "recover")
        recover_line = min(recover.lineno, *(decorator.lineno for decorator in recover.decorator_list))
        assert any(row["kind"] == "definition" and row["python"]["path"] == str(workspace / "approval.py")
                   and row["python"]["line"] == recover_line
                   and row["generated"]["path"] == generated.relative_to(generated.parents[2]).as_posix()
                   for row in source_map["entries"])


def test_loop_visits_and_procedure_activations_keep_separate_request_ids(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "visits.orc"
    source.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule visits) (import std/host :only (HostReply)) (export recover)
      (defenum Approval APPROVED DENIED)
      (defprompt visit-question (:fills (number :value Int) (checkpoint :text)) -> Approval
        "Approve visit {number} at the {checkpoint} checkpoint?")
      (defproc ask ((number Int) (checkpoint String)) -> HostReply[Approval]
        (request-input (visit-question :number number :checkpoint checkpoint) :returns Approval))
      (defworkflow recover () -> Int
        (loop/recur :max 2 :state (loop-state (number Int 0)) :on-exhausted 99
          (fn (state)
            (let* ((first (ask state.number "first")))
              (match first
                ((ANSWERED _)
                  (let* ((second (ask state.number "second")))
                    (match second
                      ((ANSWERED answer)
                        (if (= answer.value Approval.APPROVED)
                          (if (= state.number 0)
                            (continue (loop-state :like state :number 1))
                            (done 42))
                          (done 0)))
                      ((CANCELLED _) (done 1))
                      ((EXPIRED _) (done 2)))))
                ((CANCELLED _) (done 1))
                ((EXPIRED _) (done 2))))))))''', encoding="utf-8")
    state_dir = workspace / "runs"
    started = _cli(workspace, "run", str(source), "--source-root", str(workspace),
                   "--state-dir", str(state_dir), "--quiet")
    assert started.returncode == 0, started.stderr
    run_root, = [path for path in state_dir.iterdir() if path.is_dir()]
    first = pending(run_root)
    assert first is not None
    assert source.read_text(encoding="utf-8").count("(request-input") == 1
    observed = []
    for index in range(4):
        request = pending(run_root)
        assert request is not None
        assert request["request_id"] not in {row["request_id"] for row in observed[:index]}
        assert request["identity"] not in {row["identity"] for row in observed[:index]}
        if index == 0:
            for _ in range(2):
                resumed = _cli(workspace, "resume", run_root.name, "--state-dir", str(state_dir))
                assert resumed.returncode == 0, resumed.stderr
            repeated = pending(run_root)
            assert repeated["request_id"] == request["request_id"]
            assert repeated["identity"] == request["identity"]
        accepted = _cli(workspace, "input", "answer", run_root.name, request["request_id"],
                        "--state-dir", str(state_dir), "--by", "operator", "--value", '"APPROVED"')
        assert accepted.returncode == 0, accepted.stderr
        resumed = _cli(workspace, "resume", run_root.name, "--state-dir", str(state_dir))
        assert resumed.returncode == 0, resumed.stderr
        observed.append(request)

    snapshot = _snapshot(run_root)
    assert snapshot.terminal.data["value"] == 42
    requests = [row.data for row in snapshot.entries if row.data.get("effect_class") == "request_input"]
    assert len(requests) == 4
    assert [row["host_reply"]["request_id"] for row in requests] == [row["request_id"] for row in observed]
    starts = [row.data for row in snapshot.entries if row.data.get("host_request")]
    assert [(row["host_request"]["request_id"], row["identity"]) for row in starts] == [
        (request["request_id"], request["identity"]) for request in observed]
    assert len({request["request_id"] for request in observed}) == 4
    assert len({request["identity"] for request in observed}) == 4


def test_imported_same_memo_workflow_and_procedure_calls_suspend_and_settle(tmp_path):
    workspace = tmp_path / "workspace"
    helper = workspace / "host" / "helper.orc"
    helper.parent.mkdir(parents=True)
    helper.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/helper) (import std/host :only (HostReply)) (export Approval ask run)
      (defenum Approval APPROVED DENIED)
      (defproc ask ((question String)) -> HostReply[Approval]
        (request-input question :returns Approval))
      (defworkflow run ((question String)) -> HostReply[Approval] (ask question)))''', encoding="utf-8")
    entry = workspace / "host" / "entry.orc"
    entry.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply))
      (import host/helper :as helper :only (Approval ask run)) (export run)
      (defworkflow run () -> HostReply[helper.Approval]
        (let* ((first (helper.ask "First callsite")))
          (call helper.run :question "Second callsite"))))''', encoding="utf-8")
    state_dir = workspace / "runs"
    started = _cli(workspace, "run", str(entry), "--source-root", str(workspace),
                   "--state-dir", str(state_dir), "--quiet")
    assert started.returncode == 0, started.stderr
    run_root, = [path for path in state_dir.iterdir() if path.is_dir()]
    first = pending(run_root)
    assert first is not None
    for _ in range(2):
        resumed = _cli(workspace, "resume", run_root.name, "--state-dir", str(state_dir))
        assert resumed.returncode == 0, resumed.stderr
    same = pending(run_root)
    assert same["request_id"] == first["request_id"] and same["identity"] == first["identity"]
    accepted = _cli(workspace, "input", "answer", run_root.name, first["request_id"],
                    "--state-dir", str(state_dir), "--by", "operator", "--value", '"APPROVED"')
    assert accepted.returncode == 0, accepted.stderr
    resumed = _cli(workspace, "resume", run_root.name, "--state-dir", str(state_dir))
    assert resumed.returncode == 0, resumed.stderr
    second = pending(run_root)
    assert second is not None
    assert second["request_id"] != first["request_id"]
    assert second["identity"] != first["identity"]
    answer(run_root, second["request_id"], "APPROVED", by="operator", workspace=workspace)
    for _ in range(2):
        resumed = _cli(workspace, "resume", run_root.name, "--state-dir", str(state_dir))
        assert resumed.returncode == 0, resumed.stderr

    snapshot = _snapshot(run_root)
    assert snapshot.terminal is not None
    requests = [row.data for row in snapshot.entries if row.data.get("effect_class") == "request_input"]
    assert len(requests) == 2
    assert [row["host_reply"]["request_id"] for row in requests] == [first["request_id"], second["request_id"]]
    starts = [row.data for row in snapshot.entries if row.data.get("host_request")]
    assert [(row["host_request"]["request_id"], row["identity"]) for row in starts] == [
        (first["request_id"], first["identity"]), (second["request_id"], second["identity"])]


def test_parallel_command_batches_can_surround_a_serial_host_request(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "parallel.orc"
    source.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule parallel) (import std/host :only (HostReply)) (export run)
      (defenum Approval APPROVED DENIED)
      (defworkflow run () -> Int
        (let* ((before (list/map-effect ((item (list "a" "b"))) :max 2 :parallel 2 :workspace item
                             (command-result note :argv ("python" SCRIPT "before" item) :returns Int)))
               (reply (request-input "Approve between parallel batches?" :returns Approval)))
          (match reply
            ((ANSWERED answer)
              (if (= answer.value Approval.APPROVED)
                    (let* ((after (list/map-effect ((item (list "a" "b"))) :max 2 :parallel 2 :workspace item
                                        (command-result note :argv ("python" SCRIPT "after" item) :returns Int))))
                  (list/length after))
                0))
            ((CANCELLED _) 1)
            ((EXPIRED _) 2)))))''', encoding="utf-8")
    (workspace / "parallel_note.py").write_text('''import json, os, sys
from pathlib import Path
phase, item = sys.argv[1:]
root = Path(os.environ["ORCHESTRATOR_WORKSPACE_ROOT"])
with (root / "parallel.log").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"phase": phase, "item": item}, sort_keys=True) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("1")
''', encoding="utf-8")
    source.write_text(source.read_text(encoding="utf-8").replace(
        "SCRIPT", json.dumps(str(workspace / "parallel_note.py"))), encoding="utf-8")
    (workspace / "a").mkdir()
    (workspace / "b").mkdir()
    boundaries = workspace / "commands.json"
    boundaries.write_text(json.dumps({"note": {"stable_command": ["python", str(workspace / "parallel_note.py")],
                                        "closure": ["parallel_note.py"]}}), encoding="utf-8")
    state_dir = workspace / "runs"
    started = _cli(workspace, "run", str(source), "--source-root", str(workspace),
                   "--command-boundaries-file", str(boundaries), "--state-dir", str(state_dir), "--quiet")
    assert started.returncode == 0, started.stderr
    run_root, = [path for path in state_dir.iterdir() if path.is_dir()]
    request = pending(run_root)
    assert request is not None
    before = [json.loads(line) for line in (workspace / "parallel.log").read_text().splitlines()]
    assert sorted((row["phase"], row["item"]) for row in before) == [("before", "a"), ("before", "b")]
    before_memo = _snapshot(run_root)
    request_start, = [row for row in before_memo.entries if row.data.get("host_request")]
    assert all(row.data["record"] == "committed" and row.offset < request_start.offset
               for row in before_memo.entries if row.data.get("effect_class") == "command")

    accepted = _cli(workspace, "input", "answer", run_root.name, request["request_id"],
                    "--state-dir", str(state_dir), "--by", "operator", "--value", '"APPROVED"')
    assert accepted.returncode == 0, accepted.stderr
    for _ in range(2):
        resumed = _cli(workspace, "resume", run_root.name, "--state-dir", str(state_dir))
        assert resumed.returncode == 0, resumed.stderr
    assert _snapshot(run_root).terminal.data["value"] == 2
    all_rows = [json.loads(line) for line in (workspace / "parallel.log").read_text().splitlines()]
    assert sorted((row["phase"], row["item"]) for row in all_rows) == [
        ("after", "a"), ("after", "b"), ("before", "a"), ("before", "b")]
    assert len(all_rows) == 4


@pytest.mark.parametrize("frontend", ["lisp", "python"])
@pytest.mark.parametrize("changed_path", ["guide", "shown-evidence"])
def test_runtime_doc_and_shown_evidence_drift_remain_separate(tmp_path, frontend, changed_path):
    workspace, _ = _workspace(tmp_path)
    run_root = _start(workspace, frontend)
    request = pending(run_root)
    assert request is not None
    if changed_path == "guide":
        path = workspace / "docs" / "recovery-policy.md"
        expected_code = "effect_input_diverged"
    else:
        path = workspace / "artifacts" / "verification.txt"
        expected_code = "shown_evidence_changed"
    path.write_text("changed after the request was frozen\n", encoding="utf-8")
    before = (run_root / "memo.jsonl").read_bytes()

    result = _cli(workspace, "input", "answer", run_root.name, request["request_id"],
                  "--state-dir", str(run_root.parent), "--by", "operator", "--value", '"APPROVED"')

    assert result.returncode == 2
    assert expected_code in result.stderr
    assert (run_root / "memo.jsonl").read_bytes() == before
    assert [json.loads(line)["operation"] for line in (workspace / "commands.log").read_text().splitlines()] == ["verify"]


@pytest.mark.parametrize("stage", [
    "started-before-view",
    "started-after-view",
    "request-views-before-suspension",
    "suspended-before-view",
    "suspended-after-view",
])
def test_sigkill_around_durable_host_start_and_suspension_recovers_same_attempt(tmp_path, stage):
    workspace, _ = _workspace(tmp_path)
    state_dir = workspace / "runs"
    gated_request = _kill_at_gate(workspace, _run_args(workspace, "lisp", state_dir), stage)
    run_root, = [path for path in state_dir.iterdir() if path.is_dir()]
    before = _snapshot(run_root)
    started, = [row.data for row in before.entries if row.data.get("host_request")]
    request_id = started["host_request"]["request_id"]
    if gated_request["record"] == "started":
        assert request_id == gated_request["host_request"]["request_id"]
    else:
        assert gated_request["record"] == "suspended"
    assert started["identity"] == gated_request["identity"]
    assert started["attempt"] == gated_request["attempt"] == 1
    attempt_dir = (run_root / started["result_path"]).parent
    if stage in {"started-before-view", "started-after-view"}:
        assert not attempt_dir.exists()
    else:
        assert attempt_dir.is_dir()
    memo_length = len((run_root / "memo.jsonl").read_bytes())
    state_offset = json.loads((run_root / "state.json").read_text())["memo_offset"]
    if stage.endswith("before-view"):
        assert state_offset < memo_length
    else:
        assert state_offset == memo_length

    recovered = _cli(workspace, "resume", run_root.name, "--state-dir", str(state_dir))
    assert recovered.returncode == 0, recovered.stderr
    request = pending(run_root)
    assert request["request_id"] == request_id
    assert request["identity"] == gated_request["identity"]
    assert request["attempt"] == 1
    assert len((workspace / "providers.log").read_text().splitlines()) == 1
    assert [json.loads(line)["operation"] for line in (workspace / "commands.log").read_text().splitlines()] == ["verify"]

    answer(run_root, request["request_id"], "APPROVED", by="operator", workspace=workspace)
    for _ in range(2):
        resumed = _cli(workspace, "resume", run_root.name, "--state-dir", str(state_dir))
        assert resumed.returncode == 0, resumed.stderr
    assert _snapshot(run_root).terminal.data["value"]["status"] == "repaired"
    assert [json.loads(line)["operation"] for line in (workspace / "commands.log").read_text().splitlines()] == ["verify", "repair"]


@pytest.mark.parametrize("stage", [
    "reply-torn",
    "reply-before-view",
    "reply-after-view",
    "reply-after-request-view",
])
def test_sigkill_during_reply_append_or_view_recovers_single_settlement(tmp_path, stage):
    workspace, _ = _workspace(tmp_path)
    run_root = _start(workspace, "lisp")
    request = pending(run_root)
    assert request is not None
    answer_args = ["input", "answer", run_root.name, request["request_id"],
                   "--state-dir", str(run_root.parent), "--by", "operator", "--value", '"APPROVED"']

    gated_reply = _kill_at_gate(workspace, answer_args, stage)
    memo_path = run_root / "memo.jsonl"
    attempt_dir = (run_root / request["result_path"]).parent
    snapshot = _snapshot(run_root)
    reply_rows = [row.data for row in snapshot.entries if row.data.get("effect_class") == "request_input"]

    if stage == "reply-torn":
        assert snapshot.tail
        assert reply_rows == []
        assert gated_reply["host_reply"]["request_id"] == request["request_id"]
        before_pending = memo_path.read_bytes()
        assert pending(run_root)["request_id"] == request["request_id"]
        assert memo_path.read_bytes() == before_pending
        answer(run_root, request["request_id"], "APPROVED", by="operator", workspace=workspace)
    else:
        assert not snapshot.tail
        assert len(reply_rows) == 1
        assert reply_rows[0]["host_reply"]["request_id"] == request["request_id"]
        memo_length = len(memo_path.read_bytes())
        state_offset = json.loads((run_root / "state.json").read_text())["memo_offset"]
        if stage == "reply-before-view":
            assert state_offset < memo_length
        else:
            assert state_offset == memo_length
        reply_view = attempt_dir / "reply.json"
        assert reply_view.exists() is (stage == "reply-after-request-view")
        assert pending(run_root) is None

    assert [json.loads(line)["operation"] for line in (workspace / "commands.log").read_text().splitlines()] == ["verify"]
    resumed = _cli(workspace, "resume", run_root.name, "--state-dir", str(run_root.parent))
    assert resumed.returncode == 0, resumed.stderr
    assert _snapshot(run_root).terminal.data["value"]["status"] == "repaired"
    committed = [row.data for row in _snapshot(run_root).entries if row.data.get("effect_class") == "request_input"]
    assert len(committed) == 1
    assert committed[0]["host_reply"]["request_id"] == request["request_id"]
    assert committed[0]["host_reply"]["origin"] == "host"
    assert [json.loads(line)["operation"] for line in (workspace / "commands.log").read_text().splitlines()] == ["verify", "repair"]
    assert len((workspace / "providers.log").read_text().splitlines()) == 1
    after_completion = memo_path.read_bytes()
    resumed_again = _cli(workspace, "resume", run_root.name, "--state-dir", str(run_root.parent))
    assert resumed_again.returncode == 0, resumed_again.stderr
    assert memo_path.read_bytes() == after_completion


def test_sigkill_while_resume_consumes_settled_reply_does_not_redispatch(tmp_path):
    workspace, _ = _workspace(tmp_path)
    run_root = _start(workspace, "lisp")
    request = pending(run_root)
    assert request is not None
    answer(run_root, request["request_id"], "APPROVED", by="operator", workspace=workspace)

    gated_action = _kill_at_gate(
        workspace, ["resume", run_root.name, "--state-dir", str(run_root.parent)], "action-before-view"
    )
    assert gated_action["record"] == "started"
    assert gated_action["effect_class"] is None
    assert gated_action["host_request"] is None
    snapshot = _snapshot(run_root)
    settlements = [row.data for row in snapshot.entries if row.data.get("effect_class") == "request_input"]
    assert len(settlements) == 1
    assert settlements[0]["host_reply"]["request_id"] == request["request_id"]
    assert settlements[0]["value"] == {"variant": "ANSWERED", "by": "operator", "value": "APPROVED"}
    action_start, = [row.data for row in snapshot.entries
                     if row.data.get("record") == "started" and row.data.get("identity") == gated_action["identity"]
                     and not row.data.get("host_request")]
    assert action_start["identity"] == gated_action["identity"]
    assert not (run_root / action_start["result_path"]).parent.exists()
    assert json.loads((run_root / "state.json").read_text())["memo_offset"] < len((run_root / "memo.jsonl").read_bytes())
    assert len((workspace / "providers.log").read_text().splitlines()) == 1
    assert [json.loads(line)["operation"] for line in (workspace / "commands.log").read_text().splitlines()] == ["verify"]

    resumed = _cli(workspace, "resume", run_root.name, "--state-dir", str(run_root.parent))
    assert resumed.returncode == 0, resumed.stderr
    assert _snapshot(run_root).terminal.data["value"]["status"] == "repaired"
    settled_after = [row.data for row in _snapshot(run_root).entries if row.data.get("effect_class") == "request_input"]
    action_commit = next(row.data for row in _snapshot(run_root).entries
                         if row.data.get("identity") == gated_action["identity"]
                         and row.data.get("effect_class") == "command")
    assert action_commit["value"]["status"] == "repaired"
    assert len(settled_after) == 1
    assert settled_after[0]["host_reply"]["request_id"] == request["request_id"]
    assert len((workspace / "providers.log").read_text().splitlines()) == 1
    assert [json.loads(line)["operation"] for line in (workspace / "commands.log").read_text().splitlines()] == ["verify", "repair"]
    complete_memo = (run_root / "memo.jsonl").read_bytes()
    repeated = _cli(workspace, "resume", run_root.name, "--state-dir", str(run_root.parent))
    assert repeated.returncode == 0, repeated.stderr
    assert (run_root / "memo.jsonl").read_bytes() == complete_memo


def test_separate_writer_lock_and_exact_deadline_owner_races(tmp_path):
    workspace, _ = _workspace(tmp_path)
    clock_file, clock_env = _clock(workspace)
    run_root = _start(workspace, "lisp", clock_env=clock_env)
    request = pending(run_root)
    assert request is not None
    answer_args = ["input", "answer", run_root.name, request["request_id"],
                   "--state-dir", str(run_root.parent), "--by", "operator", "--value", '"APPROVED"']
    clock_file.write_text(str(request["deadline"]), encoding="utf-8")

    owner = _start_lock_owner(workspace, run_root)
    try:
        before = _run_files(run_root)
        blocked = _cli(workspace, *answer_args, env=clock_env)
        assert blocked.returncode == 2
        assert "memo_busy" in blocked.stderr
        assert _run_files(run_root) == before
    finally:
        _stop_process_group(owner)

    before = _run_files(run_root)
    expired_answer = _cli(workspace, *answer_args, env=clock_env)
    assert expired_answer.returncode == 2
    assert "host_input_deadline_elapsed" in expired_answer.stderr
    assert _run_files(run_root) == before
    resumed = _cli(workspace, "resume", run_root.name, "--state-dir", str(run_root.parent), env=clock_env)
    assert resumed.returncode == 0, resumed.stderr
    expired, = [row.data for row in _snapshot(run_root).entries if row.data.get("effect_class") == "request_input"]
    assert expired["value"] == {"variant": "EXPIRED"}
    assert expired["host_reply"]["origin"] == "runtime"
    assert expired["time"] == request["deadline"]
    after_expiration = _run_files(run_root)
    late_answer = _cli(workspace, "input", "answer", run_root.name, request["request_id"],
                       "--state-dir", str(run_root.parent), "--by", "late-operator", "--value", '"APPROVED"',
                       env=clock_env)
    assert late_answer.returncode == 2
    assert "request_already_settled" in late_answer.stderr
    assert _run_files(run_root) == after_expiration
    late_cancel = _cli(workspace, "input", "cancel", run_root.name, request["request_id"],
                       "--state-dir", str(run_root.parent), "--by", "late-operator", env=clock_env)
    assert late_cancel.returncode == 2
    assert "request_already_settled" in late_cancel.stderr
    assert _run_files(run_root) == after_expiration

    later, _ = _workspace(tmp_path / "answer-wins")
    later_clock, later_env = _clock(later)
    answer_run = _start(later, "lisp", clock_env=later_env)
    answer_request = pending(answer_run)
    assert answer_request is not None
    later_clock.write_text(str(answer_request["deadline"] - 1), encoding="utf-8")
    accepted = _cli(later, "input", "answer", answer_run.name, answer_request["request_id"],
                    "--state-dir", str(answer_run.parent), "--by", "operator", "--value", '"APPROVED"',
                    env=later_env)
    assert accepted.returncode == 0, accepted.stderr
    later_clock.write_text(str(answer_request["deadline"]), encoding="utf-8")
    completed = _cli(later, "resume", answer_run.name, "--state-dir", str(answer_run.parent), env=later_env)
    assert completed.returncode == 0, completed.stderr
    answer_commit, = [row.data for row in _snapshot(answer_run).entries
                      if row.data.get("effect_class") == "request_input"]
    assert answer_commit["value"] == {"variant": "ANSWERED", "by": "operator", "value": "APPROVED"}
    assert answer_commit["host_reply"]["origin"] == "host"
    assert answer_commit["time"] == answer_request["deadline"] - 1
    assert _snapshot(answer_run).terminal.data["value"]["status"] == "repaired"
    assert [json.loads(line)["operation"] for line in (later / "commands.log").read_text().splitlines()] == ["verify", "repair"]
