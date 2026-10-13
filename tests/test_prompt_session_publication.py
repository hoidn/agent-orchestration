"""Historical native session lookup and captured private authority regressions."""

import hashlib
import json
import os
from pathlib import Path
import pytest
from orchestrator.prompt_session import PromptSessionError, parse_session_link_bytes
from tests.test_prompt_session import PRIMARY, _historical_run, _real_private_resolved


@pytest.mark.parametrize(
    "provider",
    ("omp", "omp_unrestricted_workspace", "omp_no_tools", "omp_conf"),
)
def test_public_lane_matrix_publishes_then_resolves_exact(
    tmp_path: Path, provider: str
) -> None:
    from orchestrator.prompt_session import resolve_prompt_session

    setup = _historical_run(tmp_path, provider=provider)
    manager = setup[0]
    resolved = resolve_prompt_session(manager.run_root.parent, "run-1")
    assert resolved.link.document["provider"]["name"] == provider



def test_lookup_revalidates_frozen_profile_conf(tmp_path: Path) -> None:
    from orchestrator.prompt_session import resolve_prompt_session

    setup = _historical_run(tmp_path, provider="omp_no_tools")
    manager = setup[0]
    published = manager.run_root / "provider_sessions" / "task__v1.session-link.json"
    link = parse_session_link_bytes(published.read_bytes())
    runs = manager.run_root.parent
    assert resolve_prompt_session(runs, "run-1").run_id == "run-1"
    conf_root = manager.run_root / link.document["paths"]["conf"]
    target = conf_root / "config.yml"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        resolve_prompt_session(runs, "run-1")



def test_no_tools_private_conf_capture_is_reused_without_reopening_neutral(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.prompt_session_scaffold import verify_private_scaffold

    resolved, private = _real_private_resolved(tmp_path, provider="omp_no_tools")
    original = (private / ".omp-conf" / "config.yml").read_bytes()
    monkeypatch.setattr(
        "orchestrator.providers.omp_launch.neutral_conf_root",
        lambda: (_ for _ in ()).throw(AssertionError("neutral conf reopened")),
    )
    descriptor = os.open(private, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        captured = verify_private_scaffold(descriptor, resolved.link)
        reused = verify_private_scaffold(descriptor, resolved.link)
        assert reused.files[".omp-conf/config.yml"] == captured.files[".omp-conf/config.yml"] == original
    finally:
        os.close(descriptor)



@pytest.mark.parametrize("planted", ("../x", {}))
def test_lookup_rejects_unsafe_persisted_observed_relpath(
    tmp_path: Path, planted: object
) -> None:
    from orchestrator.prompt_session import resolve_prompt_session

    setup = _historical_run(tmp_path)
    manager = setup[0]
    metadata_path = manager.run_root / "provider_sessions" / "task__v1.json"
    metadata = json.loads(metadata_path.read_bytes())
    metadata["parser_summary"]["launch_frame"]["observed"][
        "child_relpaths"
    ].insert(0, planted)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        resolve_prompt_session(manager.run_root.parent, "run-1")



def test_r6_publish_resolve_advised_tree_imports_only_primary(tmp_path: Path) -> None:
    from orchestrator.prompt_session import resolve_prompt_session

    setup = _historical_run(
        tmp_path, provider="omp_conf",
        plant="advised",
    )
    manager = setup[0]
    resolved = resolve_prompt_session(manager.run_root.parent, "run-1")
    assert resolved.link.document["provider"]["name"] == "omp_conf"
    stem = PRIMARY[: -len(".jsonl")]
    frame = setup[3]
    assert frame["observed"] == {
        "advisor_relpaths": [f"{stem}/__advisor.jsonl"],
        "child_relpaths": [],
    }



def test_r6_publish_resolve_advised_fanout_imports_only_primary(tmp_path: Path) -> None:
    from orchestrator.prompt_session import resolve_prompt_session

    setup = _historical_run(
        tmp_path, provider="omp_conf",
        plant="advised-fanout",
    )
    manager = setup[0]
    resolved = resolve_prompt_session(manager.run_root.parent, "run-1")
    assert resolved.link.document["provider"]["name"] == "omp_conf"
    stem = PRIMARY[: -len(".jsonl")]
    frame = setup[3]
    assert frame["observed"] == {
        "advisor_relpaths": [f"{stem}/__advisor.jsonl"],
        "child_relpaths": [f"{stem}/alpha.jsonl", f"{stem}/beta.jsonl"],
    }
