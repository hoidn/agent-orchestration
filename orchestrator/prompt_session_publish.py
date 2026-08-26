"""Validated no-replace publication of Task 9 OMP session links."""
from __future__ import annotations
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from orchestrator._common.safe_tree import (
    SafeTreeError,
    copy_regular_file,
    read_regular_file,
    walk_regular_files,
)
from orchestrator.prompt_session_scaffold import (
    verify_captured_occupant,
    with_private_execution_authority,
)
from orchestrator.prompt_session_agreement import validate_publication_agreement
from orchestrator.providers.omp_conf import OmpConfError, admit_conf_tree
from orchestrator.providers.omp_protocol import loads_strict
from orchestrator.providers.omp_observation import (
    OmpObservationError,
    SESSION_TREE_MAX_BYTES,
    SESSION_TREE_MAX_DEPTH,
    SESSION_TREE_MAX_FILES,
    observe_close,
    recognized_preset_topologies,
)
from orchestrator.providers.omp_session import OmpSessionError, parse_journal_bytes
from orchestrator.providers.omp_session_manifest import build_session_manifest

_MAX_METADATA_FILES = 128
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _error(detail: str, cause: BaseException | None = None):
    from orchestrator.prompt_session import PromptSessionError
    result = PromptSessionError("session_link_invalid", detail)
    if cause is not None:
        result.__cause__ = cause
    return result


def _remove_tree(parent_fd: int, name: str) -> None:
    """Remove only the no-follow directory entry owned by this publication."""
    try:
        descriptor = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        return
    try:
        for child_name in os.listdir(descriptor):
            kind = os.stat(child_name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(kind.st_mode):
                _remove_tree(descriptor, child_name)
            else:
                os.unlink(child_name, dir_fd=descriptor)
    finally:
        os.close(descriptor)
    os.rmdir(name, dir_fd=parent_fd)


def _write_all(descriptor: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        count = os.write(descriptor, remaining)
        if count <= 0:
            raise OSError("session authority write made no progress")
        remaining = remaining[count:]


def _open_parents(root_fd: int, relative: str) -> tuple[int, list[int]]:
    descriptor = os.dup(root_fd)
    owned = [descriptor]
    for part in PurePosixPath(relative).parts[:-1]:
        try:
            os.mkdir(part, mode=0o700, dir_fd=descriptor)
        except FileExistsError:
            pass
        descriptor = os.open(part, _DIR_FLAGS, dir_fd=descriptor)
        owned.append(descriptor)
    return descriptor, owned
def _freeze_bytes(
    files: Mapping[str, bytes],
    parent_fd: int,
    name: str,
    modes: Mapping[str, int] | None = None,
):
    created = False
    target_fd = -1
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        created = True
        target_fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
        for relative in sorted(files, key=lambda item: item.encode("utf-8")):
            leaf_parent, owned = _open_parents(target_fd, relative)
            try:
                descriptor = os.open(
                    PurePosixPath(relative).name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL
                    | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=leaf_parent,
                )
                try:
                    _write_all(descriptor, files[relative])
                    os.fchmod(
                        descriptor,
                        0o644
                        if modes is None
                        else stat.S_IMODE(modes[relative]),
                    )
                finally:
                    os.close(descriptor)
            finally:
                for descriptor in reversed(owned):
                    os.close(descriptor)
        return build_session_manifest(target_fd)
    except BaseException:
        if target_fd >= 0:
            os.close(target_fd)
            target_fd = -1
        if created:
            try:
                _remove_tree(parent_fd, name)
            except OSError:
                pass
        raise
    finally:
        if target_fd >= 0:
            os.close(target_fd)


def _freeze_tree(source_fd: int, parent_fd: int, name: str):
    try:
        rows = list(walk_regular_files(
            source_fd,
            max_depth=SESSION_TREE_MAX_DEPTH,
            max_entries=SESSION_TREE_MAX_FILES,
        ))
    except SafeTreeError as exc:
        raise _error("live session tree cannot be captured", exc)
    if sum(row.size_bytes for row in rows) > SESSION_TREE_MAX_BYTES:
        raise _error("live session tree exceeds the byte bound")
    created = False
    target_fd = -1
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        created = True
        target_fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
        for row in rows:
            leaf_parent, owned = _open_parents(target_fd, row.relative_path)
            try:
                descriptor = os.open(
                    PurePosixPath(row.relative_path).name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL
                    | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=leaf_parent,
                )
                try:
                    copy_regular_file(
                        source_fd,
                        row.relative_path,
                        descriptor,
                        expected=row,
                        max_bytes=row.size_bytes,
                    )
                    os.fchmod(descriptor, stat.S_IMODE(row.mode))
                finally:
                    os.close(descriptor)
            finally:
                for descriptor in reversed(owned):
                    os.close(descriptor)
        return build_session_manifest(target_fd)
    except BaseException as exc:
        if target_fd >= 0:
            os.close(target_fd)
            target_fd = -1
        if created:
            try:
                _remove_tree(parent_fd, name)
            except OSError:
                pass
        if isinstance(exc, SafeTreeError):
            raise _error("live session tree cannot be captured", exc)
        raise
    finally:
        if target_fd >= 0:
            os.close(target_fd)




def _single_metadata(session_fd: int) -> tuple[str, dict[str, Any]]:
    names = []
    found = []
    try:
        with os.scandir(session_fd) as entries:
            for entry in entries:
                if len(names) >= _MAX_METADATA_FILES:
                    raise _error("provider session directory exceeds the entry bound")
                names.append(entry.name)
    except OSError as exc:
        raise _error("provider session directory cannot be listed", exc)
    for name in names:
        if not name.endswith(".json") or name.endswith(".session-link.json"):
            continue
        try:
            value = loads_strict(read_regular_file(
                session_fd, name, max_bytes=_MAX_METADATA_BYTES
            ).decode("utf-8"))
        except (SafeTreeError, UnicodeDecodeError, ValueError) as exc:
            raise _error("provider metadata cannot be admitted", exc)
        if isinstance(value, dict) and value.get("publication_state") == "published":
            found.append((name, value))
    if len(found) != 1:
        raise _error("run must have exactly one published OMP visit")
    return found[0]


def _scaffold_under_workspace(workspace: Path, scaffold: Path):
    workspace = Path(os.path.abspath(workspace))
    scaffold = Path(os.path.abspath(scaffold))
    try:
        relative = scaffold.relative_to(workspace)
    except ValueError as exc:
        raise _error("scaffold is outside workflow workspace", exc)
    if not relative.parts:
        raise _error("scaffold path is empty")
    try:
        workspace_fd = os.open(workspace, _DIR_FLAGS)
    except OSError as exc:
        raise _error("workflow workspace cannot be opened", exc)
    descriptor = os.dup(workspace_fd)
    try:
        for part in relative.parts:
            child = os.open(part, _DIR_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except OSError as exc:
        os.close(descriptor)
        os.close(workspace_fd)
        raise _error("scaffold path is not a no-follow directory", exc)
    return workspace, relative.as_posix(), workspace_fd, descriptor


def _captured_conf(verification) -> dict[str, bytes]:
    if verification.provider not in ("omp_conf", "omp_no_tools"):
        return {}
    if verification.provider == "omp_no_tools":
        files = {
            path[len(".omp-conf/"):]: data
            for path, data in verification.files.items()
            if path.startswith(".omp-conf/")
        }
    else:
        files = dict(verification.conf_files)
    if not files or files != dict(verification.conf_files):
        raise _error("captured conf bytes disagree")
    return files


def publish_prompt_run_link(
    manager: Any,
    *,
    workflow_workspace: Path,
    scaffold_path: Path,
    private_snapshot_fd: int,
    verification: Any,
    expected_run_identity: tuple[int, int],
) -> Path:
    """Validate captured/private/public/run agreement, freeze, then publish."""
    from orchestrator.prompt_session import _basename, extract_prompt_bytes, parse_session_link_bytes
    created: list[str] = []
    run_fd = session_fd = -1
    workspace_fd = scaffold_fd = -1
    try:
        run_fd = os.open(manager.run_root, _DIR_FLAGS)
        run_stat = os.fstat(run_fd)
        if (run_stat.st_dev, run_stat.st_ino) != expected_run_identity:
            raise _error("reserved run root identity changed")
        try:
            state = loads_strict(read_regular_file(run_fd, "state.json").decode("utf-8"))
        except (SafeTreeError, UnicodeDecodeError, ValueError) as exc:
            raise _error("run state cannot be admitted", exc)
        if not isinstance(state, dict) or state.get("run_id") != manager.run_id or state.get("status") != "completed":

            raise _error("run state is not completed")
        session_fd = os.open("provider_sessions", _DIR_FLAGS, dir_fd=run_fd)
        metadata_name, metadata = _single_metadata(session_fd)
        visit_key = metadata_name[:-5]
        if metadata_name != f"{visit_key}.json":
            raise _error("metadata filename is not canonical")
        try:
            os.stat(f"{visit_key}.transport.log", dir_fd=session_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise _error("transport spool cannot be checked", exc)
        else:
            raise _error("transport spool still exists")

        verify_captured_occupant(private_snapshot_fd, verification, private=True)
        workspace, scaffold_relpath, workspace_fd, scaffold_fd = _scaffold_under_workspace(
            workflow_workspace, scaffold_path
        )
        verify_captured_occupant(scaffold_fd, verification, private=False)

        conf_files = _captured_conf(verification)
        conf_digest = None
        conf_name = None
        if conf_files:
            conf_name = f"{visit_key}.conf"
            _freeze_bytes(conf_files, session_fd, conf_name)
            created.append(conf_name)
            conf_fd = os.open(conf_name, _DIR_FLAGS, dir_fd=session_fd)
            try:
                conf_digest = admit_conf_tree(conf_fd).manifest_sha256
            finally:
                os.close(conf_fd)
        frame, step_id = validate_publication_agreement(
            state=state,
            metadata=metadata,
            verification=verification,
            run_id=manager.run_id,
            visit_key=visit_key,
            conf_digest=conf_digest,
            private_snapshot_fd=private_snapshot_fd,
            run_root=os.fspath(manager.run_root),
            workflow_workspace=os.fspath(workflow_workspace),
        )
        primary = frame["session"]
        basename = _basename(primary["primary_relpath"], "frame primary")
        if basename is None or not basename.endswith(".jsonl"):
            raise _error("primary basename is invalid")
        live_fd = os.open(visit_key, _DIR_FLAGS, dir_fd=session_fd)
        try:
            live_manifest = build_session_manifest(live_fd)
            try:
                report = observe_close(
                    session_root_fd=live_fd,
                    stdout_session_id=primary["id"],
                    conf_manifest_sha256=conf_digest,
                    recognized_topologies=recognized_preset_topologies(),
                    isolated_worktree_root=None,
                )
            except OmpObservationError as exc:
                raise _error(f"live tree fails close-time observation: {exc}", exc)
            if (
                report.primary_relpath != primary["primary_relpath"]
                or list(report.advisor_relpaths) != frame["observed"]["advisor_relpaths"]
                or list(report.child_relpaths) != frame["observed"]["child_relpaths"]
            ):
                raise _error("adapter observed classification disagrees with live tree")
            rows = [row for row in live_manifest.rows if row.relative_path == basename]
            if len(rows) != 1:
                raise _error("live manifest lacks exact primary")
            journal_bytes = read_regular_file(live_fd, basename)
            row = rows[0]
            if len(journal_bytes) != row.size_bytes or hashlib.sha256(journal_bytes).hexdigest() != row.sha256:
                raise _error("primary journal disagrees with live manifest row")
            journal = parse_journal_bytes(journal_bytes, relpath=basename)
            if journal.header.id != primary["id"] or row.sha256 != primary["primary_sha256"]:
                raise _error("primary journal disagrees with adapter frame")
            composed = extract_prompt_bytes(journal)
            snapshot_name = f"{visit_key}.snapshot"
            snapshot_manifest = _freeze_tree(live_fd, session_fd, snapshot_name)
            created.append(snapshot_name)
        finally:
            os.close(live_fd)
        if live_manifest.manifest_sha256 != snapshot_manifest.manifest_sha256:
            raise _error("frozen session snapshot disagrees")

        authored = verification.files["prompt.md"]
        source = verification.files["run.orc"]
        manifest = verification.manifest
        semantic_sha = manifest.get("semantic_contract_sha256")
        paths = {
            "state": "state.json",
            "metadata": f"provider_sessions/{metadata_name}",
            "live": f"provider_sessions/{visit_key}",
            "snapshot": f"provider_sessions/{snapshot_name}",
            "conf": None if conf_name is None else f"provider_sessions/{conf_name}",
        }
        link = {
            "schema_version": "session_link.v1", "run_id": manager.run_id,
            "step_id": step_id, "visit_key": visit_key,
            "workflow_workspace": workspace.as_posix(),
            "scaffold_relpath": scaffold_relpath, "paths": paths,
            "session": {"id": primary["id"], "primary_basename": basename},
            "digests": {
                "live_manifest_sha256": live_manifest.manifest_sha256,
                "snapshot_manifest_sha256": snapshot_manifest.manifest_sha256,
                "conf_manifest_sha256": conf_digest,
                "scaffold_manifest_sha256": hashlib.sha256(verification.manifest_bytes).hexdigest(),
                "authored_prompt_sha256": hashlib.sha256(authored).hexdigest(),
                "composed_prompt_sha256": hashlib.sha256(composed).hexdigest(),
                "source_sha256": hashlib.sha256(source).hexdigest(),
                "semantic_contract_sha256": semantic_sha,
            },
            "provider": {
                "name": verification.provider, "model": verification.model,
                "lane": frame["lane"],
            },
            "scaffold_identity": verification.identity,
            "launch": {"argv": frame["child"]["argv"], "env_names": frame["child"]["env_names"]},
            "confinement": frame["confinement"],
        }
        payload = json.dumps(link, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        parse_session_link_bytes(payload)
        try:
            result = manager.publish_provider_session_link(
                visit_key,
                payload,
                expected_run_identity=expected_run_identity,
                session_dir_fd=session_fd,
            )
        except (FileExistsError, OSError, ValueError) as exc:
            raise _error("session link no-replace publication failed", exc)
        created.clear()
        return result
    except (
        OSError,
        SafeTreeError,
        OmpSessionError,
        OmpConfError,
        TypeError,
        ValueError,
    ) as exc:
        raise _error("session authority cannot be admitted", exc)
    finally:
        if created and session_fd >= 0:
            for name in reversed(created):
                try:
                    _remove_tree(session_fd, name)
                except OSError:
                    pass
        for descriptor in (scaffold_fd, workspace_fd, session_fd, run_fd):
            if descriptor >= 0:
                os.close(descriptor)


__all__ = ["publish_prompt_run_link", "with_private_execution_authority"]
