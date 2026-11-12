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
        assert 'copy refused' in str(checkpoint.value) and 'scope did not empty' in str(checkpoint.value)
        for _ in range(2):
            with pytest.raises(RunRefRuntimeError) as final_stop:
                session.stop()
            assert final_stop.value.code == 'run_ref_environment_escape_rejected'
            assert 'scope did not empty' in final_stop.value.detail
        assert events == ['stop-failed-not-empty']
        assert session._stop_record is None
        assert (session.layout.child_root / 'budget.json').read_bytes() == prior_budget
    finally:
        session.snapshots.close()
        session.clone_files.close()
        admission.close()


