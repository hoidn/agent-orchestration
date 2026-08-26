"""Descriptor-safe exact lookup of active linked OMP primary sessions."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import Any

from orchestrator._common.safe_tree import SafeTreeError, read_regular_file
from orchestrator.providers.omp_conf import OmpConfError, admit_conf_tree
from orchestrator.providers.omp_observation import is_advisor_name, is_child_journal
from orchestrator.providers.omp_protocol import loads_strict
from orchestrator.providers.omp_pin import OMP_BINARY_PIN
from orchestrator.providers.omp_observation import (
    OmpObservationError,
    observe_close,
    recognized_preset_topologies,
)
from orchestrator.providers.omp_session import OmpSessionError, parse_journal_bytes
from orchestrator.providers.omp_session_manifest import build_session_manifest
from orchestrator.prompt_session_chain import (
    read_continuations,
    read_manifest_bound,
    validate_continuation_journals,
)
from orchestrator.prompt_session_scaffold import capture_no_tools_conf_authority
from orchestrator.providers.omp_launch_contract import (
    build_fresh_adapter_argv,
    resolved_adapter_command,
    valid_fresh_child_cwd,
    valid_launch_env_names,
    valid_observed_relpaths,
)
from orchestrator.prompt_session import (
    PromptSessionError,
    ResolvedPrimary,
    _identifier,
    parse_session_link_bytes,
    validate_continuation_chain,
)
_FRAME_KEYS = {
    "type", "lane", "persistence", "binary", "child", "session", "conf",
    "confinement", "observed",
}
_CHILD_KEYS = {"argv", "cwd", "env_names", "exit_code"}
_SESSION_FRAME_KEYS = {
    "id", "visit_key", "primary_relpath", "primary_sha256"
}
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_METADATA_KEYS = frozenset(
    {
        "run_id", "provider", "step_name", "step_id", "visit_count", "mode",
        "step_status", "publication_state", "session_id", "metadata_mode",
        "command_variant", "resolved_command", "started_at", "updated_at",
        "captured_transport_bytes", "parser_summary", "transport_spool_path",
    }
)


def _invalid(detail: str, cause: BaseException | None = None) -> PromptSessionError:
    error = PromptSessionError("session_link_invalid", detail)
    if cause is not None:
        error.__cause__ = cause
    return error


def _open_child(root_fd: int, relative: str) -> int:
    descriptor = os.dup(root_fd)
    try:
        for part in PurePosixPath(relative).parts:
            child = os.open(part, _DIR_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except OSError as exc:
        os.close(descriptor)
        raise _invalid(f"cannot open linked directory {relative!r}", exc)




def _validate_metadata(metadata: object, *, run_name: str, link) -> dict[str, Any]:
    if not isinstance(metadata, dict) or set(metadata) != _METADATA_KEYS:
        raise _invalid("metadata is not the closed published shape")
    try:
        visit_count = int(link.visit_key.rpartition("__v")[2])
    except ValueError as exc:
        raise _invalid("visit key has no numeric visit", exc)
    if (
        metadata["run_id"] != run_name
        or metadata["provider"] != link.document["provider"]["name"]
        or metadata["step_id"] != link.document["step_id"]
        or metadata["visit_count"] != visit_count
        or metadata["mode"] != "fresh"
        or metadata["step_status"] != "completed"
        or metadata["publication_state"] != "published"
        or metadata["session_id"] != link.session_id
        or metadata["metadata_mode"] != "omp_json_stdout"
        or metadata["command_variant"] != "fresh_command"
        or metadata["captured_transport_bytes"] != 0
        or metadata["transport_spool_path"] is not None
    ):
        raise _invalid("metadata disagrees with link")
    return metadata


def _validate_state_artifact(
    state: dict[str, Any],
    metadata: dict[str, Any],
    link,
) -> None:
    versions = state.get("artifact_versions")
    rows = versions.get("omp_session") if isinstance(versions, dict) else None
    latest = rows[-1] if isinstance(rows, list) and rows else None
    if (
        not isinstance(latest, dict)
        or set(latest) != {
            "version", "value", "producer", "producer_name", "step_index"
        }
        or latest.get("value") != link.session_id
        or latest.get("producer") != link.document["step_id"]
        or latest.get("producer_name") != metadata.get("step_name")
    ):
        raise _invalid("run state omp_session artifact disagrees")


def _validate_frame(metadata: dict[str, Any], link, run_fd: int, run_root: Path):
    parser = metadata["parser_summary"]
    frame = parser.get("launch_frame") if isinstance(parser, dict) else None
    child = frame.get("child") if isinstance(frame, dict) else None
    session = frame.get("session") if isinstance(frame, dict) else None
    conf = frame.get("conf") if isinstance(frame, dict) else None
    observed = frame.get("observed") if isinstance(frame, dict) else None
    provider = link.document["provider"]["name"]
    conf_leaf = ".omp-conf" if provider == "omp_no_tools" else "conf"
    private_conf = run_root / "prompt-inputs" / conf_leaf
    frozen = None
    if provider == "omp_no_tools":
        private_fd = _open_child(run_fd, "prompt-inputs")
        try:
            identity, digest = capture_no_tools_conf_authority(private_fd)
        finally:
            os.close(private_fd)
        frozen = (identity[0], identity[1], digest)
    expected_conf = str(private_conf) if provider in ("omp_no_tools", "omp_conf") else None
    try:
        expected_argv = build_fresh_adapter_argv(
            provider,
            link.document["provider"]["model"],
            session_dir=str(run_root / link.document["paths"]["live"]),
            conf_root=expected_conf,
            frozen_conf=frozen,
        )
    except ValueError as exc:
        raise _invalid("launch frame cannot be reconstructed", exc)
    if (
        not isinstance(frame, dict)
        or set(frame) != _FRAME_KEYS
        or frame.get("type") != "orchestrator.omp_launch.v1"
        or frame.get("lane") != link.document["provider"]["lane"]
        or frame.get("persistence") != "fresh"
        or frame.get("binary") != {
            "platform": OMP_BINARY_PIN.platform,
            "arch": OMP_BINARY_PIN.arch,
            "version": OMP_BINARY_PIN.version,
            "sha256": OMP_BINARY_PIN.executable_sha256,
        }
        or frame.get("confinement") != link.document["confinement"]
        or not isinstance(child, dict)
        or set(child) != _CHILD_KEYS
        or tuple(child.get("argv") or ()) != expected_argv
        or child.get("argv") != link.document["launch"]["argv"]
        or not valid_launch_env_names(provider, child.get("env_names"))
        or child.get("env_names") != link.document["launch"]["env_names"]
        or child.get("exit_code") != 0
        or metadata.get("resolved_command") != resolved_adapter_command(expected_argv)
        or not valid_fresh_child_cwd(
            provider, child.get("cwd"), link.document["workflow_workspace"]
        )
        or not isinstance(session, dict)
        or set(session) != _SESSION_FRAME_KEYS
        or session.get("id") != link.session_id
        or session.get("visit_key") != link.visit_key
        or session.get("primary_relpath") != link.primary_basename
        or not isinstance(conf, dict)
        or set(conf) != {"manifest_sha256"}
        or conf.get("manifest_sha256")
        != link.document["digests"]["conf_manifest_sha256"]
        or not isinstance(observed, dict)
        or set(observed) != {"advisor_relpaths", "child_relpaths"}
                or not valid_observed_relpaths(observed.get("advisor_relpaths"))
        or not valid_observed_relpaths(observed.get("child_relpaths"))
        or link.primary_basename in observed["advisor_relpaths"]
        or link.primary_basename in observed["child_relpaths"]
    ):
        raise _invalid("launch frame disagrees with link")
    return frame

def _candidate(
    run_fd: int,
    run_name: str,
    run_root: Path,
    link_name: str,
    link_bytes: bytes,
    sessions_fd: int,
):
    link = parse_session_link_bytes(link_bytes)
    if link_name != f"{link.visit_key}.session-link.json" or link.run_id != run_name:
        raise _invalid("link filename or run directory disagrees")
    try:
        state = loads_strict(read_regular_file(run_fd, "state.json").decode("utf-8"))
        metadata = loads_strict(
            read_regular_file(run_fd, link.document["paths"]["metadata"]).decode("utf-8")
        )
    except (SafeTreeError, UnicodeDecodeError, ValueError) as exc:
        raise _invalid("state or metadata cannot be admitted", exc)
    if not isinstance(state, dict) or state.get("run_id") != run_name or state.get("status") != "completed":
        raise _invalid("run state is not completed")
    metadata = _validate_metadata(metadata, run_name=run_name, link=link)
    _validate_state_artifact(state, metadata, link)
    frame = _validate_frame(metadata, link, run_fd, run_root)
    try:
        os.stat(f"{link.visit_key}.transport.log", dir_fd=sessions_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise _invalid("transport spool cannot be checked", exc)
    else:
        raise _invalid("transport spool still exists")

    snapshot_fd = _open_child(run_fd, link.document["paths"]["snapshot"])
    try:
        snapshot_manifest = build_session_manifest(snapshot_fd)
        try:
            report = observe_close(
                session_root_fd=snapshot_fd,
                stdout_session_id=link.session_id,
                conf_manifest_sha256=link.document["digests"]["conf_manifest_sha256"],
                recognized_topologies=recognized_preset_topologies(),
                isolated_worktree_root=None,
            )
        except OmpObservationError as exc:
            raise _invalid(f"frozen snapshot fails close-time observation: {exc}", exc)
        if (
            report.primary_relpath != link.primary_basename
            or list(report.advisor_relpaths) != frame["observed"]["advisor_relpaths"]
            or list(report.child_relpaths) != frame["observed"]["child_relpaths"]
        ):
            raise _invalid("launch inventory disagrees with frozen snapshot")
        if snapshot_manifest.manifest_sha256 != link.document["digests"]["snapshot_manifest_sha256"]:
            raise _invalid("snapshot manifest disagrees")
        original = read_manifest_bound(
            snapshot_fd, snapshot_manifest, link.primary_basename
        )
    except OmpSessionError as exc:
        raise _invalid("snapshot cannot be admitted", exc)
    finally:
        os.close(snapshot_fd)
    initial_sha = hashlib.sha256(original).hexdigest()
    if frame["session"]["primary_sha256"] != initial_sha:
        raise _invalid("snapshot primary disagrees with launch frame")
    continuation_snapshot = read_continuations(sessions_fd, link.visit_key)
    records = continuation_snapshot[0]
    active = validate_continuation_chain(
        link_bytes,
        records,
        initial_journal_sha256=initial_sha,
        run_root=run_root,
    )
    if active.blocked:
        return None, True

    live_fd = _open_child(run_fd, link.document["paths"]["live"])
    try:
        live_manifest = build_session_manifest(live_fd)
        if live_manifest.manifest_sha256 != active.live_manifest_sha256:
            raise _invalid("live manifest disagrees")
        journal_bytes = read_manifest_bound(
            live_fd, live_manifest, active.primary_basename
        )
        validate_continuation_journals(live_fd, live_manifest, records)
    except OmpSessionError as exc:
        raise _invalid("live tree cannot be admitted", exc)
    finally:
        os.close(live_fd)

    conf_path = link.document["paths"]["conf"]
    if conf_path is not None:
        conf_fd = _open_child(run_fd, conf_path)
        try:
            conf_digest = admit_conf_tree(conf_fd).manifest_sha256
        except (OSError, OmpConfError, SafeTreeError, TypeError, ValueError) as exc:
            raise _invalid("conf tree cannot be admitted", exc)
        finally:
            os.close(conf_fd)
        if conf_digest != link.document["digests"]["conf_manifest_sha256"]:
            raise _invalid("conf manifest disagrees")

    try:
        journal = parse_journal_bytes(journal_bytes, relpath=active.primary_basename)
    except OmpSessionError as exc:
        raise _invalid("active journal cannot be parsed", exc)
    if (
        journal.header.id != active.session_id
        or hashlib.sha256(journal_bytes).hexdigest() != active.journal_sha256
        or is_advisor_name(active.primary_basename)
        or is_child_journal(journal)
    ):
        raise _invalid("active primary disagrees")
    if read_continuations(sessions_fd, link.visit_key) != continuation_snapshot:
        raise PromptSessionError(
            "session_continuation_invalid", "continuation changed during lookup"
        )
    run_stat = os.fstat(run_fd)
    return (
        ResolvedPrimary(
            run_id=run_name,
            visit_key=link.visit_key,
            session_id=active.session_id,
            primary_basename=active.primary_basename,
            link=link,
            run_root=run_root,
            run_identity=(run_stat.st_dev, run_stat.st_ino),
            journal_bytes=journal_bytes,
            initial_journal_sha256=initial_sha,
        ),
        active.blocked,
    )


def _state_matches(run_fd: int, run_name: str) -> bool:
    try:
        state = loads_strict(read_regular_file(run_fd, "state.json").decode("utf-8"))
    except (SafeTreeError, UnicodeDecodeError, ValueError):
        return False
    return isinstance(state, dict) and state.get("run_id") == run_name


def _run_candidates(runs_fd: int, run_name: str, runs_root: Path):
    run_fd = os.open(run_name, _DIR_FLAGS, dir_fd=runs_fd)
    try:
        sessions_fd = os.open("provider_sessions", _DIR_FLAGS, dir_fd=run_fd)
        try:
            names = sorted(
                name for name in os.listdir(sessions_fd)
                if name.endswith(".session-link.json")
            )
            return [
                _candidate(
                    run_fd, run_name, Path(runs_root) / run_name, name,
                    read_regular_file(sessions_fd, name), sessions_fd,
                )
                for name in names
            ]
        finally:
            os.close(sessions_fd)
    finally:
        os.close(run_fd)


def _run_names(runs_fd: int) -> list[str]:
    names = []
    try:
        entries = os.listdir(runs_fd)
    except OSError as exc:
        raise PromptSessionError("prompt_session_not_found") from exc
    for name in entries:
        try:
            descriptor = os.open(name, _DIR_FLAGS, dir_fd=runs_fd)
        except OSError:
            continue
        os.close(descriptor)
        names.append(name)
    return sorted(names)


def _ambiguous(matches) -> PromptSessionError:
    identities = ", ".join(f"{item.run_id}/{item.visit_key}" for item in matches)
    return PromptSessionError("prompt_session_ambiguous", identities)


def resolve_prompt_session(
    runs_root: Path, identifier: str
) -> ResolvedPrimary:
    """Resolve exact valid run, then session id, then primary basename."""
    value = _identifier(identifier)
    try:
        runs_fd = os.open(Path(runs_root), _DIR_FLAGS)
    except OSError as exc:
        raise PromptSessionError("prompt_session_not_found") from exc
    try:
        run_names = _run_names(runs_fd)
        if value in run_names:
            try:
                run_fd = os.open(value, _DIR_FLAGS, dir_fd=runs_fd)
            except OSError as exc:
                raise _invalid("run directory cannot be reopened", exc)
            try:
                state_match = _state_matches(run_fd, value)
            finally:
                os.close(run_fd)
            if state_match:
                try:
                    matches = _run_candidates(runs_fd, value, runs_root)
                except (OSError, SafeTreeError, OmpSessionError, OmpConfError, ValueError) as exc:
                    raise _invalid("run candidate cannot be admitted", exc)
                if len(matches) != 1:
                    raise PromptSessionError("prompt_session_not_found")
                candidate, blocked = matches[0]
                if blocked:
                    raise PromptSessionError("prompt_session_blocked")
                assert candidate is not None
                return candidate

        candidates = []
        for run_name in run_names:
            try:
                candidates.extend(_run_candidates(runs_fd, run_name, runs_root))
            except (
                OSError, SafeTreeError, OmpSessionError, OmpConfError,
                PromptSessionError, UnicodeDecodeError, ValueError,
            ):
                continue
        for attribute in ("session_id", "primary_basename"):
            tier = [
                item for item, blocked in candidates
                if not blocked and getattr(item, attribute) == value
            ]
            if tier:
                if len(tier) > 1:
                    raise _ambiguous(tier)
                return tier[0]
        raise PromptSessionError("prompt_session_not_found")
    finally:
        os.close(runs_fd)


__all__ = ["resolve_prompt_session"]
