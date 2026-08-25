"""Closed state, metadata, adapter-frame, and scaffold launch agreement."""
from __future__ import annotations
import os
from typing import Any
from orchestrator.prompt_session_scaffold import capture_no_tools_conf_authority
from orchestrator.providers.omp_pin import OMP_BINARY_PIN
from orchestrator.providers.omp_launch_contract import (
    POSITIVE_ENV_NAMES,
    build_fresh_adapter_argv,
    resolved_adapter_command,
    valid_fresh_child_cwd,
    valid_observed_relpaths,
)

_METADATA_KEYS = frozenset({
    "run_id", "provider", "step_name", "step_id", "visit_count", "mode",
    "step_status", "publication_state", "session_id", "metadata_mode",
    "command_variant", "resolved_command", "started_at", "updated_at",
    "captured_transport_bytes", "parser_summary", "transport_spool_path",
})
_FRAME_KEYS = frozenset({
    "type", "lane", "persistence", "binary", "child", "session", "conf",
    "confinement", "observed",
})


def _error(detail: str):
    from orchestrator.prompt_session import PromptSessionError
    return PromptSessionError("session_link_invalid", detail)


def _pin_object() -> dict[str, str]:
    return {
        "platform": OMP_BINARY_PIN.platform,
        "arch": OMP_BINARY_PIN.arch,
        "version": OMP_BINARY_PIN.version,
        "sha256": OMP_BINARY_PIN.executable_sha256,
    }




def _validate_session_artifact(
    state: dict[str, Any],
    metadata: dict[str, Any],
    session_id: str,
    step_id: str,
) -> None:
    artifact_versions = state.get("artifact_versions")
    versions = (
        artifact_versions.get("omp_session")
        if isinstance(artifact_versions, dict)
        else None
    )
    if not isinstance(versions, list) or not versions:
        raise _error("run state lacks omp_session artifact lineage")
    expected_keys = {
        "version", "value", "producer", "producer_name", "step_index"
    }
    for index, row in enumerate(versions, 1):
        if (
            not isinstance(row, dict)
            or set(row) != expected_keys
            or type(row.get("version")) is not int
            or row["version"] != index
            or type(row.get("step_index")) is not int
        ):
            raise _error("omp_session artifact lineage is malformed")
    latest = versions[-1]
    if (
        latest["value"] != session_id
        or latest["producer"] != step_id
        or latest["producer_name"] != metadata.get("step_name")
    ):
        raise _error("omp_session artifact disagrees with selected visit")


def _validate_confinement(lane: str, confinement: object) -> None:
    if lane in ("ambient", "ambient-unrestricted"):
        if confinement is not None:
            raise _error("ambient frame has confinement")
        return
    if (
        not isinstance(confinement, dict)
        or set(confinement) != {
            "schema_version", "landlock_abi", "policy_sha256"
        }
        or confinement.get("schema_version") != "omp_write_confinement.v1"
        or type(confinement.get("landlock_abi")) is not int
        or confinement["landlock_abi"] < 3
        or not isinstance(confinement.get("policy_sha256"), str)
        or len(confinement["policy_sha256"]) != 64
        or any(ch not in "0123456789abcdef" for ch in confinement["policy_sha256"])
    ):
        raise _error("profile confinement is invalid")


def validate_publication_agreement(
    *,
    state: dict[str, Any],
    metadata: dict[str, Any],
    verification,
    run_id: str,
    visit_key: str,
    conf_digest: str | None,
    private_snapshot_fd: int,
    run_root: str,
    workflow_workspace: str,
):
    """Return the admitted frame and step id after complete agreement."""
    from orchestrator.prompt_session import _LANES
    if set(metadata) != _METADATA_KEYS:
        raise _error("provider metadata is not the closed minimized shape")
    step_id = metadata.get("step_id")
    visit_count = metadata.get("visit_count")
    canonical_visit = (
        f"{step_id.replace('/', '_')}__v{visit_count}"
        if isinstance(step_id, str) and type(visit_count) is int
        else None
    )
    if (
        metadata.get("run_id") != run_id
        or metadata.get("provider") != verification.provider
        or metadata.get("mode") != "fresh"
        or metadata.get("step_status") != "completed"
        or metadata.get("publication_state") != "published"
        or metadata.get("metadata_mode") != "omp_json_stdout"
        or metadata.get("command_variant") != "fresh_command"
        or not isinstance(metadata.get("resolved_command"), str)
        or metadata.get("captured_transport_bytes") != 0
        or metadata.get("transport_spool_path") is not None
        or canonical_visit != visit_key
    ):
        raise _error("state and provider metadata disagree")
    parser = metadata.get("parser_summary")
    frame = parser.get("launch_frame") if isinstance(parser, dict) else None
    if not isinstance(frame, dict) or set(frame) != _FRAME_KEYS:
        raise _error("adapter launch frame is not closed")
    child, session = frame.get("child"), frame.get("session")
    binary, conf, observed = frame.get("binary"), frame.get("conf"), frame.get("observed")
    lane = _LANES[verification.provider]
    if (
        frame.get("type") != "orchestrator.omp_launch.v1"
        or frame.get("lane") != lane
        or frame.get("persistence") != "fresh"
        or binary != _pin_object()
        or not isinstance(child, dict)
        or set(child) != {"argv", "cwd", "env_names", "exit_code"}
        or child.get("exit_code") != 0
        or not isinstance(child.get("argv"), list)
        or not isinstance(child.get("env_names"), list)
        or child["env_names"] != list(POSITIVE_ENV_NAMES)
        or not isinstance(session, dict)
        or set(session) != {"id", "visit_key", "primary_relpath", "primary_sha256"}
        or session.get("visit_key") != visit_key
        or session.get("id") != metadata.get("session_id")
        or not isinstance(session.get("primary_relpath"), str)
        or not isinstance(session.get("primary_sha256"), str)
        or len(session["primary_sha256"]) != 64
        or not isinstance(conf, dict)
        or set(conf) != {"manifest_sha256"}
        or conf.get("manifest_sha256") != conf_digest
        or not isinstance(observed, dict)
        or set(observed) != {"advisor_relpaths", "child_relpaths"}
        or observed.get("advisor_relpaths") != []
        or not valid_observed_relpaths(observed.get("child_relpaths"))
        or session["primary_relpath"] not in observed["child_relpaths"]
    ):
        raise _error("metadata and adapter frame disagree")
    live_root = os.path.join(run_root, "provider_sessions", visit_key)
    conf_leaf = ".omp-conf" if verification.provider == "omp_no_tools" else "conf"
    conf_root = os.path.join(run_root, "prompt-inputs", conf_leaf)
    frozen_conf = None
    if verification.provider == "omp_no_tools":
        identity, digest = capture_no_tools_conf_authority(private_snapshot_fd)
        if digest != conf_digest:
            raise _error("no-tools adapter conf authority disagrees")
        frozen_conf = (identity[0], identity[1], digest)
    expected_conf_root = (
        conf_root
        if verification.provider in ("omp_no_tools", "omp_conf")
        else None
    )
    try:
        expected_argv = build_fresh_adapter_argv(
            verification.provider,
            verification.model,
            session_dir=live_root,
            conf_root=expected_conf_root,
            frozen_conf=frozen_conf,
        )
    except ValueError as exc:
        raise _error(str(exc)) from exc
    if (
        tuple(child["argv"]) != expected_argv
        or metadata["resolved_command"] != resolved_adapter_command(expected_argv)
        or not valid_fresh_child_cwd(
            verification.provider, child.get("cwd"), workflow_workspace
        )
    ):
        raise _error("adapter launch envelope disagrees")
    _validate_confinement(lane, frame.get("confinement"))
    _validate_session_artifact(state, metadata, session["id"], step_id)
    return frame, step_id


__all__ = ["validate_publication_agreement"]
