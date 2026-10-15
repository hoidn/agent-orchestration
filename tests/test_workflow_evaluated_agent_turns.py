"""Two agents, four typed turns: distinct native identities, predecessor lineage, exactly four dispatches."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_invalidate import _cli

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Draft (text String)) (defrecord Feedback (notes List[String]))
  (defprompt draft (:fills (task :text)) -> Draft "Draft: {task}")
  (defprompt review (:fills (text :text)) -> Feedback "Review: {text}")
  (defprompt revise (:fills (text :text) (notes :value List[String])) -> Draft "Revise: {text} {notes}")
  (defprompt execute (:fills (text :text)) -> Feedback "Execute: {text}")
  (defworkflow run ((task String)) -> Feedback
    (let* ((designer (agent providers.claude :model "planner" :effort "high"))
           (reviewer (agent providers.codex :model "reviewer" :effort "high"))
           (a1 (provider-result designer :prompt (draft :task task) :timeout-sec 60))
           (b1 (provider-result reviewer :prompt (review :text a1.text) :timeout-sec 60))
           (a2 (provider-result designer :prompt (revise :text a1.text :notes b1.notes) :timeout-sec 60))
           (b2 (provider-result reviewer :prompt (execute :text a2.text) :timeout-sec 60)))
      b2)))'''

PLAN = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": "success", "result": {"text": "d2"}}],
        "codex": [{"mode": "success", "result": {"notes": ["n"]}}, {"mode": "success", "result": {"notes": ["done"]}}]}


def fixture(root: Path, source: str = SOURCE) -> list[str]:
    (root / "main.orc").write_text(source, encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.claude": "claude_unrestricted_workspace", "providers.codex": "codex"}))
    return ["main.orc", "--source-root", str(root), "--provider-externs-file", "providers.json", "--input", "task=t"]


def memo_of(root: Path):
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    classes = site_classes(authority.program)
    return run_root, authority, classes, read_memo(authority.memo_path, classes)


def turns(memo, classes):
    return {i.rsplit("/ ", 1)[1]: c.data for i, c in memo.active_commits.items() if classes[i] == "agent_turn"}


def test_clean_run_commits_four_turns_on_two_native_sessions(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    run = _cli(tmp_path, "run", *fixture(tmp_path))
    assert run.returncode == 0, run.stderr
    run_root, _authority, classes, memo = memo_of(tmp_path)
    assert memo.terminal.data == {"record": "terminal", "outcome": "completed", "value": {"notes": ["done"]}}
    t = turns(memo, classes)
    assert set(t) == {"a1", "b1", "a2", "b2"}
    assert [t[k]["value"] for k in ("a1", "b1", "a2", "b2")] == [{"text": "d1"}, {"notes": ["n"]}, {"text": "d2"}, {"notes": ["done"]}]
    designer = t["a1"]["proof"]["agent"]; reviewer = t["b1"]["proof"]["agent"]
    assert designer.endswith("/ designer") and reviewer.endswith("/ reviewer")
    assert (t["a1"]["proof"]["predecessor"], t["a2"]["proof"]["predecessor"]) == (None, t["a1"]["identity"])
    assert (t["b1"]["proof"]["predecessor"], t["b2"]["proof"]["predecessor"]) == (None, t["b1"]["identity"])
    assert t["a1"]["proof"]["locator"] == t["a2"]["proof"]["locator"] != t["b1"]["proof"]["locator"] == t["b2"]["proof"]["locator"]
    assert t["a2"]["proof"]["position"]["end_line"] > t["a1"]["proof"]["position"]["end_line"]
    assert (t["a1"]["proof"]["adapter"], t["b1"]["proof"]["adapter"]) == ("claude_stream_json_stdout", "codex_exec_jsonl_stdout")
    # predecessor is a dependency even where the prompt does not consume it (b2 reads a2 only)
    assert t["b1"]["identity"] in t["b2"]["depends_on"] and designer in t["a1"]["depends_on"]
    for row in t.values():
        assert (row["identity"], row["attempt"]) in memo.settlements
    requests = shim_requests(tmp_path)
    assert [r["tool"] for r in requests] == ["claude", "codex", "claude", "codex"]
    assert requests[0]["session"] == requests[2]["session"] and "--resume" in requests[2]["argv"] and "--resume" not in requests[0]["argv"]
    assert requests[1]["session"] == requests[3]["session"] and "resume" in requests[3]["argv"]
    assert all("--model" in r["argv"] or "--model" in " ".join(r["argv"]) for r in requests)
    attempt = run_root / Path(t["a1"]["result_path"]).parent
    receipt = json.loads((attempt / "receipt.json").read_text())
    assert receipt["completion"] == "completed" and receipt["locator"] == t["a1"]["proof"]["locator"]
    assert receipt["position_after"] == t["a1"]["proof"]["position"] and receipt["result_digest"] == t["a1"]["result_digest"]
    assert receipt["pgid"] is not None and receipt["leader_start_time"] is not None       # launch facts recorded at bind (R3) ...
    assert receipt["config_digest"] == t["a1"]["proof"]["config_digest"]                    # ... and monotone: they survive completion


def test_input_parts_bind_agent_and_predecessor(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    _root, _authority, classes, memo = memo_of(tmp_path)
    t = turns(memo, classes)
    for name, row in t.items():
        assert {"agent", "predecessor", "declaration", "values", "policy", "params", "prompt", "dependency_rows", "delivery"} <= set(row["input_parts"])
    assert t["a1"]["input_parts"]["agent"] == t["a2"]["input_parts"]["agent"] != t["b1"]["input_parts"]["agent"]
    assert t["a1"]["input_parts"]["predecessor"] != t["a2"]["input_parts"]["predecessor"]


def test_completed_resume_is_readonly_and_dispatches_nothing(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    run_root, *_ = memo_of(tmp_path)
    before = {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"}
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    assert {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"} == before
    assert len(shim_requests(tmp_path)) == 4


def test_receipt_updates_are_monotone(tmp_path) -> None:
    from orchestrator.workflow.evaluated.agent_sessions import Receipt, read_receipt, write_receipt
    from orchestrator.workflow.evaluated.agent_turns import update_receipt
    from orchestrator.workflow.evaluated.memo import MemoError
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    files = WorkspaceFiles(tmp_path)
    write_receipt(files, Receipt(run_id="r", agent="a", turn="t", attempt=1, predecessor=None, input_digest="sha256:" + "0" * 64,
                                 adapter="codex_exec_jsonl_stdout", config_digest="sha256:" + "0" * 64, mode="fresh", locator=None,
                                 pgid=None, leader_start_time=None, position_before=None, position_after=None, completion="intent", result_digest=None))
    update_receipt(files, completion="launching", pgid=4242, leader_start_time=77)
    done = update_receipt(files, locator="sess", position_after={"turn_id": "t", "end_line": 9}, completion="completed")
    assert (done.pgid, done.leader_start_time, done.locator, done.completion) == (4242, 77, "sess", "completed")   # launch facts survive later writes
    assert (read_receipt(files).pgid, read_receipt(files).leader_start_time) == (4242, 77)
    with pytest.raises(MemoError, match="memo_inconsistent"):
        update_receipt(files, completion="intent")                                          # never backwards
    files.close()


def test_policy_mismatch_refuses_before_dispatch(tmp_path, monkeypatch) -> None:
    from orchestrator.workflow.evaluated.agent_sessions import AgentBinding
    from orchestrator.workflow.evaluated.agent_turns import AgentTurnError, check_origins
    with pytest.raises(AgentTurnError) as excinfo:
        check_origins({"origins": ["codex"]}, AgentBinding("x", "r", "claude_unrestricted_workspace", {}, "sha256:" + "0" * 64))
    assert excinfo.value.code == "agent_policy_mismatch"


# Kill-free seam: the executor has bound the child (receipt `launching`) and the CLI completed normally; completion
# verification then raises an exception the coordinator does not map. Task 11 reuses this driver for the resume half.
BROKEN_VERIFY = r'''import os, sys
from orchestrator.workflow.evaluated import agent_turns
verify = agent_turns._verify_completion
def broken(attempt, resolved, session_id, before):
    if attempt.identity.endswith(os.environ["BROKEN_TURN"]):
        raise OSError("disk hiccup after launch")
    return verify(attempt, resolved, session_id, before)
agent_turns._verify_completion = broken
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


def test_unmapped_exception_after_launch_keeps_started_pending_as_unresolved(tmp_path, monkeypatch) -> None:
    """Design failure table row 3: once the child is bound, an exception the coordinator does not map is an unknown
    append/completion outcome, not a failed attempt: tail = pending `started`, no `failed`, no terminal, receipt `unknown`
    with its launch facts, public exit 1 with `agent_turn_unresolved`."""
    import os, subprocess, sys
    from tests.workflow_evaluated_consumer_sources import ROOT
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    run = subprocess.run([sys.executable, "-c", BROKEN_VERIFY, "run", *fixture(tmp_path)], cwd=tmp_path, capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "BROKEN_TURN": "/ a2"})
    assert run.returncode == 1 and "agent_turn_unresolved" in run.stderr, run.stderr
    run_root, _a, classes, memo = memo_of(tmp_path)
    tail = memo.entries[-1].data
    assert tail["record"] == "started" and tail["identity"].endswith("/ a2") and tail["identity"] in memo.pending_starts
    assert memo.terminal is None and not any(e.data["record"] == "failed" for e in memo.entries)
    t = turns(memo, classes)
    assert set(t) == {"a1", "b1"}
    receipt = json.loads((run_root / Path(tail["result_path"]).parent / "receipt.json").read_text())
    assert receipt["completion"] == "unknown"                                               # uncertainty, never `not_dispatched`
    assert receipt["pgid"] is not None and receipt["locator"] == t["a1"]["proof"]["locator"]  # launch facts kept for resume
    assert [r["tool"] for r in shim_requests(tmp_path)] == ["claude", "codex", "claude"]


# Kill-free seam for design row 6: the adapter confirmed completion (receipt `completed`) and the typed result validated;
# the prepared-proof write (`update_receipt(result_digest=...)`, the only update carrying just that key) then raises.
BROKEN_PROJECT = r'''import os, sys
from orchestrator.workflow.evaluated import agent_turns
update = agent_turns.update_receipt
def broken(files, **changes):
    if set(changes) == {"result_digest"} and agent_turns.read_receipt(files).turn.endswith(os.environ["BROKEN_TURN"]):
        raise OSError("disk hiccup while projecting the result")
    return update(files, **changes)
agent_turns.update_receipt = broken
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


def test_unmapped_exception_during_projection_keeps_started_pending_with_a_completed_receipt(tmp_path, monkeypatch) -> None:
    """Design failure table row 6: native completion confirmed, interrupted before the prepared proof -> `started` stays
    pending and the receipt stays `completed` (not `unknown`, no `failed`, no terminal); only an invalid typed result
    may close `failed`. Resume recovers this ordinal (Task 11)."""
    import os, subprocess, sys
    from tests.workflow_evaluated_consumer_sources import ROOT
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    run = subprocess.run([sys.executable, "-c", BROKEN_PROJECT, "run", *fixture(tmp_path)], cwd=tmp_path, capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "BROKEN_TURN": "/ a2"})
    assert run.returncode == 1 and "agent_turn_unresolved" in run.stderr, run.stderr
    run_root, _a, classes, memo = memo_of(tmp_path)
    tail = memo.entries[-1].data
    assert tail["record"] == "started" and tail["identity"].endswith("/ a2") and tail["identity"] in memo.pending_starts
    assert memo.terminal is None and not any(e.data["record"] == "failed" for e in memo.entries)
    receipt = json.loads((run_root / Path(tail["result_path"]).parent / "receipt.json").read_text())
    assert receipt["completion"] == "completed" and receipt["result_digest"] is None      # completion kept; proof not yet durable
    assert receipt["position_after"] is not None and receipt["pgid"] is not None
    assert len(shim_requests(tmp_path)) == 3


REGISTRY_SWAP = r'''import sys
from orchestrator.providers import registry as registry_module
from orchestrator.providers.types import ProviderTemplate
load = registry_module.ProviderRegistry._load_builtin_providers
def swapped(self):
    templates = load(self)
    codex = templates["codex"]
    templates["codex"] = ProviderTemplate(**{**codex.__dict__, "defaults": {**codex.defaults, "reasoning_effort": "low"}})
    return templates
registry_module.ProviderRegistry._load_builtin_providers = swapped
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


@pytest.mark.skipif(not __import__("importlib").util.find_spec("tests.test_workflow_evaluated_agent_turn_recovery"), reason="kill-point drivers land in Task 11")
def test_template_change_between_run_and_resume_refuses_agent_policy_mismatch(tmp_path, monkeypatch) -> None:
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECORD, _stopped
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": "settled", "STOP_TURN": "/ a1"}, "run", *fixture(tmp_path))
    run_root, *_ = memo_of(tmp_path)
    import os, subprocess, sys
    from tests.workflow_evaluated_consumer_sources import ROOT
    resumed = subprocess.run([sys.executable, "-c", REGISTRY_SWAP, "resume", run_root.name], cwd=tmp_path, capture_output=True, text=True,
                             env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"})
    assert resumed.returncode == 1 and "agent_policy_mismatch" in resumed.stderr      # reviewer b1 refused before dispatch
    assert [r["tool"] for r in shim_requests(tmp_path)] == ["claude"]


def _driven(root: Path, script: str, env: dict, *arguments: str):
    import os, subprocess, sys
    from tests.workflow_evaluated_consumer_sources import ROOT
    return subprocess.run([sys.executable, "-c", script, *arguments], cwd=root, capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", **env})


def _failed_rows(memo) -> list[dict]:
    return [e.data for e in memo.entries if e.data["record"] == "failed"]


@pytest.mark.parametrize("plan, turn, code", [
    ({**PLAN, "claude": [{"mode": "invalid-result"}]}, "/ a1", "provider_result_invalid"),
    ({**PLAN, "claude": [PLAN["claude"][0], {"mode": "invalid-result"}]}, "/ a2", "agent_turn_result_invalid"),
])
def test_invalid_typed_result_closes_failed_with_the_turn_position_code(tmp_path, monkeypatch, plan, turn, code) -> None:
    """Only a conclusively invalid typed result closes `failed`; a later turn never reports `provider_result_invalid`."""
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)
    run = _cli(tmp_path, "run", *fixture(tmp_path))
    assert run.returncode == 1 and code in run.stderr, run.stderr
    run_root, _a, _classes, memo = memo_of(tmp_path)
    (failed,) = _failed_rows(memo)
    assert failed["identity"].endswith(turn) and failed["code"] == code and not memo.pending_starts
    assert memo.terminal.data["outcome"] == "failed"
    started = next(e.data for e in memo.entries if e.data["record"] == "started" and e.data["identity"] == failed["identity"])
    assert json.loads((run_root / Path(started["result_path"]).parent / "receipt.json").read_text())["completion"] == "completed"


IS_ERROR = r'''import os, sys
from orchestrator.workflow.evaluated import agent_turns
launch = agent_turns.launch_provider
def flagged(node, resolved, identity, **kwargs):
    execution = launch(node, resolved, identity, **kwargs)
    if identity.endswith(os.environ["BROKEN_TURN"]):
        execution.provider_session = {**execution.provider_session, "is_error": True}
    return execution
agent_turns.launch_provider = flagged
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


def test_claude_is_error_result_is_never_committed(tmp_path, monkeypatch) -> None:
    """A Claude `result` with `is_error: true` finalizes as metadata, not a transport error: the turn is refused."""
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    run = _driven(tmp_path, IS_ERROR, {"BROKEN_TURN": "/ a2"}, "run", *fixture(tmp_path))
    assert run.returncode == 1 and "agent_turn_result_invalid" in run.stderr, run.stderr
    _root, _a, classes, memo = memo_of(tmp_path)
    assert set(turns(memo, classes)) == {"a1", "b1"}
    (failed,) = _failed_rows(memo)
    assert failed["identity"].endswith("/ a2") and failed["code"] == "agent_turn_result_invalid"


DIVERGE = r'''import json, os, sys
from pathlib import Path
from orchestrator.workflow.evaluated import agent_turns
perform = agent_turns.perform_turn
def advanced(attempt, **kwargs):
    outcome = perform(attempt, **kwargs)
    if attempt.identity.endswith("/ b1"):          # an operator appends a completed turn to the reviewer's conversation
        (path,) = Path(os.environ["CODEX_HOME"]).rglob("rollout-*.jsonl")
        session = json.loads(path.read_text().splitlines()[0])["payload"]["id"]
        rows = [{"type": "event_msg", "payload": {"type": "task_started", "turn_id": "ext"}},
                {"type": "event_msg", "payload": {"type": "item_completed", "turn_id": "ext", "thread_id": session,
                 "item": {"id": "u-ext", "type": "UserMessage", "content": [{"text_elements": ["operator"]}]}}},
                {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "ext"}}]
        with path.open("a", encoding="utf-8") as out:
            out.write("".join(json.dumps(row) + "\n" for row in rows))
    return outcome
agent_turns.perform_turn = advanced
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


def test_native_head_advanced_elsewhere_refuses_before_started(tmp_path, monkeypatch) -> None:
    """D1: before an append the native head must equal the predecessor's committed position."""
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    run = _driven(tmp_path, DIVERGE, {}, "run", *fixture(tmp_path))
    assert run.returncode == 1 and "agent_session_diverged" in run.stderr, run.stderr
    _root, _a, classes, memo = memo_of(tmp_path)
    assert set(turns(memo, classes)) == {"a1", "b1", "a2"}
    assert not any(e.data["record"] == "started" and e.data["identity"].endswith("/ b2") for e in memo.entries)
    assert memo.terminal.data["code"] == "agent_session_diverged"
    assert [r["tool"] for r in shim_requests(tmp_path)] == ["claude", "codex", "claude"]


def test_config_digest_change_refuses_policy_mismatch(tmp_path) -> None:
    from orchestrator.providers.registry import ProviderRegistry
    from orchestrator.workflow.evaluated.agent_sessions import AgentBinding, pinned_config_digest
    from orchestrator.workflow.evaluated.agent_turns import AgentTurnError, check_origins
    template = ProviderRegistry().get("codex")
    pinned = pinned_config_digest(template, {"model": "m"}, tmp_path)
    check_origins({"origins": ["codex"]}, AgentBinding("x", "r", "codex", {"model": "m"}, pinned), template, tmp_path)
    with pytest.raises(AgentTurnError) as excinfo:
        check_origins({"origins": ["codex"]}, AgentBinding("x", "r", "codex", {"model": "m"}, pinned), template, tmp_path / "moved")
    assert excinfo.value.code == "agent_policy_mismatch"


BUNDLE_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defpath ResultBundle :kind relpath :under ".orchestrate/runs" :must-exist false)
  (defrecord Draft (text String))
  (defprompt draft (:fills (task :text)) -> Draft "Draft: {task}")
  (defworkflow run ((task String)) -> ResultBundle
    (let* ((designer (agent providers.claude :model "planner" :effort "high"))
           (a1 (provider-result designer :prompt (draft :task task) :timeout-sec 60)))
      (provider-bundle-path a1 :as ResultBundle))))'''


def test_agent_turn_result_exposes_its_committed_bundle_path(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    run = _cli(tmp_path, "run", *fixture(tmp_path, BUNDLE_SOURCE))
    assert run.returncode == 0, run.stderr
    run_root, _a, classes, memo = memo_of(tmp_path)
    bundle = memo.terminal.data["value"]
    assert (tmp_path / bundle).resolve() == (run_root / turns(memo, classes)["a1"]["result_path"]).resolve()
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0


UNCONSUMED_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Draft (text String))
  (defprompt draft (:fills (task :text)) -> Draft "Draft: {task}")
  (defworkflow run ((task String)) -> Draft
    (let* ((designer (agent providers.claude :model "planner" :effort "high"))
           (a1 (provider-result designer :prompt (draft :task task) :timeout-sec 60))
           (a2 (provider-result designer :prompt (draft :task task) :timeout-sec 60)))
      a2)))'''


def test_unconsumed_predecessor_is_a_dependency_and_replays_on_the_logical_cursor(tmp_path, monkeypatch) -> None:
    """a2 never reads a1, yet a1 is its predecessor dependency; a read-only resume replays both commits."""
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    assert _cli(tmp_path, "run", *fixture(tmp_path, UNCONSUMED_SOURCE)).returncode == 0
    run_root, _a, classes, memo = memo_of(tmp_path)
    t = turns(memo, classes)
    assert t["a1"]["identity"] in t["a2"]["depends_on"] and t["a2"]["proof"]["predecessor"] == t["a1"]["identity"]
    before = {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"}
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"} == before
    assert len(shim_requests(tmp_path)) == 2


@pytest.mark.parametrize("plan, turn, completion", [
    ({**PLAN, "claude": [PLAN["claude"][0], {"mode": "nonzero-before-append"}]}, "/ a2", "not_dispatched"),
    ({**PLAN, "claude": [PLAN["claude"][0], {"mode": "nonzero"}]}, "/ a2", "unknown"),
    ({**PLAN, "claude": [PLAN["claude"][0], {"mode": "overlap", "result": {"text": "d2"}}]}, "/ a2", "unknown"),
    ({**PLAN, "codex": [{"mode": "nonzero-before-append"}]}, "/ b1", "unknown"),
])
def test_transport_failure_closes_failed_only_when_the_adapter_proves_no_advance(tmp_path, monkeypatch, plan, turn, completion) -> None:
    """Exit codes and stdout never prove non-dispatch: a resumed turn whose native head is unchanged may close `failed`;
    an advanced/open head, an external turn beside ours, or any fresh-turn failure keeps `started` pending."""
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)
    run = _cli(tmp_path, "run", *fixture(tmp_path))
    assert run.returncode == 1, run.stderr
    run_root, _a, _classes, memo = memo_of(tmp_path)
    started = [e.data for e in memo.entries if e.data["record"] == "started" and e.data["identity"].endswith(turn)]
    receipt = json.loads((run_root / Path(started[-1]["result_path"]).parent / "receipt.json").read_text())
    assert receipt["completion"] == completion and receipt["pgid"] is not None
    if completion == "not_dispatched":
        assert [f["code"] for f in _failed_rows(memo)] == ["provider_exit_nonzero"] and memo.terminal is not None
    else:
        assert "agent_turn_unresolved" in run.stderr and started[-1]["identity"] in memo.pending_starts
        assert memo.terminal is None and not _failed_rows(memo)
