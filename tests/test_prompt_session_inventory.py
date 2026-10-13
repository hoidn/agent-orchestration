"""Adapter immediate-inventory agreement across publication and lookup (R6:
the shared close-time observer classifies the live tree; the frame carries
the recursive journal relpaths it produced)."""

import json
from pathlib import Path

from orchestrator.prompt_session import resolve_prompt_session
from tests.test_prompt_session import PRIMARY, _historical_run, _canonical


def test_publication_and_lookup_use_adapter_immediate_inventory(tmp_path) -> None:
    setup = _historical_run(tmp_path, plant="advised-fanout")
    manager, _scaffold, _verification, frame, metadata, _identity = setup
    sessions = manager.run_root / "provider_sessions"
    stem = PRIMARY[: -len(".jsonl")]
    # A non-journal artifact nested under the artifacts dir stays manifest-only
    # (never an observed relpath); the planted child journals must.
    (sessions / "task__v1" / stem / "evidence.txt").write_bytes(b"evidence")
    (sessions / "task__v1.json").write_text(json.dumps(metadata), encoding="utf-8")
    from orchestrator.providers.omp_session_manifest import build_session_manifest
    import os
    # evidence is historical manifest-only data, outside the journal inventory.
    live = sessions / "task__v1"
    frozen = sessions / "task__v1.snapshot"
    (frozen / stem / "evidence.txt").write_bytes(b"evidence")
    link_path = sessions / "task__v1.session-link.json"
    link = json.loads(link_path.read_bytes())
    for key, path in (("live_manifest_sha256", live), ("snapshot_manifest_sha256", frozen)):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            link["digests"][key] = build_session_manifest(fd).manifest_sha256
        finally:
            os.close(fd)
    link_path.write_bytes(_canonical(link))
    assert resolve_prompt_session(manager.run_root.parent, "run-1").run_id == "run-1"
    assert frame["observed"] == {
        "advisor_relpaths": [f"{stem}/__advisor.jsonl"],
        "child_relpaths": [f"{stem}/alpha.jsonl", f"{stem}/beta.jsonl"],
    }
