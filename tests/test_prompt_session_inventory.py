"""Adapter immediate-inventory agreement across publication and lookup."""

import json

from orchestrator.prompt_session import resolve_prompt_session
from tests.test_prompt_session_publication import PRIMARY, _publish, _setup_publication


def test_publication_and_lookup_use_adapter_immediate_inventory(tmp_path) -> None:
    setup = _setup_publication(tmp_path)
    manager, _scaffold, _verification, frame, metadata, _identity = setup
    sessions = manager.run_root / "provider_sessions"
    nested = sessions / "task__v1" / "nested"
    nested.mkdir()
    (nested / "evidence.txt").write_bytes(b"evidence")
    frame["observed"]["child_relpaths"] = sorted([PRIMARY, "nested"])
    (sessions / "task__v1.json").write_text(json.dumps(metadata), encoding="utf-8")
    _publish(setup)
    assert resolve_prompt_session(manager.run_root.parent, "run-1").run_id == "run-1"
