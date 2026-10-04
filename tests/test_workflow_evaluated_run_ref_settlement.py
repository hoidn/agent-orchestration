"""Durable memo gaps and readonly proof replay at the public parent service."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.main import create_parser
from orchestrator.workflow.evaluated import runtime as evaluated_runtime
from orchestrator.workflow.evaluated import run_ref as adapter
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import MemoError, read_memo
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from tests.test_workflow_evaluated_run_ref import (
    _authority, _assert_readonly_resumes, _public_fixture, _repeated_fixture,
)
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_resume import _resume_cli


def _service_run(monkeypatch, parent, source, refs, *extra):
    argv = ["run", str(source), "--run-ref-root", str(refs), *extra]
    args = create_parser().parse_args(argv)
    monkeypatch.chdir(parent)
    with monkeypatch.context() as context:
        context.setattr(sys, "argv", ["orchestrator", *argv])
        return run_workflow(args)


def _commit_gap(monkeypatch, parent, source, refs, *, gap="pending", extra=()):
    real_finalize = adapter.finalize_run_ref_parent_commit

    def stop(request, prepared, **kwargs):
        if gap == "committed":
            real_finalize(request, prepared, **kwargs)
        raise RuntimeError("test interruption after durable memo commit")

    with monkeypatch.context() as context:
        context.setattr(adapter, "finalize_run_ref_parent_commit", stop)
        result = _service_run(context, parent, source, refs, *extra)
    assert result.exit_code == 1
    authority, snapshot = _authority(parent)
    assert snapshot.unsettled_coordinators and not snapshot.pending_starts and snapshot.terminal is None
    ledger = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
    assert ledger.rows[-1].stage == ("committed" if gap == "committed" else "completed_pending_parent_commit")
    return authority, snapshot


@pytest.mark.parametrize("gap", ["pending", "committed"])
def test_public_resume_reconciles_actual_memo_commit_without_child(tmp_path, monkeypatch, gap):
    parent, source, refs = _public_fixture(tmp_path)
    authority, before = _commit_gap(monkeypatch, parent, source, refs, gap=gap)
    (commit,) = before.active_commits.values()
    child = Path(commit.data["proof"]["settled_result"]["workspace_path"])
    child_count = len(list(refs.rglob("child-request.json")))
    result = _resume_cli(parent, authority.run_root.name)
    assert result.returncode == 0, result.stderr
    _, after = _authority(parent)
    assert after.active_commits[commit.data["identity"]] == commit
    assert after.terminal.data["value"] is True
    assert after.entries[-2].data["by"] == "reconcile"
    assert len(list(refs.rglob("child-request.json"))) == child_count == 1
    assert child.exists()
    _assert_readonly_resumes(parent, authority, refs)


@pytest.mark.parametrize("changed", ["value", "result-digest", "artifacts", "numeric-alias"])
def test_finalize_requires_exact_reread_active_commit(tmp_path, monkeypatch, changed):
    parent, source, refs = _public_fixture(tmp_path)
    real_append = evaluated_runtime.append_record
    accepted = []

    def mutate_after_append(path, record, **kwargs):
        entry = real_append(path, record, **kwargs)
        if record["record"] == "committed":
            rows = [json.loads(line) for line in kwargs["run_files"].read("memo.jsonl").splitlines()]
            row = rows[-1]
            if changed == "value":
                row["value"]["value"] = False
                row["result_digest"] = canonical_sha256(row["value"])
            elif changed == "numeric-alias":
                row["value"]["value"] = 1
            elif changed == "result-digest":
                row["result_digest"] = canonical_sha256("different result bytes")
            else:
                row["proof"]["artifacts"]["value"] = False
            kwargs["run_files"].write_atomic("memo.jsonl", b"".join(
                json.dumps(item, separators=(",", ":")).encode() + b"\n" for item in rows))
            authority, snapshot = _authority(parent)
            assert snapshot.active_commits[record["identity"]].data == row
            accepted.append(authority)
        return entry

    monkeypatch.setattr(evaluated_runtime, "append_record", mutate_after_append)
    result = _service_run(monkeypatch, parent, source, refs)
    assert result.exit_code == 1
    assert accepted
    ledger = load_attempt_ledger(accepted[0].run_root / "run-ref-attempts.jsonl")
    assert ledger.rows[-1].stage == "completed_pending_parent_commit"
    snapshot = read_memo(accepted[0].memo_path, site_classes(accepted[0].program))
    assert not snapshot.settlements and snapshot.terminal is None


@pytest.mark.parametrize("child_target", ["2.24", "2.35"])
@pytest.mark.parametrize("structure", ["direct", "helper", "nested"])
def test_public_repetition_resume_after_real_first_settlement(tmp_path, monkeypatch, child_target, structure):
    parent, source, refs = _repeated_fixture(tmp_path, child_target=child_target, structure=structure, forwarding=True)
    real_settle = evaluated_runtime.settle_evaluated_run_ref

    def settle_then_interrupt(*args, **kwargs):
        real_settle(*args, **kwargs)
        raise RuntimeError("test stop after first real commit and settlement")

    with monkeypatch.context() as context:
        context.setattr(evaluated_runtime, "settle_evaluated_run_ref", settle_then_interrupt)
        assert _service_run(context, parent, source, refs).exit_code == 1
    authority, before = _authority(parent)
    (first,) = before.active_commits.values()
    assert len(before.settlements) == 1 and not before.unsettled_coordinators
    ledger_before = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
    assert len(list(refs.rglob("child-request.json"))) == 1
    result = _resume_cli(parent, authority.run_root.name)
    assert result.returncode == 0, result.stderr
    _, after = _authority(parent)
    assert len(after.active_commits) == len(after.settlements) == 2
    assert after.active_commits[first.data["identity"]] == first
    assert len(list(refs.rglob("child-request.json"))) == 2
    ledger_after = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
    assert ledger_after.rows[:len(ledger_before.rows)] == ledger_before.rows
    assert after.terminal.data["value"] is True
    _assert_readonly_resumes(parent, authority, refs)


@pytest.mark.parametrize("gap", ["pending", "committed"])
def test_unsettled_first_iteration_reconciles_before_next_coordinator(tmp_path, monkeypatch, gap):
    parent, source, refs = _repeated_fixture(tmp_path, forwarding=True)
    authority, before = _commit_gap(monkeypatch, parent, source, refs, gap=gap)
    (first,) = before.active_commits.values()
    result = _resume_cli(parent, authority.run_root.name)
    assert result.returncode == 0, result.stderr
    _, after = _authority(parent)
    assert len(after.active_commits) == len(after.settlements) == 2
    assert after.active_commits[first.data["identity"]] == first
    assert len(list(refs.rglob("child-request.json"))) == 2
    _assert_readonly_resumes(parent, authority, refs)


def _mixed_fixture(tmp_path, monkeypatch, *, later="command", smoke=False):
    command = '(command-result emit :argv ("python" "probe.py" answer) :returns Int)'
    provider = '(provider-result providers.review :prompt prompts.base :inputs (answer) :returns Result)'
    definitions = '(defrecord Result (ok Bool))'
    if smoke:
        definitions = lambda call: f'''(defrecord Result (ok Bool))
          (defproc leaf () -> Bool :effects ((runs-ref run)) :lowering inline
            (let* ((child {call})) child.value))
          (defproc invoke () -> Bool :effects ((runs-ref run)) :lowering inline (leaf))'''
        body = lambda call: f'''(let* ((before (command-result emit :argv ("python" "probe.py") :returns Int))
          (answer (invoke)) (provider {provider}) (after {command})) (and answer provider.ok))'''
    else:
        body = lambda call: f'(let* ((child {call}) (answer child.value) (later {command if later == "command" else provider})) answer)'
    parent, source, refs = _public_fixture(tmp_path, body=body, definitions=definitions)
    from tests.test_workflow_evaluated_command_template_scopes import _write_probe, _write_boundaries
    from tests.test_workflow_evaluated_providers import _fixture
    _write_probe(parent)
    boundaries = _write_boundaries(parent)
    extra = ["--command-boundaries-file", str(boundaries)]
    if smoke or later == "provider":
        _source, providers, prompts, _request = _fixture(parent)
        monkeypatch.setenv("PATH", str(parent / "bin") + os.pathsep + os.environ["PATH"])
        extra.extend(["--provider-externs-file", str(providers), "--prompt-externs-file", str(prompts)])
    return parent, source, refs, extra


def _unsettle_first(authority, *, gap):
    """Adversarial valid prefix fixture; later commits were originally made after settlement."""
    rows = [json.loads(line) for line in authority.memo_path.read_bytes().splitlines()]
    rows = [row for row in rows if row["record"] not in {"settled", "terminal"}]
    authority.memo_path.write_bytes(b"".join(json.dumps(row).encode() + b"\n" for row in rows))
    ledger_path = authority.run_root / "run-ref-attempts.jsonl"
    if gap == "pending":
        lines = ledger_path.read_bytes().splitlines(keepends=True)
        ledger_path.write_bytes(b"".join(lines[:-1]))
    ledger = load_attempt_ledger(ledger_path)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert snapshot.unsettled_coordinators and not snapshot.terminal
    assert ledger.rows[-1].stage == ("committed" if gap == "committed" else "completed_pending_parent_commit")
    return snapshot


@pytest.mark.parametrize("gap", ["pending", "committed"])
@pytest.mark.parametrize("later", ["command", "provider"])
def test_entire_prefix_divergence_precedes_any_reconcile(tmp_path, monkeypatch, gap, later):
    parent, source, refs, extra = _mixed_fixture(tmp_path, monkeypatch, later=later)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs), *extra)
    assert result.returncode == 0, result.stderr
    authority, _memo = _authority(parent)
    snapshot = _unsettle_first(authority, gap=gap)
    assert len(snapshot.active_commits) == 2
    changed = parent / ("probe.py" if later == "command" else "prompt.md")
    changed.write_text(changed.read_text() + "\n# changed declared input\n")
    before = _tree_bytes(parent), _tree_bytes(refs)
    resumed = _resume_cli(parent, authority.run_root.name)
    assert resumed.returncode == 2 and "effect_input_diverged" in resumed.stderr
    assert (_tree_bytes(parent), _tree_bytes(refs)) == before


def test_public_command_provider_nested_run_ref_smoke_keeps_c9(tmp_path, monkeypatch):
    parent, source, refs, extra = _mixed_fixture(tmp_path, monkeypatch, smoke=True)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs), *extra)
    assert result.returncode == 0, result.stderr
    authority, memo = _authority(parent)
    commits = list(memo.active_commits.values())
    assert [row.data["effect_class"] for row in commits] == ["command", "run_ref", "provider", "command"]
    assert commits[1].data["identity"] in commits[2].data["depends_on"]
    assert commits[1].data["identity"] in commits[3].data["depends_on"]
    assert memo.terminal.data["value"] is True
    _assert_readonly_resumes(parent, authority, refs)


@pytest.mark.parametrize("gap", ["pending", "committed"])
@pytest.mark.parametrize("change", ["artifact-alias", "value-alias", "parent", "config"])
def test_parser_valid_memo_proof_tamper_refuses_readonly(tmp_path, monkeypatch, gap, change):
    parent, source, refs = _public_fixture(tmp_path)
    authority, _memo = _commit_gap(monkeypatch, parent, source, refs, gap=gap)
    rows = [json.loads(line) for line in authority.memo_path.read_bytes().splitlines()]
    commit = rows[-1]
    if change == "artifact-alias":
        commit["proof"]["artifacts"]["value"] = 1
    elif change == "value-alias":
        commit["value"]["value"] = 1
    elif change == "parent":
        commit["proof"]["settled_result"]["visit"]["parent_run_id"] = "other-parent"
    else:
        commit["proof"]["settled_result"]["step_config_digest"] = canonical_sha256("different config")
    authority.memo_path.write_bytes(b"".join(json.dumps(row).encode() + b"\n" for row in rows))
    assert read_memo(authority.memo_path, site_classes(authority.program)).unsettled_coordinators
    before = _tree_bytes(parent), _tree_bytes(refs)
    resumed = _resume_cli(parent, authority.run_root.name)
    assert resumed.returncode == 2, resumed.stderr
    assert (_tree_bytes(parent), _tree_bytes(refs)) == before


def test_completed_resume_keeps_tail_and_view_without_coordinator_calls(tmp_path, monkeypatch):
    parent, source, refs = _public_fixture(tmp_path)
    assert _run_cli(parent, str(source), "--run-ref-root", str(refs)).returncode == 0
    authority, _memo = _authority(parent)
    (authority.run_root / "state.json").write_text('{"status":"failed"}')
    with authority.memo_path.open("ab") as stream:
        stream.write(b'{"torn":')
    def forbidden(*args, **kwargs):
        pytest.fail("completed resume called a mutable coordinator operation")
    monkeypatch.setattr(adapter, "recover_run_ref_settlement", forbidden)
    monkeypatch.setattr(adapter, "prepare_run_ref_settlement", forbidden)
    monkeypatch.setattr(adapter, "finalize_run_ref_parent_commit", forbidden)
    monkeypatch.chdir(parent)
    before = _tree_bytes(parent), _tree_bytes(refs)
    for _ in range(2):
        assert resume_workflow(authority.run_root.name) == 0
        assert (_tree_bytes(parent), _tree_bytes(refs)) == before


def _install_fault(context, fault):
    real_append = evaluated_runtime.append_record
    real_settled_append = adapter.append_record

    def fail_commit(path, record, **kwargs):
        if record["record"] == "committed" and fault == "before-commit":
            raise OSError("test append failed before commit bytes")
        result = real_append(path, record, **kwargs)
        if record["record"] == "committed":
            raise OSError("test sync failure after complete commit bytes")
        return result

    def fail_settled(path, record, **kwargs):
        if record["record"] == "settled":
            raise OSError("test settled append failed")
        return real_settled_append(path, record, **kwargs)

    def fail_prepare(*args, **kwargs):
        raise OSError("test failure before first child allocation")

    if fault in {"before-commit", "after-commit"}:
        context.setattr(evaluated_runtime, "append_record", fail_commit)
    elif fault == "settled":
        context.setattr(adapter, "append_record", fail_settled)
    else:
        context.setattr(adapter, "prepare_run_ref_settlement", fail_prepare)


@pytest.mark.parametrize("child_target", ["2.24", "2.35"])
@pytest.mark.parametrize("fault", ["before-commit", "after-commit", "settled", "before-child"])
def test_failed_append_and_settlement_preserve_durable_commit_and_ordinals(tmp_path, monkeypatch, child_target, fault):
    parent, source, refs = _public_fixture(tmp_path, child_target=child_target)
    with monkeypatch.context() as context:
        _install_fault(context, fault)
        assert _service_run(context, parent, source, refs).exit_code == 1
    authority, before = _authority(parent)
    durable = fault in {"after-commit", "settled"}
    if durable:
        assert len(before.active_commits) == 1 and before.unsettled_coordinators
        assert not before.pending_starts and before.terminal is None
        assert all(row.data["record"] != "failed" for row in before.entries)
    else:
        assert not before.active_commits and before.terminal.data["outcome"] == "failed"
    result = _resume_cli(parent, authority.run_root.name)
    assert result.returncode == 0, result.stderr
    _, after = _authority(parent)
    (commit,) = after.active_commits.values()
    proof = commit.data["proof"]["settled_result"]
    expected = {"before-commit": (2, 2, 2), "after-commit": (1, 1, 1),
        "settled": (1, 1, 1), "before-child": (2, 1, 1)}[fault]
    assert (commit.data["attempt"], proof["attempt_ordinal"], len(list(refs.rglob("child-request.json")))) == expected
    assert after.terminal.data["value"] is True
    _assert_readonly_resumes(parent, authority, refs)


@pytest.mark.parametrize("position", ["first", "middle", "last"])
def test_public_invalidate_refuses_coordinator_anywhere_in_suffix(tmp_path, position):
    from tests.test_workflow_evaluated_command_template_scopes import _write_probe, _write_boundaries
    from tests.test_workflow_evaluated_invalidate import _cli
    command = '(command-result emit :argv ("python" "probe.py") :returns Int)'
    def body(call):
        before = f"(before {command})" if position != "first" else ""
        after = f"(after {command})" if position != "last" else ""
        return f"(let* ({before} (child {call}) {after}) child.value)"
    parent, source, refs = _public_fixture(tmp_path, body=body)
    _write_probe(parent)
    boundaries = _write_boundaries(parent)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs), "--command-boundaries-file", str(boundaries))
    assert result.returncode == 0, result.stderr
    authority, memo = _authority(parent)
    commits = list(memo.active_commits.values())
    before = _tree_bytes(parent), _tree_bytes(refs)
    for anchor in (commits[0], next(row for row in commits if row.data["effect_class"] == "run_ref")):
        result = _cli(parent, "invalidate", authority.run_root.name, anchor.data["identity"])
        assert result.returncode == 2 and "invalidate_coordinator_committed" in result.stderr
        assert (_tree_bytes(parent), _tree_bytes(refs)) == before


def _assert_reducer_guard_readonly(parent, refs, authority, message):
    before = _tree_bytes(parent), _tree_bytes(refs)
    with pytest.raises(MemoError, match=message) as error:
        read_memo(authority.memo_path, site_classes(authority.program))
    assert error.value.code == "memo_inconsistent"
    result = _resume_cli(parent, authority.run_root.name)
    assert result.returncode == 2 and "memo_inconsistent" in result.stderr
    assert (_tree_bytes(parent), _tree_bytes(refs)) == before


def test_public_coordinator_terminal_requires_settlement(tmp_path, monkeypatch):
    parent, source, refs = _public_fixture(tmp_path)
    authority, snapshot = _commit_gap(monkeypatch, parent, source, refs)
    prefix = read_memo(authority.memo_path, site_classes(authority.program))
    assert prefix == snapshot and prefix.unsettled_coordinators and not prefix.pending_starts
    with authority.memo_path.open("a") as journal:
        journal.write(json.dumps({"record": "terminal", "outcome": "completed", "value": True}) + "\n")
    _assert_reducer_guard_readonly(parent, refs, authority,
        "terminal leaves an attempt or coordinator unsettled")


def test_public_committed_coordinator_cannot_be_superseded(tmp_path, monkeypatch):
    from orchestrator.workflow.evaluated.attempts import attempt_paths
    parent, source, refs = _public_fixture(tmp_path)
    assert _service_run(monkeypatch, parent, source, refs).exit_code == 0
    authority, snapshot = _authority(parent)
    authority.memo_path.write_bytes(authority.memo_path.read_bytes()[:snapshot.terminal.offset])
    prefix = read_memo(authority.memo_path, site_classes(authority.program))
    (commit,) = prefix.active_commits.values()
    assert prefix.terminal is None and (commit.data["identity"], commit.data["attempt"]) in prefix.settlements
    ordinal, _directory, result_path = attempt_paths(prefix, commit.data["identity"])
    assert ordinal == 2
    candidate = {**prefix.entries[0].data, "attempt": ordinal, "result_path": result_path}
    with authority.memo_path.open("a") as journal:
        journal.write(json.dumps(candidate) + "\n")
    _assert_reducer_guard_readonly(parent, refs, authority,
        "started attempt ordinal is not the next available ordinal")
