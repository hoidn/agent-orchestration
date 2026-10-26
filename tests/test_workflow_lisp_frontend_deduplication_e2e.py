"""Public execution and durable recovery of expanded and abbreviated authoring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

from orchestrator.contracts.closed_program.sites import _ast_nodes
from orchestrator.workflow.evaluated.authority import load_run_authority
from tests.test_workflow_evaluated_resume_retry import _public_env, _start_and_kill
from tests.test_workflow_host_input_e2e import _cli, _run_files, _snapshot


def fixture_source(expanded: bool, fields: tuple[str, str] = ("second", "first")) -> str:
    """Return the portable fixture's authored source for execution and LOC readouts."""
    def command(name: str, result: str, inputs: str = "") -> str:
        argv = f':argv ("python" "tool.py" "{name}") ' if expanded else ""
        return f"(command-result {name} {inputs}{argv}:returns {result})"

    inputs = ":inputs (" + " ".join(f"({name} (produce-{name}))" for name in fields) + ") "
    returns = ":returns Approval " if expanded else ""
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule deduplication) (import std/host :only (HostReply)) (export run)
  (defpath Evidence :kind relpath :under "artifacts" :must-exist true)
  (defenum Approval APPROVED DENIED)
  (defunion Reading (READY (summary String) (evidence Evidence)) (BLOCKED))
  (defprompt approval-question (:fills (summary :text)) -> Approval
    "Approve the verified result: {{summary}}")
  (defproc produce-first () -> Int {command("first", "Int")})
  (defproc produce-second () -> Int {command("second", "Int")})
  (defworkflow run () -> Int
    (match {command("read", "Reading", inputs)}
      ((READY checked)
        (let* ((reply (request-input (approval-question :summary checked.summary)
                       {returns}:show (checked.evidence))))
          (match reply
            ((ANSWERED answer)
              (if (= answer.value Approval.APPROVED)
                {command("write", "Int", ":inputs () ")} 0))
            ((CANCELLED _) 0) ((EXPIRED _) 0))))
      ((BLOCKED _) 0))))
'''


def fixture_manifest(expanded: bool) -> dict:
    """Return equivalent explicit-flat or shared-closure command declarations."""
    commands = {name: {"stable_command": ["python", "tool.py", name],
                       "closure": ["tool.py"], "must_not_repeat": name == "write"}
                for name in ("first", "second", "read", "write")}
    if expanded:
        for row in commands.values():
            row["closure"].append("shared.py")
        return commands
    return {"$schema": "workflow-command-boundaries.v1", "shared_closure": ["shared.py"],
            "commands": commands}


TOOL = '''import json, os, signal, sys
from pathlib import Path
from shared import VALUE

operation = sys.argv[1]
arguments = sys.argv[2:]
document = json.loads(Path(arguments[0]).read_bytes()) if arguments else None
with Path("dispatches.jsonl").open("a") as stream:
    stream.write(json.dumps({"operation": operation, "arguments": arguments,
                             "document": document}) + "\\n")
    stream.flush()
    os.fsync(stream.fileno())
if operation == "write" and os.environ.get("ORCH_DEDUP_HOLD_WRITE"):
    with Path("write-dispatched").open("w") as stream:
        stream.write("dispatched\\n")
        stream.flush()
        os.fsync(stream.fileno())
    while True:
        signal.pause()
result = {"first": 11, "second": 12, "write": VALUE}.get(operation)
if operation == "read":
    result = {"variant": "READY", "summary": "verified-local-result",
              "evidence": "artifacts/evidence.txt"}
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(result))
'''


def _start(root: Path, expanded: bool, fields=("second", "first")) -> Path:
    (root / "deduplication.orc").write_text(fixture_source(expanded, fields), encoding="utf-8")
    (root / "commands.json").write_text(json.dumps(fixture_manifest(expanded)), encoding="utf-8")
    (root / "tool.py").write_text(TOOL, encoding="utf-8")
    (root / "shared.py").write_text("VALUE = 42\n", encoding="utf-8")
    (root / "artifacts").mkdir()
    (root / "artifacts/evidence.txt").write_text("verified evidence\n", encoding="utf-8")
    arguments = [str(root / "deduplication.orc"), "--source-root", str(root),
                 "--command-boundaries-file", str(root / "commands.json")]
    compiled = _cli(root, "compile", *arguments)
    assert compiled.returncode == 0, compiled.stderr
    summary = json.loads(compiled.stdout)
    assert (Path(summary["build_root"]) / "closed_program.json").is_file()
    started = _cli(root, "run", *arguments, "--quiet")
    assert started.returncode == 0, started.stderr
    run_root, = (root / ".orchestrate/runs").iterdir()
    assert [row["operation"] for row in _dispatches(root)] == [*fields, "read"]
    _assert_transports_and_closed_authority(root, run_root, fields)
    return run_root


def _dispatches(root: Path) -> list[dict]:
    return [json.loads(line) for line in (root / "dispatches.jsonl").read_text().splitlines()]


def _assert_transports_and_closed_authority(root: Path, run_root: Path, fields) -> None:
    rows = _dispatches(root)
    assert all(row["arguments"] == [] and row["document"] is None for row in rows[:2])
    assert rows[-1]["document"] == {"first": 11, "second": 12}
    assert len(rows[-1]["arguments"]) == 1
    assert (root / rows[-1]["arguments"][0]).is_relative_to(run_root)
    program = load_run_authority(run_root).program
    bodies = [program.tree["body"], *(item["body"] for item in program.tree["definitions"].values())]
    nodes = [node for body in bodies for node in _ast_nodes(body) if node.get("k") == "perform"]
    commands = {node["boundary"]: node for node in nodes if node["class"] == "command"}
    assert set(commands) == {"first", "second", "read", "write"}
    for name, node in commands.items():
        assert node["command"] == ["python", "tool.py", name]
        assert node["argv"] == []
        assert node["closure"] == [{"base": "workspace", "path": path}
                                   for path in ("shared.py", "tool.py")]
    assert "document" not in commands["first"] and "document" not in commands["second"]
    assert [name for name, _ in commands["read"]["document"]] == list(fields)
    assert commands["write"]["document"] == []
    assert commands["write"]["repeat"] == "never"
    request, = [node for node in nodes if node["class"] == "request_input"]
    assert request["answer"]["kind"] == "enum"
    assert request["answer"]["allowed"] == ["APPROVED", "DENIED"]
    assert request["result"]["kind"] == "union"


def _request(root: Path, run_root: Path) -> dict:
    result = _cli(root, "input", "get", run_root.name)
    assert result.returncode == 0, result.stderr
    request = json.loads(result.stdout)
    shown, = request["show"]
    assert shown["path"] == "artifacts/evidence.txt"
    assert shown["sha256"] == "sha256:" + hashlib.sha256((root / shown["path"]).read_bytes()).hexdigest()
    return request


def _answer(root: Path, run_root: Path, request: dict):
    return _cli(root, "input", "answer", run_root.name, request["request_id"],
                "--by", "operator", "--value", '"APPROVED"')


def _complete(root: Path, run_root: Path) -> None:
    immutable = {name: (run_root / name).read_bytes() for name in ("run.json", "closed_program.json")}
    resumed = _cli(root, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    rows = _dispatches(root)
    assert len(rows) == 4
    assert [row["operation"] for row in rows].count("write") == 1
    assert rows[-1]["operation"] == "write" and rows[-1]["document"] == {}
    assert len(rows[-1]["arguments"]) == 1
    snapshot = _snapshot(run_root)
    assert snapshot.terminal.data == {"record": "terminal", "outcome": "completed", "value": 42}
    reply, = [row.data for row in snapshot.active_commits.values()
              if row.data["effect_class"] == "request_input"]
    assert reply["value"] == {"variant": "ANSWERED", "value": "APPROVED", "by": "operator"}
    assert {name: (run_root / name).read_bytes() for name in immutable} == immutable
    saved = _run_files(run_root)
    dispatches = (root / "dispatches.jsonl").read_bytes()
    replayed = _cli(root, "resume", run_root.name)
    assert replayed.returncode == 0, replayed.stderr
    assert _run_files(run_root) == saved
    assert (root / "dispatches.jsonl").read_bytes() == dispatches


@pytest.mark.parametrize("expanded", [True, False], ids=["expanded", "abbreviated"])
@pytest.mark.parametrize("fields", [("first", "second"), ("second", "first")])
def test_public_approval_and_completed_resume_dispatch_each_command_once(tmp_path, expanded, fields):
    run_root = _start(tmp_path, expanded, fields)
    accepted = _answer(tmp_path, run_root, _request(tmp_path, run_root))
    assert accepted.returncode == 0, accepted.stderr
    assert len(_dispatches(tmp_path)) == 3
    _complete(tmp_path, run_root)


@pytest.mark.parametrize("expanded", [True, False], ids=["expanded", "abbreviated"])
def test_public_answer_refuses_changed_shown_evidence_then_recovers(tmp_path, expanded):
    run_root = _start(tmp_path, expanded)
    request = _request(tmp_path, run_root)
    evidence = tmp_path / "artifacts/evidence.txt"
    original = evidence.read_bytes()
    evidence.write_bytes(b"changed evidence\n")
    saved = _run_files(run_root)
    refused = _answer(tmp_path, run_root, request)
    assert refused.returncode == 2 and "shown_evidence_changed" in refused.stderr
    assert _run_files(run_root) == saved
    assert len(_dispatches(tmp_path)) == 3
    evidence.write_bytes(original)
    accepted = _answer(tmp_path, run_root, request)
    assert accepted.returncode == 0, accepted.stderr
    _complete(tmp_path, run_root)


@pytest.mark.parametrize("expanded", [True, False], ids=["expanded", "abbreviated"])
def test_public_resume_refuses_changed_shared_closure_then_recovers(tmp_path, expanded):
    run_root = _start(tmp_path, expanded)
    accepted = _answer(tmp_path, run_root, _request(tmp_path, run_root))
    assert accepted.returncode == 0, accepted.stderr
    helper = tmp_path / "shared.py"
    original = helper.read_bytes()
    helper.write_bytes(b"VALUE = 99\n")
    saved = _run_files(run_root)
    refused = _cli(tmp_path, "resume", run_root.name)
    assert refused.returncode == 2 and "effect_input_diverged" in refused.stderr
    assert _run_files(run_root) == saved
    assert len(_dispatches(tmp_path)) == 3
    helper.write_bytes(original)
    _complete(tmp_path, run_root)


@pytest.mark.parametrize("expanded", [True, False], ids=["expanded", "abbreviated"])
def test_public_resume_never_repeats_uncertain_write_after_sigkill(tmp_path, expanded):
    run_root = _start(tmp_path, expanded)
    accepted = _answer(tmp_path, run_root, _request(tmp_path, run_root))
    assert accepted.returncode == 0, accepted.stderr
    _start_and_kill([sys.executable, "-B", "-m", "orchestrator", "resume", run_root.name],
                    root=tmp_path, env={**_public_env(), "ORCH_DEDUP_HOLD_WRITE": "1"},
                    marker=tmp_path / "write-dispatched")
    assert [row["operation"] for row in _dispatches(tmp_path)] == ["second", "first", "read", "write"]
    snapshot = _snapshot(run_root)
    assert snapshot.terminal is None
    assert len(snapshot.pending_starts) == 1
    saved = _run_files(run_root)
    refused = _cli(tmp_path, "resume", run_root.name)
    assert refused.returncode == 2 and "lexical_restore_pending_effect_unsafe" in refused.stderr
    assert _run_files(run_root) == saved
    assert len(_dispatches(tmp_path)) == 4
    assert not list(run_root.glob("effects/*/attempt-2"))
