"""Task 9 publication and private-authority regressions."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from orchestrator.prompt_session import (
    PromptSessionError,
    parse_session_link_bytes,
    publish_prompt_run_link,
    with_private_execution_authority,
)

TS = "2026-08-23T22:33:31.340Z"
HEX = "a" * 64
SESSION_ID = "11111111-1111-7111-8111-111111111111"
PRIMARY = f"2026-08-23T22-33-31-340Z_{SESSION_ID}.jsonl"


def _slot() -> str:
    obj = {"type": "title", "v": 1, "title": "", "updatedAt": TS, "pad": ""}
    base = json.dumps(obj, separators=(",", ":")) + "\n"
    obj["pad"] = " " * (256 - len(base.encode()))
    result = json.dumps(obj, separators=(",", ":")) + "\n"
    assert len(result.encode()) == 256
    return result


def _entry(kind: str, entry_id: str, parent: str | None, **extra: object) -> dict:
    return {"type": kind, "id": entry_id, "parentId": parent, "timestamp": TS, **extra}


def _user(content: object) -> dict:
    return _entry(
        "message", "u", None,
        message={"role": "user", "content": content, "timestamp": 1},
    )


def _journal(*entries: dict, session_id: str = SESSION_ID) -> bytes:
    header = {
        "type": "session", "version": 3, "id": session_id,
        "timestamp": TS, "cwd": "/workspace",
    }
    lines = [json.dumps(header, separators=(",", ":")), *(
        json.dumps(row, separators=(",", ":")) for row in entries
    )]
    return (_slot() + "\n".join(lines) + "\n").encode()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _setup_publication(tmp_path: Path, *, provider: str = "omp"):
    from orchestrator.prompt_contract import default_semantic_contract
    from orchestrator.prompt_scaffold import (
        ScaffoldInputs,
        generate_scaffold,
        materialize_run_snapshot,
    )
    from orchestrator.providers.omp_pin import OMP_BINARY_PIN
    from orchestrator.state import StateManager

    workspace = tmp_path / "workspace"
    generated = workspace / "workflows" / "generated"
    generated.mkdir(parents=True)
    prompt = b"authored prompt"
    conf_manifest = None
    if provider == "omp_conf":
        from orchestrator.providers.omp_conf import admit_conf_tree

        authored_conf = tmp_path / "authored-conf"
        authored_conf.mkdir()
        fixture = Path(__file__).parent / "fixtures" / "omp" / "conf" / "neutral"
        (authored_conf / "config.yml").write_bytes(
            (fixture / "config.yml").read_bytes()
        )
        conf_fd = os.open(
            authored_conf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            conf_manifest = admit_conf_tree(conf_fd)
        finally:
            os.close(conf_fd)
    inputs = ScaffoldInputs(
        prompt_sha256=hashlib.sha256(prompt).hexdigest(),
        contract=default_semantic_contract(),
        provider=provider,
        model="gpt-5.6-sol",
        conf_manifest=conf_manifest,
        slug="prompt",
        pin=OMP_BINARY_PIN,
    )
    scaffold = generate_scaffold(
        generated_root=generated,
        inputs=inputs,
        prompt_bytes=prompt,
        authoring={"mode": "exact"},
    )
    verification = with_private_execution_authority(scaffold.verification)
    runs = workspace / ".orchestrate" / "runs"
    manager = StateManager(workspace, run_id="run-1", state_dir=runs)
    private = manager.run_root / "prompt-inputs"
    private.mkdir(parents=True)
    snapshot = materialize_run_snapshot(verification, private)
    snapshot.close()

    sessions = manager.run_root / "provider_sessions"
    live = sessions / "task__v1"
    live.mkdir(parents=True)
    journal = _journal(_user(prompt.decode()))
    (live / PRIMARY).write_bytes(journal)
    state = {
        "run_id": "run-1",
        "status": "completed",
        "artifact_versions": {
            "omp_session": [{
                "version": 1,
                "value": SESSION_ID,
                "producer": "task",
                "producer_name": "task",
                "step_index": 0,
            }],
        },
    }
    (manager.run_root / "state.json").write_text(
        json.dumps(state),
        encoding="utf-8",
    )
    from orchestrator.providers.omp_launch_contract import (
        POSITIVE_ENV_NAMES,
        build_fresh_adapter_argv,
        resolved_adapter_command,
    )
    lane = {
        "omp": "ambient",
        "omp_unrestricted_workspace": "ambient-unrestricted",
        "omp_no_tools": "no-tools",
        "omp_conf": "conf",
    }[provider]
    conf_digest = (
        inputs.conf_manifest_sha256
        if provider in ("omp_no_tools", "omp_conf")
        else None
    )
    confinement = None
    frozen = None
    conf_root = None
    child_cwd = str(workspace)
    if provider in ("omp_no_tools", "omp_conf"):
        confinement = {
            "schema_version": "omp_write_confinement.v1",
            "landlock_abi": 3,
            "policy_sha256": "b" * 64,
        }
        child_cwd = str(
            workspace / ("omp-empty-" + "1" * 16 + "-" + "2" * 16)
        )
    if provider == "omp_no_tools":
        from orchestrator.prompt_session_scaffold import (
            capture_no_tools_conf_authority,
        )
        root_fd = os.open(private, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            conf_identity, captured_digest = capture_no_tools_conf_authority(root_fd)
        finally:
            os.close(root_fd)
        frozen = (conf_identity[0], conf_identity[1], captured_digest)
        conf_root = str(private / ".omp-conf")
    elif provider == "omp_conf":
        conf_root = str(private / "conf")
    argv = list(
        build_fresh_adapter_argv(
            provider,
            verification.model,
            session_dir=str(live),
            conf_root=conf_root,
            frozen_conf=frozen,
        )
    )
    frame = {
        "type": "orchestrator.omp_launch.v1",
        "lane": lane,
        "persistence": "fresh",
        "binary": {
            "platform": OMP_BINARY_PIN.platform,
            "arch": OMP_BINARY_PIN.arch,
            "version": OMP_BINARY_PIN.version,
            "sha256": OMP_BINARY_PIN.executable_sha256,
        },
        "child": {
            "argv": argv,
            "cwd": child_cwd,
            "env_names": list(POSITIVE_ENV_NAMES),
            "exit_code": 0,
        },
        "session": {
            "id": SESSION_ID,
            "visit_key": "task__v1",
            "primary_relpath": PRIMARY,
            "primary_sha256": hashlib.sha256(journal).hexdigest(),
        },
        "conf": {"manifest_sha256": conf_digest},
        "confinement": confinement,
        "observed": {"advisor_relpaths": [], "child_relpaths": [PRIMARY]},
    }
    metadata = {
        "run_id": "run-1",
        "provider": provider,
        "step_name": "task",
        "step_id": "task",
        "visit_count": 1,
        "mode": "fresh",
        "step_status": "completed",
        "publication_state": "published",
        "session_id": SESSION_ID,
        "metadata_mode": "omp_json_stdout",
        "command_variant": "fresh_command",
        "resolved_command": resolved_adapter_command(argv),
        "started_at": TS,
        "updated_at": TS,
        "captured_transport_bytes": 0,
        "parser_summary": {"launch_frame": frame},
        "transport_spool_path": None,
    }
    (sessions / "task__v1.json").write_text(json.dumps(metadata), encoding="utf-8")
    run_stat = manager.run_root.stat()
    return (
        manager,
        scaffold.path,
        verification,
        frame,
        metadata,
        (run_stat.st_dev, run_stat.st_ino),
    )


def _publish(setup):
    manager, scaffold, verification, _frame, _metadata, identity = setup
    private_fd = os.open(
        manager.run_root / "prompt-inputs",
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    try:
        return publish_prompt_run_link(
            manager,
            workflow_workspace=manager.workspace,
            scaffold_path=scaffold,
            private_snapshot_fd=private_fd,
            verification=verification,
            expected_run_identity=identity,
        )
    finally:
        os.close(private_fd)


def test_publish_freezes_live_and_binds_captured_scaffold(tmp_path: Path) -> None:
    setup = _setup_publication(tmp_path)
    published = _publish(setup)
    link = parse_session_link_bytes(published.read_bytes())
    assert link.document["digests"]["authored_prompt_sha256"] == hashlib.sha256(
        b"authored prompt"
    ).hexdigest()


@pytest.mark.parametrize(
    "provider",
    ("omp", "omp_unrestricted_workspace", "omp_no_tools", "omp_conf"),
)
def test_public_lane_matrix_publishes_then_resolves_exact(
    tmp_path: Path, provider: str
) -> None:
    from orchestrator.prompt_session import resolve_prompt_session

    setup = _setup_publication(tmp_path, provider=provider)
    manager = setup[0]
    _publish(setup)
    resolved = resolve_prompt_session(manager.run_root.parent, "run-1")
    assert resolved.link.document["provider"]["name"] == provider


@pytest.mark.parametrize("target", ("private", "public"))
def test_publish_rejects_post_capture_scaffold_mutation(
    tmp_path: Path,
    target: str,
) -> None:
    setup = _setup_publication(tmp_path)
    manager, scaffold, _verification, _frame, _metadata, _identity = setup
    path = (
        manager.run_root / "prompt-inputs" / "run.orc"
        if target == "private"
        else scaffold / "run.orc"
    )
    path.chmod(0o600)
    path.write_bytes(path.read_bytes() + b" ")
    path.chmod(0o400 if target == "private" else 0o644)
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        _publish(setup)
    assert not (
        manager.run_root / "provider_sessions" / "task__v1.snapshot"
    ).exists()


@pytest.mark.parametrize(
    "mismatch",
    (
        "provider", "model", "spool", "extra-argv", "env", "cwd",
        "observed-path", "observed-type", "observed-extra",
    ),
)
def test_publish_rejects_metadata_frame_or_spool_disagreement(
    tmp_path: Path,
    mismatch: str,
) -> None:
    setup = _setup_publication(tmp_path)
    manager, _scaffold, _verification, frame, metadata, _identity = setup
    if mismatch == "provider":
        metadata["provider"] = "omp_unrestricted_workspace"
    elif mismatch == "model":
        model_index = frame["child"]["argv"].index("--model") + 1
        frame["child"]["argv"][model_index] = "different-model"
    elif mismatch == "spool":
        (
            manager.run_root / "provider_sessions" / "task__v1.transport.log"
        ).write_bytes(b"")
    elif mismatch == "extra-argv":
        frame["child"]["argv"].extend(["--unknown", "value"])
    elif mismatch == "env":
        frame["child"]["env_names"].append("UNOWNED")
        frame["child"]["env_names"].sort()
    elif mismatch == "cwd":
        frame["child"]["cwd"] = "/wrong"
    elif mismatch == "observed-path":
        frame["observed"]["child_relpaths"].insert(0, "../x")
    elif mismatch == "observed-extra":
        frame["observed"]["child_relpaths"].append("extra.jsonl")
        frame["observed"]["child_relpaths"].sort()
    else:
        frame["observed"]["child_relpaths"].insert(0, {})
    metadata_path = manager.run_root / "provider_sessions" / "task__v1.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        _publish(setup)
    assert not (
        manager.run_root / "provider_sessions" / "task__v1.snapshot"
    ).exists()


def test_publish_collision_cleans_frozen_authority_and_allows_retry(
    tmp_path: Path,
) -> None:
    setup = _setup_publication(tmp_path)
    manager = setup[0]
    sessions = manager.run_root / "provider_sessions"
    link = sessions / "task__v1.session-link.json"
    link.write_bytes(b"existing")
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        _publish(setup)
    assert link.read_bytes() == b"existing"
    assert not (sessions / "task__v1.snapshot").exists()
    assert not (sessions / "task__v1.conf").exists()
    link.unlink()
    assert _publish(setup).exists()


@pytest.mark.parametrize("field", ("value", "producer"))
def test_publish_binds_persisted_session_artifact(
    tmp_path: Path,
    field: str,
) -> None:
    setup = _setup_publication(tmp_path)
    manager = setup[0]
    state_path = manager.run_root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["artifact_versions"]["omp_session"][0][field] = "different"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        _publish(setup)



def test_publish_accepts_authored_conf_launch_agreement(tmp_path: Path) -> None:
    from orchestrator.prompt_session import resolve_prompt_session

    setup = _setup_publication(tmp_path, provider="omp_conf")
    manager = setup[0]
    published = _publish(setup)
    link = parse_session_link_bytes(published.read_bytes())
    assert link.document["provider"]["name"] == "omp_conf"
    assert link.document["paths"]["conf"] == "provider_sessions/task__v1.conf"
    assert resolve_prompt_session(manager.run_root.parent, "run-1").run_id == "run-1"


def test_lookup_revalidates_frozen_profile_conf(tmp_path: Path) -> None:
    from orchestrator.prompt_session import resolve_prompt_session

    setup = _setup_publication(tmp_path, provider="omp_no_tools")
    manager = setup[0]
    published = _publish(setup)
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
    from orchestrator.prompt_contract import default_semantic_contract
    from orchestrator.prompt_scaffold import ScaffoldVerification

    original = b"advisor:\n  enabled: false\n"
    verification = ScaffoldVerification(
        identity=HEX, provider="omp_no_tools", model="gpt-5.6-sol",
        semantic_contract=default_semantic_contract(), files={"prompt.md": b"x"},
        conf_files={"config.yml": original}, manifest={}, manifest_bytes=b"{}\n",
    )
    monkeypatch.setattr(
        "orchestrator.providers.omp_launch.neutral_conf_root",
        lambda: (_ for _ in ()).throw(AssertionError("neutral conf reopened")),
    )
    captured = with_private_execution_authority(verification)
    reused = with_private_execution_authority(captured)
    assert reused.files[".omp-conf/config.yml"] == original


def test_scaffold_relpath_rejects_planted_workspace_symlink(tmp_path: Path) -> None:
    from orchestrator.prompt_session_publish import _scaffold_under_workspace

    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "generated").mkdir()
    (workspace / "workflows").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        _scaffold_under_workspace(workspace, workspace / "workflows" / "generated")


def test_publish_rejects_provider_sessions_swap_at_sink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.state import StateManager

    setup = _setup_publication(tmp_path)
    manager = setup[0]
    sessions = manager.run_root / "provider_sessions"
    detached = manager.run_root / "validated-provider-sessions"
    original = StateManager.publish_provider_session_link

    def swap_then_publish(self, *args, **kwargs):
        sessions.rename(detached)
        sessions.mkdir()
        return original(self, *args, **kwargs)

    monkeypatch.setattr(
        StateManager, "publish_provider_session_link", swap_then_publish
    )
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        _publish(setup)
    assert not list(sessions.glob("*.session-link.json"))
    assert (detached / "task__v1.json").exists()


@pytest.mark.parametrize("planted", ("../x", {}))
def test_lookup_rejects_unsafe_persisted_observed_relpath(
    tmp_path: Path, planted: object
) -> None:
    from orchestrator.prompt_session import resolve_prompt_session

    setup = _setup_publication(tmp_path)
    manager = setup[0]
    _publish(setup)
    metadata_path = manager.run_root / "provider_sessions" / "task__v1.json"
    metadata = json.loads(metadata_path.read_bytes())
    metadata["parser_summary"]["launch_frame"]["observed"][
        "child_relpaths"
    ].insert(0, planted)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        resolve_prompt_session(manager.run_root.parent, "run-1")
