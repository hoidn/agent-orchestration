"""Unproved scope teardown must block checkpoint repair and parent settlement."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from orchestrator.workflow.run_ref import confined_lifecycle, confined_session, holder_scope
from orchestrator.workflow.run_ref.image_store import SealedImage
from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError
from tests import test_workflow_run_ref_confined_child as child
from tests.test_workflow_run_ref_confined_child import _removable_tmp, world  # noqa: F401
from tests.test_workflow_run_ref_confined_integration_fixes import _session
from tests.test_workflow_run_ref_holder import LIMITS


def test_holder_scope_stop_failure_is_sticky_and_keeps_teardown_evidence(tmp_path, monkeypatch):
    scope = holder_scope.HolderScope(SealedImage(-1, {}), LIMITS, control_dir=tmp_path)
    scope.path = tmp_path / 'unproved-cgroup'
    scope.runref.mkdir()
    (scope.runref / 'evidence').write_bytes(b'keep')
    kills = []
    monkeypatch.setattr(holder_scope, 'kill_cgroup', lambda path: kills.append(path) or False)
    monkeypatch.setattr(holder_scope.subprocess, 'run', lambda *a, **kw: None)

    with pytest.raises(RunRefRuntimeError) as first:
        scope.stop()
    with pytest.raises(RunRefRuntimeError) as second:
        scope.stop()

    assert first.value is second.value
    assert first.value.code == 'run_ref_environment_lost'
    assert 'did not empty' in first.value.detail
    assert scope._stopped is False
    assert (scope.runref / 'evidence').read_bytes() == b'keep'
    assert kills == [scope.path]


def test_checkpoint_does_not_refreeze_and_session_cannot_succeed_after_stop_failure(world, monkeypatch):
    session, admission, _ = _session(world, monkeypatch)
    prior_budget = (session.layout.child_root / 'budget.json').read_bytes()
    events = []

    def stop():
        events.append('stop-failed-not-empty')
        if len(events) == 1:
            raise RunRefRuntimeError('run_ref_environment_lost', 'scope did not empty')
        # Reproduces a lower layer that incorrectly treats the prior failed stop as done.

    session.holder = SimpleNamespace(stop=stop)
    monkeypatch.setattr(session, '_helper', lambda *_: ('run_ref_environment_escape_rejected', 'copy refused'))
    monkeypatch.setattr(confined_session, 'preflight_checkpoint', lambda *_: events.append('refreeze'))
    try:
        with pytest.raises(Exception) as checkpoint:
            session._checkpoint('effect-attempt-1')
        assert checkpoint.value.code == 'run_ref_environment_escape_rejected'
        assert 'copy refused' in str(checkpoint.value) and 'holder_stop_failed' in str(checkpoint.value)
        assert 'scope did not empty' not in str(checkpoint.value)
        for _ in range(2):
            with pytest.raises(RunRefRuntimeError) as final_stop:
                session.stop()
            assert final_stop.value.code == 'run_ref_environment_escape_rejected'
            assert 'holder_stop_failed' in final_stop.value.detail
            assert 'scope did not empty' not in final_stop.value.detail
        assert events == ['stop-failed-not-empty']
        assert session._stop_record is None
        assert (session.layout.child_root / 'budget.json').read_bytes() == prior_budget
    finally:
        session.snapshots.close()
        session.clone_files.close()
        admission.close()


def test_unproved_stop_aborts_lifecycle_before_witness_delta_or_parent_settlement(world, monkeypatch):
    events = []
    stop = child.FakeHolder.stop
    helper = confined_session.ConfinedChildSession._helper

    def stop_without_proof(holder):
        if not holder.stopped:
            stop(holder)
            events.append('stop-failed-not-empty')
            raise RunRefRuntimeError('run_ref_environment_lost', 'scope did not empty')

    def failed_checkpoint(session, operation, *args):
        if operation == 'checkpoint':
            return 'run_ref_environment_escape_rejected', 'copy refused'
        return helper(session, operation, *args)

    monkeypatch.setattr(child.FakeHolder, 'stop', stop_without_proof)
    monkeypatch.setattr(confined_session.ConfinedChildSession, '_helper', failed_checkpoint)
    monkeypatch.setattr(confined_lifecycle, '_checked_child', lambda *a, **kw: events.append('witness'))
    monkeypatch.setattr(confined_lifecycle, 'build_workspace_delta', lambda *a, **kw: events.append('delta'))
    status, (authority, memo) = child._run(world)

    assert status == 1
    assert memo.terminal.data['code'] == 'run_ref_environment_escape_rejected'
    assert 'holder_stop_failed' in memo.terminal.data['message']
    assert 'scope did not empty' not in memo.terminal.data['message']
    assert not memo.active_commits and not memo.settlements
    assert events == ['stop-failed-not-empty']
    assert not list(world['refs'].rglob('workspace-delta.json'))
    assert not list(world['refs'].rglob('evidence-manifest.json'))
    roots = list((authority.run_root / 'run-ref-children').iterdir())
    assert len(roots) == 1 and not (roots[0] / 'budget.json').exists()
