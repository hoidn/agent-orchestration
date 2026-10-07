"""Preparation and reuse checks for reached evaluated effects."""

from __future__ import annotations

from contextlib import closing, nullcontext
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from orchestrator.workflow.evaluated.attempts import attempt_paths
from orchestrator.workflow.evaluated.closure import ClosureEvidenceError, resolve_command_evidence
from orchestrator.workflow.evaluated.commands import (
    CommandTemplateError,
    render_command_argv,
    workspace_relative_path,
)
from orchestrator.workflow.evaluated.memo import JournalEntry, MemoSnapshot
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.workspace_files import WorkspaceFiles
from .authority import RunAuthority, workspace_result_locator
from .inputs import DocumentInputError, command_binding_kind, prepare_command_document
from .providers import resolve_provider_input
from .run_ref import require_run_ref_root, resolve_run_ref_input, validate_evaluated_run_ref


class _PreflightRefusal(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.preflight = True
        super().__init__(message)


class _EffectInputDiverged(_PreflightRefusal):
    def __init__(self, identity: str, detail: str) -> None:
        super().__init__(
            "effect_input_diverged",
            f"{identity}: effect input diverged ({detail})",
        )


def _replay_committed_effect(authority, node, operands, identity, reader, commit, workspace, snapshot, owner):
    resolved, parts, _implementation_files = _resolve_effect_input(
        authority, node, operands, identity, workspace, reader,
        commit, None, None, commit.data["result_path"],
        check_command_destinations=False, owner=owner,
    )
    dependencies = sorted({dependency for value in operands for dependency in value.dependencies})
    result = _reuse_effect_commit(
        authority, commit, node, identity, parts, canonical_sha256(parts), dependencies
    )
    if node["class"] == "run_ref":
        validate_evaluated_run_ref(authority, resolved, identity, workspace, commit,
            settled=(identity, commit.data["attempt"]) in snapshot.settlements)
    return result


def _check_resume_boundary(authority, snapshot, node, operands, identity, reader, workspace, owner) -> None:
    _ensure_effect_can_start(snapshot, identity, allow_unsettled=True)
    if node["class"] == "run_ref":
        require_run_ref_root(authority)
    baseline = _retry_baseline(snapshot, identity, snapshot.latest_starts.get(identity))
    if node["class"] == "command" and baseline is not None:
        _ordinal, attempt_directory, result_path = attempt_paths(snapshot, identity)
        _resolve_effect_input(
            authority, node, operands, identity, workspace, reader,
            None, baseline, attempt_directory, result_path, owner=owner,
            check_command_destinations=False,
        )
    elif node["class"] == "provider" and identity in snapshot.pending_starts:
        _ordinal, attempt_directory, result_path = attempt_paths(snapshot, identity)
        _resolve_effect_input(
            authority, node, operands, identity, workspace, reader,
            None, baseline, attempt_directory, result_path, owner=owner,
        )
    if baseline is not None and node.get("repeat") == "never":
        raise _PreflightRefusal(
            "lexical_restore_pending_effect_unsafe",
            f"{identity}: effect declares that it must not be repeated",
        )


def _resolve_effect_input(
    authority, node, operands, identity, workspace, reader,
    commit, baseline, attempt_directory, result_path, *, owner, workspace_files=None, check_command_destinations=True,
):
    """Resolve only the reached effect; command closure checks stay local."""
    if node["class"] == "command":
        return _resolve_command_input(authority, node, operands, identity, owner, workspace,
            commit, baseline, attempt_directory, result_path, workspace_files, check_command_destinations)
    elif node["class"] == "run_ref":
        require_run_ref_root(authority)
        resolved, parts = resolve_run_ref_input(node, operands)
        implementation_files = {}
    else:
        try:
            resolved = resolve_provider_input(node, operands, workspace=workspace, reader=reader,
                result_path=workspace_relative_path(workspace, authority.run_root / result_path))
        except Exception as exc:
            if commit is not None:
                raise _EffectInputDiverged(identity, f"provider inputs could not be resolved: {exc}") from exc
            raise
        parts = dict(resolved.input_parts)
        implementation_files = {}
    return resolved, parts, implementation_files


def _ensure_effect_can_start(snapshot: MemoSnapshot, identity: str, *, allow_unsettled=False) -> None:
    pending_elsewhere = sorted(set(snapshot.pending_starts) - {identity})
    if pending_elsewhere or (snapshot.unsettled_coordinators and not allow_unsettled):
        raise _PreflightRefusal(
            "memo_inconsistent",
            f"cannot start {identity}: other effect evidence is unsettled",
        )
    terminal = snapshot.terminal
    if terminal is not None and terminal.data["outcome"] == "completed":
        raise _PreflightRefusal(
            "memo_inconsistent",
            f"cannot start {identity}: run already has a completed terminal",
        )


def _resolve_command_input(authority, node, operands, identity, owner, workspace,
    commit, baseline, attempt_directory, result_path, workspace_files, check_destinations):
    previous = commit if commit is not None else baseline
    external = command_binding_kind(authority.program, owner, node["boundary"]) == "external_tool"
    with nullcontext(workspace_files) if workspace_files is not None else closing(WorkspaceFiles(workspace)) as files:
        argv, document, contract = _render_resolved_argv(node, operands, commit, identity,
            external=external, workspace=workspace, workspace_files=files)
    destinations = (_command_destinations(authority, attempt_directory, result_path,
        include_input=external and document is not None)
        if commit is None and check_destinations else ())
    implementation_files = _resolve_command_implementation(node, workspace, identity,
        None if previous is None else previous.data["implementation_files"], destinations)
    _check_retry_implementation(identity, baseline, implementation_files)
    parts = _command_input_parts(node, argv, implementation_files, document)
    if external and document is not None:
        parts["input_contract"] = canonical_sha256(contract)
    return (argv, document if external else None), parts, implementation_files


def _render_resolved_argv(node, operands, commit, identity, *, external, workspace, workspace_files):
    try:
        tail = render_command_argv(node, operands)
        document, contract = prepare_command_document(node, operands, external=external,
            workspace=workspace, workspace_files=workspace_files)
    except (CommandTemplateError, DocumentInputError) as exc:
        if commit is not None:
            detail = "document validation failed" if isinstance(exc, DocumentInputError) else "template resolution failed"
            error = _EffectInputDiverged(identity, f"{detail}: {exc}")
            if isinstance(exc, DocumentInputError):
                error.field, error.value_path, error.violation = exc.field, exc.value_path, exc.violation
                error.violations = exc.violations
            raise error from exc
        raise
    argv = [*node["command"], *tail]
    if document is not None and not external:
        argv.append(document.decode("utf-8"))
    return argv, document, contract


def _resolve_command_implementation(node, workspace, identity, previous, destinations):
    try:
        return resolve_command_evidence(
            node["command"],
            node["closure"],
            workspace_root=workspace,
            prior=previous,
            destinations=destinations,
        )
    except ClosureEvidenceError as exc:
        if previous is not None and not _is_destination_overlap(exc):
            raise _EffectInputDiverged(
                identity, f"implementation evidence could not be re-resolved: {exc}"
            ) from exc
        raise


def _check_retry_implementation(identity, baseline, implementation_files) -> None:
    if baseline is None or implementation_files == baseline.data["implementation_files"]:
        return
    changed = _changed_evidence(baseline.data["implementation_files"], implementation_files)
    raise _EffectInputDiverged(identity, f"retry implementation files changed: {changed}")


def _reuse_effect_commit(authority, commit, node, identity, parts, input_digest, dependencies):
    row = commit.data
    changed_parts = sorted(
        name for name in set(parts) | set(row["input_parts"])
        if parts.get(name) != row["input_parts"].get(name)
    )
    dependency_changed = dependencies != row["depends_on"]
    if input_digest != row["input_digest"] or changed_parts or dependency_changed:
        raise _EffectInputDiverged(
            identity,
            f"input parts changed: {changed_parts}; dependency identities changed: {dependency_changed}; previous {row['input_digest']}, current {input_digest}",
        )
    return coerce_evaluated_value(
        row["value"],
        node["result"],
        dependencies=(*dependencies, identity),
        committed_result_path=workspace_result_locator(authority.header, row["result_path"]),
        context=f"committed {node['class']} result",
    )


def _retry_baseline(
    snapshot: MemoSnapshot,
    identity: str,
    latest_start: JournalEntry | None,
) -> JournalEntry | None:
    if latest_start is None:
        return None
    row = latest_start.data
    commit = next(
        (
            entry
            for entry in reversed(snapshot.entries)
            if entry.data.get("record") == "committed"
            and entry.data.get("identity") == identity
            and entry.data.get("attempt") == row["attempt"]
        ),
        None,
    )
    if commit is not None and any(
        entry.offset > commit.offset
        and entry.data.get("record") == "invalidated"
        and entry.data.get("from_commit", commit.offset + 1) <= commit.offset
        for entry in snapshot.entries
    ):
        return None
    return latest_start


def _command_destinations(
    authority: RunAuthority,
    attempt_directory: str,
    result_path: str,
    *, include_input: bool = False,
) -> tuple[Path, ...]:
    run_root = authority.run_root
    attempt_root = run_root / attempt_directory
    paths = [
        attempt_root,
        run_root / result_path,
        attempt_root / "stdout.txt",
        attempt_root / "stderr.txt",
        authority.memo_path,
    ]
    if include_input:
        paths.append(attempt_root / "inputs.json")
    return tuple(paths)


def _command_input_parts(
    node: Mapping[str, Any],
    resolved_argv: Sequence[str],
    implementation_files: Mapping[str, Any],
    document_bytes: bytes | None,
) -> dict[str, str]:
    parts = {
        "argv": canonical_sha256(list(resolved_argv)),
        "contract": canonical_sha256(node["contract"]),
        "closure": canonical_sha256(node["closure"]),
        "implementation_files": canonical_sha256(dict(implementation_files)),
    }
    if document_bytes is not None:
        parts["document"] = "sha256:" + hashlib.sha256(document_bytes).hexdigest()
    return parts


def _changed_evidence(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    return sorted(
        key for key in set(before) | set(after) if before.get(key) != after.get(key)
    )


def _is_destination_overlap(exc: ClosureEvidenceError) -> bool:
    return "runtime destination overlaps command closure" in exc.reason
