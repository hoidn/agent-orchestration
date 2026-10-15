"""Allocation commits a runtime-owned Agent descriptor without launching anything; replay reconstructs it."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.agent_sessions import AgentBinding, Receipt, read_receipt, resolve_agent_reference, write_receipt
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import MemoError, read_memo
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_invalidate import _cli

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Note (text String))
  (defworkflow run ((task String) (n Int)) -> Note
    (let* ((designer (agent providers.codex :model "chosen-model" :effort "low"))
           (copies (loop/recur :max 3 :state (loop-state (i Int 0)) :on-exhausted 0
                      (fn (state)
                        (if (>= state.i n) (done state.i)
                            (let* ((inner (agent providers.claude :model "m2")))
                              (continue (loop-state :like state :i (+ state.i 1)))))))))
      (record Note :text task))))'''


def _fixture(root: Path) -> list[str]:
    (root / "main.orc").write_text(SOURCE, encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.codex": "codex", "providers.claude": "claude_unrestricted_workspace"}))
    return ["run", "main.orc", "--source-root", str(root), "--provider-externs-file", "providers.json", "--input", "task=t", "--input", "n=2"]


def test_allocations_commit_descriptors_with_no_dispatch_and_replay_readonly(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan={"codex": [], "claude": []})
    run = _cli(tmp_path, *_fixture(tmp_path))
    assert run.returncode == 0, run.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    classes = site_classes(authority.program)
    memo = read_memo(authority.memo_path, classes)
    from orchestrator.workflow.evaluated.memo_reducer import _DYNAMIC_INDEX
    allocations = {i: c for i, c in memo.active_commits.items() if (classes.get(i) or classes[_DYNAMIC_INDEX.sub("[*]", i)]) == "agent"}
    assert len(allocations) == 3  # designer + two loop activations
    designer = next(c for i, c in allocations.items() if i.endswith("/ designer"))
    value = designer.data["value"]
    assert {k: value[k] for k in ("run_id", "identity", "provider", "policy")} == {"run_id": run_root.name, "identity": designer.data["identity"], "provider": "codex", "policy": {"model": "chosen-model", "effort": "low"}}
    from orchestrator.providers.registry import ProviderRegistry
    from orchestrator.workflow.evaluated.agent_sessions import pinned_config_digest
    assert value["config_digest"] == pinned_config_digest(ProviderRegistry().get("codex"), value["policy"], tmp_path.resolve())  # effective cwd
    assert designer.data["effect_class"] == "agent" and "proof" not in designer.data
    assert {c.data["value"]["identity"] for c in allocations.values()} == set(allocations)
    assert shim_requests(tmp_path) == []
    assert (run_root / Path(designer.data["result_path"])).read_bytes()
    assert sorted(p.name for p in (run_root / Path(designer.data["result_path"]).parent).iterdir()) == ["result.json"]
    before = {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"}
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"} == before


def test_reference_decoding_requires_the_active_allocation_commit(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan={"codex": [], "claude": []})
    assert _cli(tmp_path, *_fixture(tmp_path)).returncode == 0
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    memo = read_memo(authority.memo_path, site_classes(authority.program))
    designer = next(c for i, c in memo.active_commits.items() if i.endswith("/ designer"))
    binding = resolve_agent_reference(memo, designer.data["value"], run_id=run_root.name)
    assert binding == AgentBinding(designer.data["identity"], run_root.name, "codex", {"model": "chosen-model", "effort": "low"}, designer.data["value"]["config_digest"])
    with pytest.raises(MemoError, match="memo_inconsistent"):
        resolve_agent_reference(memo, {**designer.data["value"], "policy": {"model": "other"}}, run_id=run_root.name)
    with pytest.raises(MemoError, match="memo_inconsistent"):
        resolve_agent_reference(memo, designer.data["value"], run_id="another-run")


def test_receipt_round_trips_and_rejects_foreign_schema(tmp_path) -> None:
    files = WorkspaceFiles(tmp_path)
    receipt = Receipt(run_id="r", agent="a", turn="t", attempt=1, predecessor=None, input_digest="sha256:" + "0" * 64,
                      adapter="codex_exec_jsonl_stdout", config_digest="sha256:" + "0" * 64, mode="fresh", locator=None, pgid=None,
                      leader_start_time=None, position_before=None, position_after=None, completion="intent", result_digest=None)
    write_receipt(files, receipt)
    assert read_receipt(files) == receipt
    (tmp_path / "receipt.json").write_text(json.dumps({"schema": "other"}))
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_receipt(files)
    files.close()


def _receipt(**changes) -> Receipt:
    base = dict(run_id="r", agent="a", turn="t", attempt=1, predecessor=None, input_digest="sha256:" + "0" * 64,
                adapter="codex_exec_jsonl_stdout", config_digest="sha256:" + "0" * 64, mode="fresh", locator=None, pgid=None,
                leader_start_time=None, position_before=None, position_after=None, completion="intent", result_digest=None)
    return Receipt(**{**base, **changes})


def test_missing_receipt_reads_as_none(tmp_path) -> None:
    files = WorkspaceFiles(tmp_path)
    assert read_receipt(files) is None
    files.close()


@pytest.mark.parametrize("field, value", [("mode", "replay"), ("completion", "done"), ("attempt", 0), ("attempt", True),
                                          ("pgid", "4242"), ("position_after", {"turn_id": "x"}), ("run_id", None)])
def test_malformed_receipt_field_is_refused_on_read_and_write(tmp_path, field, value) -> None:
    files = WorkspaceFiles(tmp_path)
    with pytest.raises(MemoError, match="memo_inconsistent"):
        write_receipt(files, _receipt(**{field: value}))
    row = json.loads(json.dumps({**_receipt().__dict__, field: value}))
    (tmp_path / "receipt.json").write_text(json.dumps(row))
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_receipt(files)
    files.close()


def test_backward_completion_transition_is_refused(tmp_path) -> None:
    files = WorkspaceFiles(tmp_path)
    write_receipt(files, _receipt(completion="launching", pgid=7))
    with pytest.raises(MemoError, match="memo_inconsistent"):
        write_receipt(files, _receipt(completion="intent"))
    assert read_receipt(files).completion == "launching"
    files.close()


@pytest.mark.parametrize("field, value", [("run_id", "r2"), ("agent", "b"), ("turn", "u"), ("attempt", 2),
                                          ("input_digest", "sha256:" + "1" * 64), ("predecessor", "p")])
def test_binding_field_change_is_refused(tmp_path, field, value) -> None:
    files = WorkspaceFiles(tmp_path)
    write_receipt(files, _receipt())
    with pytest.raises(MemoError, match="memo_inconsistent"):
        write_receipt(files, _receipt(**{field: value}, completion="launching"))
    assert read_receipt(files) == _receipt()
    files.close()
